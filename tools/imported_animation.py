"""Per-part source clips: opt-in NLA scheduling and persistent bindings."""
import math
import json
import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty
from ..utils.blender_compat import iter_action_fcurves
from ..utils.import_assets import (uid, binding_target, set_binding, model_root,
                                   collect_clips, walk_objects, set_auxiliary_visibility,
                                   data_snapshot, cleanup_new_data)
from ..utils.import_assets import capture_rest, restore_values
from ..utils.import_assets import resolve_playback, remove_playback
from ..utils.import_assets import resolve_override, covered_by_other
from ..utils.import_assets import update_baselines
from ..utils.blender_compat import ensure_action_fcurve


def curves(action, slot_source=None):
    return {(fc.data_path, fc.array_index) for fc in iter_action_fcurves(action, slot_source) if not fc.mute}


def selected_clip(root):
    clips = collect_clips(root)
    try:
        index = int(root.ksp_assets.clip_choice)
    except ValueError:
        index = 0
    if not 0 <= index < len(clips):
        raise ValueError("该零件没有可选择的导入动画")
    return index, clips[index][1]


def validate_range(clip, start, end):
    if not all(math.isfinite(x) for x in (start, end)):
        raise ValueError("帧区间必须为有限数值")
    if end <= start:
        raise ValueError("源结束帧必须大于源开始帧")
    if start < clip.start - 0.0001 or end > clip.end + 0.0001:
        raise ValueError(f"源区间必须在 {clip.start:g}–{clip.end:g} 内")
    if not clip.bindings:
        raise ValueError("此片段没有可绑定通道，请查看导入报告")
    for binding in clip.bindings:
        target = binding_target(binding)
        if not target or not binding.action:
            raise ValueError(f"动画目标或资源已删除：{binding.path}")
        ad = getattr(target, "animation_data", None)
        if ad and ad.use_tweak_mode:
            raise ValueError(f"请先退出 NLA 编辑模式：{target.name}")
        if ad and any(track.is_solo for track in ad.nla_tracks):
            raise ValueError(f"请先取消 NLA 轨道独奏：{target.name}")
        for fc in iter_action_fcurves(binding.action):
            try:
                target.path_resolve(fc.data_path)
            except (ValueError, TypeError):
                raise ValueError(f"通道无法绑定：{target.name}: {fc.data_path}")


def clip_conflicts(clip, start, end):
    result, seen = [], set()
    for binding in clip.bindings:
        target = binding_target(binding)
        ad = getattr(target, "animation_data", None)
        if not ad:
            continue
        channels = curves(binding.action)
        if ad.action and curves(ad.action, ad) & channels:
            key = (target.as_pointer(), 'ACTIVE')
            if key not in seen:
                result.append((target, None, None))
                seen.add(key)
        for track in ad.nla_tracks:
            if track.mute:
                continue
            for strip in track.strips:
                if strip.mute or not strip.action:
                    continue
                if strip.action.get('ksp_baseline'):
                    continue
                if strip.frame_start >= end or strip.frame_end <= start:
                    continue
                if not curves(strip.action, strip) & channels:
                    continue
                key = (target.as_pointer(), strip.as_pointer())
                if key not in seen:
                    result.append((target, track, strip))
                    seen.add(key)
    return result


def assign_slot(strip, action):
    if hasattr(strip, "action_slot") and len(action.slots):
        strip.action_slot = action.slots[0]


def ensure_realized(root, context):
    if not any(obj.instance_type == 'COLLECTION' and obj.instance_collection
               for obj in walk_objects(root)):
        return root, None
    from ..model import realize_model_instance
    collection = root.users_collection[0]
    original = root
    root = realize_model_instance(original, collection, original.parent)
    root.matrix_world = original.matrix_world.copy()
    context.view_layer.objects.active = root
    return root, original


def restore_override(saved):
    target = binding_target(saved)
    ad = getattr(target, "animation_data", None)
    track, strip = resolve_override(saved)
    if saved.active:
        if not ad or (ad.action and ad.action != saved.action):
            return
        ad.action = saved.action
        if hasattr(ad, "action_slot_handle"):
            ad.action_slot_handle = saved.slot_handle
        ad.action_blend_type = saved.active_blend
        ad.action_extrapolation = saved.active_extrapolation
        ad.action_influence = saved.active_influence
        if strip:
            track.strips.remove(strip)
            if not track.strips:
                ad.nla_tracks.remove(track)
        else:
            track = ad.nla_tracks.get(saved.track)
            if track and not track.strips:
                ad.nla_tracks.remove(track)
    elif strip:
        strip.mute = saved.was_mute


def live_channels(target):
    ad = getattr(target, 'animation_data', None)
    result = set()
    if ad:
        if ad.action:
            result.update(curves(ad.action, ad))
        for track in ad.nla_tracks:
            if not track.mute:
                for strip in track.strips:
                    if not strip.mute and strip.action:
                        result.update(curves(strip.action, strip))
    return result


def ensure_baseline(root, source):
    target = binding_target(source)
    props = root.ksp_assets
    baseline = next((b for b in props.baselines if binding_target(b) == target), None)
    values = json.loads(source.rest or capture_rest(target, source.action))
    if baseline is None:
        # Do not mask unrelated user-authored animation with a static pose.
        if live_channels(target) & {(path, channel) for path, channel, _ in values}:
            return
        baseline = props.baselines.add()
        action = bpy.data.actions.new('KSP static imported pose')
        action['ksp_baseline'] = True
        set_binding(baseline, target, action, source.path)
        ad = target.animation_data or target.animation_data_create()
        ad = target.animation_data
        track = ad.nla_tracks.new()
        track.name = 'KSP baseline ' + uid()
        baseline.track = track.name
    action = baseline.action
    old_values = json.loads(baseline.rest or '[]')
    existing = curves(action)
    ad = target.animation_data
    previous = ad.action
    previous_slot = getattr(ad, 'action_slot_handle', 0)
    try:
        for path, channel, value in values:
            if (path, channel) in existing:
                continue
            fc = ensure_action_fcurve(action, target, path, channel)
            for frame in (0, 1):
                key = fc.keyframe_points.insert(frame, value)
                key.interpolation = 'CONSTANT'
            old_values.append([path, channel, value])
    finally:
        ad.action = previous
        if previous:
            ad.action_slot_handle = previous_slot
    baseline.rest = json.dumps(old_values)
    track, _ = resolve_playback(baseline)
    track = track or ad.nla_tracks.get(baseline.track)
    if not track:
        track = ad.nla_tracks.new()
        track.name = 'KSP baseline ' + uid()
        baseline.track = track.name
    if not track.strips:
        strip = track.strips.new('Imported static pose', 0, action)
        assign_slot(strip, action)
        strip.extrapolation = 'HOLD'
        baseline.strip = strip.name


def remove_scheduled(root, group_id):
    props = root.ksp_assets
    index = next((i for i, entry in enumerate(props.scheduled) if entry.uid == group_id), -1)
    if index < 0:
        raise ValueError("片段已移除")
    group = props.scheduled[index]
    actions = set(e.action for e in group.entries if e.action)
    for entry in group.entries:
        remove_playback(entry)
    for saved in group.overrides:
        if not saved.active and covered_by_other(root, group, binding_target(saved), saved.action):
            continue
        # Keep a preserved active Action stashed while other plugin clips need NLA.
        other = next((g for g in props.scheduled if g.uid != group.uid and saved.active
                      and any(binding_target(e) == binding_target(saved) for e in g.entries)), None)
        if other:
            copy = other.overrides.add()
            set_binding(copy, binding_target(saved), saved.action, saved.path)
            for field in ("track", "strip", "active", "slot_handle", "was_mute",
                          "active_blend", "active_extrapolation", "active_influence"):
                setattr(copy, field, getattr(saved, field))
            copy.frame_start, copy.frame_end = saved.frame_start, saved.frame_end
        else:
            restore_override(saved)
    props.scheduled.remove(index)
    from ..properties.imported_assets import update_playback
    for other in props.scheduled:
        # An overridden plugin playback that was explicitly removed is no
        # longer a restoration target. Release its retained Action pointer.
        for i in reversed(range(len(other.overrides))):
            saved = other.overrides[i]
            if not saved.active and saved.action in actions:
                other.overrides.remove(i)
        update_playback(other, bpy.context)
    for i in reversed(range(len(props.baselines))):
        baseline = props.baselines[i]
        target = binding_target(baseline)
        if any(binding_target(e) == target for g in props.scheduled for e in g.entries):
            continue
        ad = getattr(target, 'animation_data', None)
        remove_playback(baseline)
        if target:
            restore_values(target, json.loads(baseline.rest or '[]'), live_channels(target))
        if baseline.action:
            actions.add(baseline.action)
        props.baselines.remove(i)
    for action in actions:
        if not action.users and not action.use_fake_user:
            bpy.data.actions.remove(action)


def add_clip(root, context, mode='CANCEL'):
    props = root.ksp_assets
    clip_index, clip = selected_clip(root)
    source_start, source_end = props.source_start, props.source_end
    insert, hold = props.insert_frame, props.hold
    if not math.isfinite(insert):
        raise ValueError("插入帧必须为有限数值")
    validate_range(clip, source_start, source_end)
    source_key = f"{clip_index}:{clip.uid}"
    if any(g.source_key == source_key
           and abs(g.source_start - source_start) < 0.0001
           and abs(g.source_end - source_end) < 0.0001
           and abs(g.start - insert) < 0.0001 for g in props.scheduled):
        raise ValueError("相同片段、区间和插入位置已存在")
    factor = context.scene.render.fps / context.scene.render.fps_base / clip.fps
    end = insert + (source_end - source_start) * factor
    conflicts = clip_conflicts(clip, insert, end)
    if conflicts and mode == 'CANCEL':
        raise ValueError("与已有动画冲突，请选择覆盖、融合或取消")
    snapshot = data_snapshot()
    root, original = ensure_realized(root, context)
    group = None
    try:
        props = root.ksp_assets
        clip = collect_clips(root)[clip_index][1]
        validate_range(clip, source_start, source_end)
        conflicts = clip_conflicts(clip, insert, end)
        group = props.scheduled.add()
        group.uid, group.name = uid(), clip.name
        group.source_key = source_key
        group.source_start, group.source_end = source_start, source_end
        group.start, group.end, group.hold = insert, end, hold
        group.blend = 'COMBINE' if mode == 'BLEND' else 'REPLACE'
        for target, track, strip in conflicts:
            saved = group.overrides.add()
            ad = target.animation_data
            set_binding(saved, target, ad.action if track is None else strip.action)
            if track is None:
                saved.active = True
                saved.slot_handle = getattr(ad, "action_slot_handle", 0)
                saved.active_blend = ad.action_blend_type
                saved.active_extrapolation = ad.action_extrapolation
                saved.active_influence = ad.action_influence
                action = ad.action
                a, b = action.frame_range
                track = ad.nla_tracks.new()
                track.name = "KSP preserved " + group.uid
                saved.track = track.name
                strip = track.strips.new(action.name, math.floor(a), action)
                saved.strip = strip.name
                saved.frame_start, saved.frame_end = strip.frame_start, strip.frame_end
                assign_slot(strip, action)
                for slot in action.slots:
                    if slot.handle == saved.slot_handle:
                        strip.action_slot = slot
                strip.frame_start, strip.frame_end = a, max(a + 1, b)
                strip.extrapolation = saved.active_extrapolation
                strip.blend_type = saved.active_blend
                strip.influence = saved.active_influence
                saved.track, saved.strip = track.name, strip.name
                saved.frame_start, saved.frame_end = strip.frame_start, strip.frame_end
                ad.action = None
                strip.mute = mode != 'BLEND'
            else:
                saved.track, saved.strip, saved.was_mute = track.name, strip.name, strip.mute
                saved.frame_start, saved.frame_end = strip.frame_start, strip.frame_end
                strip.mute = mode != 'BLEND'
        for binding_index, binding in enumerate(clip.bindings):
            target = binding_target(binding)
            if not target.animation_data:
                target.animation_data_create()
            ensure_baseline(root, binding)
            action = binding.action.copy()
            action.name = clip.name + " [KSP playback]"
            action.use_fake_user = False
            action["ksp_playback_uid"] = group.uid
            entry = group.entries.add()
            set_binding(entry, target, action, binding.path, binding.rest)
            track = target.animation_data.nla_tracks.new()
            track.name = f"KSP {group.uid} {binding_index}"
            entry.track = track.name
            strip = track.strips.new(clip.name, math.floor(insert), action)
            entry.strip = strip.name
            assign_slot(strip, action)
            strip.action_frame_start, strip.action_frame_end = source_start, source_end
            strip.frame_start, strip.frame_end = insert, end
            strip.blend_type = group.blend
            strip.influence = 1
            strip.extrapolation = 'HOLD_FORWARD' if hold else 'NOTHING'
        update_baselines(root)
        if original:
            bpy.data.objects.remove(original, do_unlink=True)
        context.view_layer.objects.active = root
        context.view_layer.update()
        return root, group
    except Exception:
        if group:
            remove_scheduled(root, group.uid)
        if original:
            from ..utils.import_assets import walk_objects
            for obj in reversed(list(walk_objects(root))):
                bpy.data.objects.remove(obj, do_unlink=True)
            cleanup_new_data(snapshot)
            context.view_layer.objects.active = original
        raise


class KSP_OT_ImportedClipAdd(bpy.types.Operator):
    bl_idname = "object.ksp_imported_clip_add"
    bl_label = "加入所选区间"
    bl_options = {'REGISTER', 'UNDO'}
    conflict: EnumProperty(name="冲突处理", items=(('CANCEL', "取消", "保留已有动画"),
                                                   ('REPLACE', "覆盖", "暂停冲突动画，保留原数据"),
                                                   ('BLEND', "融合", "NLA COMBINE，默认影响 1")), default='CANCEL')
    details: StringProperty(options={'HIDDEN'})
    report_name: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and not context.mode.startswith('EDIT')
                    and model_root(context.active_object))

    def invoke(self, context, event):
        root = model_root(context.active_object)
        if not root:
            self.report({'WARNING'}, "请选择导入模型或零件；旧模型请先迁移绑定")
            return {'CANCELLED'}
        try:
            _, clip = selected_clip(root)
            props = root.ksp_assets
            validate_range(clip, props.source_start, props.source_end)
            factor = context.scene.render.fps / context.scene.render.fps_base / clip.fps
            found = clip_conflicts(clip, props.insert_frame,
                                   props.insert_frame + (props.source_end - props.source_start) * factor)
            if found:
                lines = []
                for target, track, strip in found:
                    label = f"{strip.name} [{strip.frame_start:g}–{strip.frame_end:g}]" if strip else '活动 Action'
                    action = strip.action if strip else target.animation_data.action
                    channels = ', '.join(sorted({path for path, _ in curves(action)})[:2])
                    lines.append(f"{target.name} / {label} / {channels}")
                self.details = '\n'.join(lines)
                report = bpy.data.texts.new('KSP Animation Conflicts')
                report.write(self.details)
                self.report_name = report.name
                return context.window_manager.invoke_props_dialog(self, width=540)
            self.conflict = 'CANCEL'
            return self.execute(context)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def draw(self, context):
        self.layout.label(text="以下已有动画通道冲突：", icon='ERROR')
        lines = self.details.splitlines()
        for line in lines[:12]:
            self.layout.label(text=line)
        if len(lines) > 12:
            self.layout.label(text=f"另 {len(lines) - 12} 项；完整列表见文本 {self.report_name}")
        self.layout.prop(self, "conflict", expand=True)

    def execute(self, context):
        root = model_root(context.active_object)
        if not root:
            return {'CANCELLED'}
        try:
            _, group = add_clip(root, context, self.conflict)
            self.report({'INFO'}, f"已加入 {group.name}：{group.start:g}–{group.end:g}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class KSP_OT_ImportedClipRemove(bpy.types.Operator):
    bl_idname = "object.ksp_imported_clip_remove"
    bl_label = "移除播放片段"
    bl_options = {'REGISTER', 'UNDO'}
    group_uid: StringProperty()

    def execute(self, context):
        try:
            remove_scheduled(model_root(context.active_object), self.group_uid)
            context.view_layer.update()
            return {'FINISHED'}
        except (ValueError, AttributeError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class KSP_OT_ImportedClipLocate(bpy.types.Operator):
    bl_idname = "object.ksp_imported_clip_locate"
    bl_label = "选择片段并跳转起点"
    group_uid: StringProperty()

    def execute(self, context):
        root = model_root(context.active_object)
        group = next((g for g in root.ksp_assets.scheduled if g.uid == self.group_uid), None)
        if not group:
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        for entry in group.entries:
            target = binding_target(entry)
            ad = getattr(target, "animation_data", None)
            track, own_strip = resolve_playback(entry)
            if track:
                for strip in track.strips:
                    strip.select = strip == own_strip
            if isinstance(target, bpy.types.Object) and target.name in context.view_layer.objects:
                target.select_set(True)
        root.select_set(True)
        context.view_layer.objects.active = root
        context.scene.frame_set(math.floor(group.start), subframe=group.start % 1)
        return {'FINISHED'}


def data_objects(root):
    result = []
    def visit(obj, stack=()):
        result.append(obj)
        if obj.instance_type == 'COLLECTION' and obj.instance_collection:
            collection = obj.instance_collection
            if collection.as_pointer() not in stack:
                objects = set(collection.all_objects)
                for item in collection.all_objects:
                    if item.parent not in objects:
                        visit(item, stack + (collection.as_pointer(),))
        for child in obj.children:
            visit(child, stack)
    visit(root)
    return result


class KSP_OT_ImportedDataToggle(bpy.types.Operator):
    bl_idname = "object.ksp_imported_data_toggle"
    bl_label = "显示 / 隐藏辅助数据"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and not context.mode.startswith('EDIT')
                    and model_root(context.active_object))

    def execute(self, context):
        root = model_root(context.active_object)
        if not root:
            return {'CANCELLED'}
        objects = data_objects(root)
        if not 0 <= self.index < len(objects):
            return {'CANCELLED'}
        token = objects[self.index].get("ksp_data_token")
        occurrence = sum(o.get("ksp_data_token") == token for o in objects[:self.index])
        original = None
        snapshot = data_snapshot()
        try:
            root, original = ensure_realized(root, context)
            matches = [o for o in data_objects(root) if o.get("ksp_data_token") == token]
            obj = matches[occurrence]
            set_auxiliary_visibility(obj, not obj.get("ksp_aux_visible", False))
            if original:
                bpy.data.objects.remove(original, do_unlink=True)
            return {'FINISHED'}
        except Exception as exc:
            if original:
                for obj in reversed(list(walk_objects(root))):
                    bpy.data.objects.remove(obj, do_unlink=True)
                cleanup_new_data(snapshot)
                context.view_layer.objects.active = original
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class KSP_OT_ImportedClipCurrentFrame(bpy.types.Operator):
    bl_idname = "object.ksp_imported_clip_current_frame"
    bl_label = "使用当前帧"
    bl_options = {'UNDO'}

    def execute(self, context):
        root = model_root(context.active_object)
        root.ksp_assets.insert_frame = context.scene.frame_current_final
        return {'FINISHED'}


class KSP_OT_ImportedAssetsMigrate(bpy.types.Operator):
    bl_idname = "object.ksp_imported_assets_migrate"
    bl_label = "迁移旧动画绑定"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = model_root(context.active_object) or context.active_object
        if not root:
            return {'CANCELLED'}
        if collect_clips(root):
            self.report({'INFO'}, "已有可靠绑定，无需迁移")
            return {'CANCELLED'}
        from ..utils import original_ksp_name
        candidates = []
        for obj in data_objects(root):
            candidates.append(obj)
            if obj.type in {'LIGHT', 'CAMERA'}:
                candidates.append(obj.data)
            if obj.type == 'MESH':
                candidates.extend(mat for mat in obj.data.materials if mat)
        groups, skipped = {}, 0
        for action in bpy.data.actions:
            if not action.get("ksp_imported_action") or action.get("ksp_playback_uid"):
                continue
            name = action.get("ksp_target_object", "")
            matches = set(target for target in candidates if target.name == name)
            if not matches:
                # Aliases are accepted only if unique across the entire scene.
                global_matches = [obj for obj in bpy.data.objects
                                  if original_ksp_name(obj) == name]
                if len(global_matches) == 1 and global_matches[0] in candidates:
                    matches = {global_matches[0]}
            if len(matches) != 1:
                skipped += 1
                continue
            target = next(iter(matches))
            groups.setdefault(action.get("ksp_clip_name", action.name), []).append((action, target))
        if not groups:
            self.report({'WARNING'}, "没有可唯一绑定的旧动画，请重新导入模型")
            return {'CANCELLED'}
        root.ksp_assets.uid = uid()
        root["ksp_model_root"] = True
        fps = context.scene.render.fps / context.scene.render.fps_base
        for name, bindings in groups.items():
            clip = root.ksp_assets.clips.add()
            clip.uid, clip.name, clip.fps = uid(), name, fps
            clip.start = min(action.frame_range[0] for action, _ in bindings)
            clip.end = max(action.frame_range[1] for action, _ in bindings)
            for action, target in bindings:
                set_binding(clip.bindings.add(), target, action, target.name, capture_rest(target, action))
                action.use_fake_user = True
        root.ksp_assets.clip_choice = '0'
        self.report({'INFO'}, f"迁移 {len(groups)} 个片段；跳过 {skipped} 个不唯一或无关资源")
        return {'FINISHED'}


class KSP_OT_MaterialPreview(bpy.types.Operator):
    bl_idname = 'view3d.ksp_material_preview'
    bl_label = '查看贴图（材质预览）'
    bl_description = '仅切换当前 3D 视图的显示模式；实体模式不显示完整纹理，不改动画或场景渲染设置'

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        context.space_data.shading.type = 'MATERIAL'
        return {'FINISHED'}


class VIEW3D_PT_KSPImportedData(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "KSP"
    bl_label = "导入模型 / 零件"

    def draw(self, context):
        layout = self.layout
        layout.operator('view3d.ksp_material_preview', icon='SHADING_TEXTURE')
        row = layout.row(align=True)
        row.operator('material.ksp_preview_arrange', text='整理材质节点')
        row.operator('material.ksp_preview_simplify', text='精简当前材质')
        shading = getattr(context.space_data, 'shading', None)
        if shading and shading.type == 'SOLID':
            layout.label(text='实体模式不显示完整贴图', icon='INFO')
        root = model_root(context.active_object)
        if not root:
            layout.label(text="选择导入模型或零件的任意子对象")
            layout.operator("object.ksp_imported_assets_migrate")
            return
        props = root.ksp_assets
        layout.label(text=root.name, icon='OBJECT_DATA')
        layout.label(text="原始动画已保留，默认不接入时间线")
        clips = collect_clips(root)
        if clips:
            box = layout.box()
            box.prop(props, "clip_choice")
            try:
                _, clip = selected_clip(root)
                targets = {binding_target(b) for b in clip.bindings if binding_target(b)}
                counts = {kind: sum(isinstance(t, cls) for t in targets) for kind, cls in
                          (("对象", bpy.types.Object), ("材质", bpy.types.Material), ("灯光", bpy.types.Light))}
                bones = set((b.path, fc.data_path.split('].')[0]) for b in clip.bindings
                            for fc in iter_action_fcurves(b.action) if fc.data_path.startswith('pose.bones['))
                box.label(text=f"源 {clip.start:g}–{clip.end:g} 帧 / {(clip.end - clip.start) / clip.fps:g} 秒")
                box.label(text=" / ".join(f"{k} {v}" for k, v in counts.items()) + f" / 骨骼 {len(bones)}")
                if clip.issues:
                    box.label(text=f"未绑定 / 不支持通道：{len(clip.issues.splitlines())} 项", icon='ERROR')
                    box.prop(props, "show_issues")
                    if props.show_issues:
                        for issue in clip.issues.splitlines():
                            box.label(text=issue)
                row = box.row(align=True)
                row.prop(props, "source_start")
                row.prop(props, "source_end")
                row = box.row(align=True)
                row.prop(props, "insert_frame")
                row.operator("object.ksp_imported_clip_current_frame", text="当前帧")
                box.prop(props, "hold")
                box.operator("object.ksp_imported_clip_add", icon='NLA')
            except ValueError:
                box.label(text="请重新选择动画")
        else:
            layout.label(text="没有可选择的游戏动画")
            layout.operator("object.ksp_imported_assets_migrate")
        for group in props.scheduled:
            box = layout.box()
            box.label(text=f"{group.name}: {group.start:g}–{group.end:g}")
            if group.issue:
                box.label(text=group.issue, icon='ERROR')
            row = box.row(align=True)
            row.prop(group, "mute")
            row.prop(group, "hold")
            row = box.row(align=True)
            row.prop(group, "blend")
            row.prop(group, "influence")
            row = box.row(align=True)
            row.operator("object.ksp_imported_clip_locate", text="选择 / 定位").group_uid = group.uid
            row.operator("object.ksp_imported_clip_remove", text="移除").group_uid = group.uid


class VIEW3D_PT_KSPAuxiliaryData(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "KSP"
    bl_label = "骨架与辅助数据"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        root = model_root(context.active_object)
        if not root:
            self.layout.label(text="未选择导入模型")
            return
        objects = data_objects(root)
        self.layout.label(text=f"网格 {sum(o.type == 'MESH' for o in objects)} / 骨架 {sum(o.type == 'ARMATURE' for o in objects)}")
        for i, obj in enumerate(objects):
            if obj.get("ksp_auxiliary"):
                row = self.layout.row(align=True)
                row.label(text=f"{obj.get('ksp_auxiliary')}: {obj.name}")
                row.operator("object.ksp_imported_data_toggle", text="隐藏" if obj.get("ksp_aux_visible") else "显示").index = i
        self.layout.label(text="旧 Unity 碰撞体不导入；未自动添加物理")
        for name in sorted({o.get("ksp_import_report") for o in objects if o.get("ksp_import_report")}):
            self.layout.label(text="文本报告：" + name, icon='TEXT')


classes_to_register = (KSP_OT_ImportedClipAdd, KSP_OT_ImportedClipRemove,
                       KSP_OT_ImportedClipLocate, KSP_OT_ImportedDataToggle,
                       KSP_OT_ImportedClipCurrentFrame, KSP_OT_ImportedAssetsMigrate,
                       KSP_OT_MaterialPreview,
                       VIEW3D_PT_KSPImportedData, VIEW3D_PT_KSPAuxiliaryData)
