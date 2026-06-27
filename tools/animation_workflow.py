# vim:ts=4:et
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from ..utils import collect_hierarchy_objects
from ..utils.blender_compat import iter_action_fcurves


TRANSFORM_ITEMS = (
    ('thrustTransform', "thrustTransform", "Engine thrust transform"),
    ('fxTransform', "fxTransform", "Particle or audio effect transform"),
    ('gimbal', "gimbal", "Engine gimbal pivot transform"),
    ('deployPivot', "deployPivot", "Deploy animation pivot transform"),
    ('lightTransform', "lightTransform", "Light source transform"),
)

OBJECT_ANIM_PROPS = {"location", "rotation_quaternion", "rotation_euler", "scale"}
LIGHT_ANIM_PROPS = {"color", "energy"}
MATERIAL_PREFIXES = (
    "mumatprop.color.",
    "mumatprop.vector.",
    "mumatprop.float2.",
    "mumatprop.float3.",
)
VALIDATION_TEXT_NAME = "KSP Animation Export Validation"


class KSPMUAnimationWorkflowProperties(bpy.types.PropertyGroup):
    clip_name: StringProperty(name="Clip", default="deploy")
    start_frame: IntProperty(name="Start", default=1)
    end_frame: IntProperty(name="End", default=60, min=1)
    loop: BoolProperty(name="Loop", default=False)

    start_event_gui_name: StringProperty(name="Start Event", default="Start")
    end_event_gui_name: StringProperty(name="End Event", default="End")
    action_gui_name: StringProperty(name="Action", default="Toggle")

    helper_type: EnumProperty(
        name="Transform",
        items=TRANSFORM_ITEMS,
        default='thrustTransform',
    )
    last_validation: StringProperty(name="Last Validation", default="Not run")


def safe_idprop_get(data, name, default=None):
    try:
        return data.get(name, default)
    except (AttributeError, TypeError):
        return default


def safe_idprop_set(data, name, value):
    try:
        data[name] = value
    except TypeError:
        pass


def iter_hierarchy(root):
    if not root:
        return []
    return collect_hierarchy_objects(root)


def action_fcurves(action):
    return list(iter_action_fcurves(action))


def has_action_curves(action):
    return bool(action and action_fcurves(action))


def ensure_animation_data(data):
    if not data.animation_data:
        data.animation_data_create()
    return data.animation_data


def set_action_metadata(action, props):
    safe_idprop_set(action, "ksp_clip_name", props.clip_name)
    safe_idprop_set(action, "ksp_start_frame", props.start_frame)
    safe_idprop_set(action, "ksp_end_frame", props.end_frame)
    safe_idprop_set(action, "ksp_loop", props.loop)
    for attr, value in (
        ("use_frame_range", True),
        ("frame_start", props.start_frame),
        ("frame_end", props.end_frame),
    ):
        if hasattr(action, attr):
            try:
                setattr(action, attr, value)
            except TypeError:
                pass


def mark_nla_clip(track, strip, props):
    for data in (track, strip):
        safe_idprop_set(data, "ksp_clip_name", props.clip_name)
        safe_idprop_set(data, "ksp_start_frame", props.start_frame)
        safe_idprop_set(data, "ksp_end_frame", props.end_frame)
        safe_idprop_set(data, "ksp_loop", props.loop)


def clip_loop(track):
    if safe_idprop_get(track, "ksp_loop", False):
        return True
    for strip in track.strips:
        if safe_idprop_get(strip, "ksp_loop", False):
            return True
        if strip.action and safe_idprop_get(strip.action, "ksp_loop", False):
            return True
    return False


def nla_clip_name(track, strip):
    action = strip.action if strip else None
    return (safe_idprop_get(track, "ksp_clip_name", "")
            or track.name
            or safe_idprop_get(strip, "ksp_clip_name", "")
            or safe_idprop_get(action, "ksp_clip_name", "")
            or strip.name
            or (action.name if action else ""))


def iter_animation_sources(obj):
    if obj.type == 'ARMATURE':
        yield obj, "ARMATURE", obj
    else:
        yield obj, "OBJECT", obj
    data = getattr(obj, "data", None)
    if data:
        if obj.type == 'LIGHT':
            yield data, "LIGHT", obj
    if obj.type == 'MESH' and data:
        for mat in data.materials:
            if mat:
                yield mat, "MATERIAL", obj


def iter_clip_entries(root):
    for obj in iter_hierarchy(root):
        for data, source_type, owner in iter_animation_sources(obj):
            ad = getattr(data, "animation_data", None)
            if not ad:
                continue
            for track in ad.nla_tracks:
                for strip in track.strips:
                    yield {
                        "name": nla_clip_name(track, strip),
                        "track": track,
                        "strip": strip,
                        "action": strip.action,
                        "source": data,
                        "source_type": source_type,
                        "owner": owner,
                        "loop": clip_loop(track),
                    }
            if ad.action and not ad.nla_tracks:
                yield {
                    "name": safe_idprop_get(ad.action, "ksp_clip_name",
                                            ad.action.name),
                    "track": None,
                    "strip": None,
                    "action": ad.action,
                    "source": data,
                    "source_type": source_type,
                    "owner": owner,
                    "loop": safe_idprop_get(ad.action, "ksp_loop", False),
                }


def collect_clip_names(root):
    clips = {}
    for entry in iter_clip_entries(root):
        name = entry["name"]
        if name not in clips:
            clips[name] = entry
    return clips


def selected_clip_name(context):
    props = context.scene.kspanimprops
    if props.clip_name.strip():
        return props.clip_name.strip()
    obj = context.active_object
    if not obj:
        return ""
    clips = collect_clip_names(obj)
    return next(iter(clips), "")


def write_text_block(name, body):
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    else:
        text.clear()
    text.write(body)
    return text


def action_has_unsupported_paths(action, source_type):
    unsupported = []
    for curve in action_fcurves(action):
        data_path = curve.data_path
        if source_type == "MATERIAL":
            if data_path.startswith("mumatprop.texture."):
                unsupported.append(data_path)
            elif not data_path.startswith(MATERIAL_PREFIXES):
                unsupported.append(data_path)
        elif source_type == "LIGHT":
            if data_path not in LIGHT_ANIM_PROPS:
                unsupported.append(data_path)
        elif source_type == "ARMATURE":
            if data_path in OBJECT_ANIM_PROPS:
                continue
            if data_path.startswith('pose.bones["'):
                prop = data_path.rsplit(".", 1)[-1]
                if prop in OBJECT_ANIM_PROPS:
                    continue
            unsupported.append(data_path)
        else:
            if data_path not in OBJECT_ANIM_PROPS:
                unsupported.append(data_path)
    return unsupported


def object_has_animation(obj):
    for data, source_type, owner in iter_animation_sources(obj):
        ad = getattr(data, "animation_data", None)
        if not ad:
            continue
        if ad.action or any(track.strips for track in ad.nla_tracks):
            return True
    return False


def draw_action_summary(layout, obj):
    ad = obj.animation_data
    action_name = ad.action.name if ad and ad.action else "None"
    row = layout.row()
    row.label(text="Action:")
    row.label(text=action_name, icon='ACTION')
    if not ad:
        return
    if not ad.nla_tracks:
        layout.label(text="NLA: None", icon='NLA')
        return
    for index, track in enumerate(ad.nla_tracks):
        if index >= 5:
            break
        names = [nla_clip_name(track, strip) for strip in track.strips]
        label = track.name
        if names:
            label += " - " + ", ".join(names)
        icon = 'FILE_REFRESH' if clip_loop(track) else 'NLA'
        layout.label(text=label, icon=icon)
    if len(ad.nla_tracks) > 5:
        layout.label(text="... %d more NLA tracks" % (len(ad.nla_tracks) - 5))


def draw_model_clip_summary(layout, obj):
    clips = collect_clip_names(obj)
    box = layout.box()
    box.label(text="Model Clips", icon='SEQUENCE')
    if not clips:
        box.label(text="None")
        return
    for index, (name, entry) in enumerate(clips.items()):
        if index >= 8:
            box.label(text="... %d more clips" % (len(clips) - 8))
            break
        icon = 'FILE_REFRESH' if entry["loop"] else 'ACTION'
        label = name or "<empty>"
        box.label(text=label, icon=icon)


class KSPMU_OT_KSPAnimationNewClip(bpy.types.Operator):
    '''Create a new KSP animation action on the active object'''
    bl_idname = "object.ksp_animation_new_clip"
    bl_label = "New KSP Clip"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        props = context.scene.kspanimprops
        clip_name = props.clip_name.strip()
        if not clip_name:
            self.report({'ERROR'}, "KSP clip name cannot be empty")
            return {'CANCELLED'}

        obj = context.active_object
        action = bpy.data.actions.new(clip_name)
        set_action_metadata(action, props)
        ensure_animation_data(obj).action = action
        context.scene.frame_start = props.start_frame
        context.scene.frame_end = max(props.end_frame, props.start_frame)
        self.report({'INFO'}, "Created KSP clip action '%s'" % clip_name)
        return {'FINISHED'}


class KSPMU_OT_KSPAnimationPushActionToNLA(bpy.types.Operator):
    '''Push the active action to an NLA track named as the KSP clip'''
    bl_idname = "object.ksp_animation_push_action_to_nla"
    bl_label = "Push Action to NLA"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.animation_data and obj.animation_data.action)

    def execute(self, context):
        props = context.scene.kspanimprops
        clip_name = props.clip_name.strip()
        if not clip_name:
            self.report({'ERROR'}, "KSP clip name cannot be empty")
            return {'CANCELLED'}

        obj = context.active_object
        ad = obj.animation_data
        action = ad.action
        action.name = clip_name
        set_action_metadata(action, props)

        start = props.start_frame
        end = max(props.end_frame, start + 1)
        track = ad.nla_tracks.new()
        track.name = clip_name
        strip = track.strips.new(clip_name, start, action)
        strip.name = clip_name
        try:
            strip.frame_start = start
            strip.frame_end = end
            strip.action_frame_start = start
            strip.action_frame_end = end
        except TypeError:
            pass
        mark_nla_clip(track, strip, props)
        ad.action = None
        self.report({'INFO'}, "Pushed action to KSP NLA clip '%s'" % clip_name)
        return {'FINISHED'}


class KSPMU_OT_KSPCreateTransformHelper(bpy.types.Operator):
    '''Create a KSP/Unity axis transform empty at the 3D cursor'''
    bl_idname = "object.ksp_create_transform_helper"
    bl_label = "Create KSP Transform"
    bl_options = {'REGISTER', 'UNDO'}

    transform_type: EnumProperty(
        name="Transform",
        items=TRANSFORM_ITEMS,
        default='thrustTransform',
    )

    def execute(self, context):
        parent = context.active_object
        transform_type = self.transform_type
        if not transform_type:
            transform_type = context.scene.kspanimprops.helper_type

        collection = context.collection
        if parent and parent.users_collection:
            collection = parent.users_collection[0]

        obj = bpy.data.objects.new(transform_type, None)
        obj.empty_display_type = 'ARROWS'
        obj.empty_display_size = 0.35
        obj.show_name = True
        obj.show_in_front = True
        obj.rotation_mode = 'QUATERNION'
        obj["ksp_transform_type"] = transform_type
        obj["ksp_axis_hint"] = "Unity +Z = Blender +Y, Unity +Y = Blender +Z"
        collection.objects.link(obj)

        obj.matrix_world = context.scene.cursor.matrix
        if parent:
            obj.parent = parent
            obj.matrix_world = context.scene.cursor.matrix

        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({'INFO'}, "Created %s" % transform_type)
        return {'FINISHED'}


class KSPMU_OT_KSPGenerateModuleAnimateGeneric(bpy.types.Operator):
    '''Generate a ModuleAnimateGeneric cfg snippet into a Blender text block'''
    bl_idname = "object.ksp_generate_module_animate_generic"
    bl_label = "Generate ModuleAnimateGeneric"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.kspanimprops
        clip_name = selected_clip_name(context)
        if not clip_name:
            self.report({'ERROR'}, "No KSP animation clip selected")
            return {'CANCELLED'}

        cfg = (
            "MODULE\n"
            "{\n"
            "    name = ModuleAnimateGeneric\n"
            "    animationName = %s\n"
            "    startEventGUIName = %s\n"
            "    endEventGUIName = %s\n"
            "    actionGUIName = %s\n"
            "}\n"
        ) % (
            clip_name,
            props.start_event_gui_name,
            props.end_event_gui_name,
            props.action_gui_name,
        )
        text = write_text_block("ModuleAnimateGeneric_%s.cfg" % clip_name, cfg)
        self.report({'INFO'}, "Wrote cfg snippet to text block '%s'" % text.name)
        return {'FINISHED'}


class KSPMU_OT_KSPAnimationValidateExport(bpy.types.Operator):
    '''Validate active KSP animation export setup'''
    bl_idname = "object.ksp_animation_validate_export"
    bl_label = "Validate KSP Animation Export"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        root = context.active_object
        hierarchy = set(iter_hierarchy(root))
        messages = []
        entries = list(iter_clip_entries(root))

        if not entries:
            messages.append(("ERROR", "No action or NLA strip found under export root '%s'" % root.name))

        for entry in entries:
            name = entry["name"]
            action = entry["action"]
            owner = entry["owner"]
            if not name:
                messages.append(("ERROR", "Empty clip name on '%s'" % owner.name))
            if not action:
                messages.append(("ERROR", "NLA clip '%s' has no action" % (name or "<empty>")))
                continue
            if not has_action_curves(action):
                messages.append(("WARNING", "Clip '%s' action '%s' has no f-curves" % (name, action.name)))
            unsupported = action_has_unsupported_paths(action, entry["source_type"])
            for data_path in unsupported:
                messages.append(("WARNING",
                                 "Unsupported animated property '%s' in action '%s' on '%s'"
                                 % (data_path, action.name, owner.name)))

        for obj in hierarchy:
            if (obj.instance_type == 'COLLECTION' and obj.instance_collection):
                messages.append(("ERROR",
                                 "Collection instance '%s' must be realized before export"
                                 % obj.name))
            if obj.constraints and object_has_animation(obj):
                messages.append(("WARNING",
                                 "Animated object '%s' has constraints that may need baking"
                                 % obj.name))
            if obj.type == 'ARMATURE':
                for bone in obj.pose.bones:
                    if bone.constraints:
                        messages.append(("WARNING",
                                         "Armature '%s' pose bone '%s' has constraints that may need baking"
                                         % (obj.name, bone.name)))

        for obj in context.selected_objects:
            if obj not in hierarchy and object_has_animation(obj):
                messages.append(("WARNING",
                                 "Selected animated object '%s' is outside export root '%s'"
                                 % (obj.name, root.name)))

        if not messages:
            messages.append(("OK", "No KSP animation export issues found"))

        errors = sum(1 for level, msg in messages if level == "ERROR")
        warnings = sum(1 for level, msg in messages if level == "WARNING")
        body = "KSP Animation Export Validation: %s\n\n" % root.name
        body += "\n".join("%s: %s" % item for item in messages)
        body += "\n"
        write_text_block(VALIDATION_TEXT_NAME, body)

        summary = "%d error(s), %d warning(s)" % (errors, warnings)
        context.scene.kspanimprops.last_validation = summary
        report_level = {'ERROR'} if errors else {'WARNING'} if warnings else {'INFO'}
        self.report(report_level, summary)
        return {'FINISHED'}


class VIEW3D_PT_KSPAnimationPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_context = ".objectmode"
    bl_label = "KSP Animation"

    def draw(self, context):
        layout = self.layout
        props = context.scene.kspanimprops
        obj = context.active_object

        if obj:
            layout.label(text=obj.name, icon='OBJECT_DATA')
            draw_action_summary(layout, obj)
            draw_model_clip_summary(layout, obj)
        else:
            layout.label(text="No active object", icon='ERROR')

        box = layout.box()
        box.label(text="Clip", icon='ACTION')
        box.prop(props, "clip_name")
        row = box.row(align=True)
        row.prop(props, "start_frame")
        row.prop(props, "end_frame")
        box.prop(props, "loop")
        row = box.row(align=True)
        row.operator("object.ksp_animation_new_clip", text="New")
        row.operator("object.ksp_animation_push_action_to_nla", text="Push NLA")

        box = layout.box()
        box.label(text="Transform / Axis Helper", icon='EMPTY_AXIS')
        box.prop(props, "helper_type")
        op = box.operator("object.ksp_create_transform_helper", text="Create")
        op.transform_type = props.helper_type
        box.operator_menu_enum("object.ksp_create_transform_helper",
                               "transform_type", text="Create Common")

        box = layout.box()
        box.label(text="ModuleAnimateGeneric", icon='TEXT')
        box.prop(props, "start_event_gui_name")
        box.prop(props, "end_event_gui_name")
        box.prop(props, "action_gui_name")
        box.operator("object.ksp_generate_module_animate_generic",
                     text="Generate cfg")

        box = layout.box()
        box.label(text="Export Validator", icon='CHECKMARK')
        box.operator("object.ksp_animation_validate_export", text="Validate")
        box.label(text=props.last_validation)


classes_to_register = (
    KSPMUAnimationWorkflowProperties,
    KSPMU_OT_KSPAnimationNewClip,
    KSPMU_OT_KSPAnimationPushActionToNLA,
    KSPMU_OT_KSPCreateTransformHelper,
    KSPMU_OT_KSPGenerateModuleAnimateGeneric,
    KSPMU_OT_KSPAnimationValidateExport,
    VIEW3D_PT_KSPAnimationPanel,
)

custom_properties_to_register = (
    (bpy.types.Scene, "kspanimprops", KSPMUAnimationWorkflowProperties),
)
