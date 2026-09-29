"""UI operators, duplicate track names, failure rollback, migration and undo."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.utils.import_assets import (uid, set_binding, capture_rest,
                                                       binding_target, data_snapshot)
from io_object_mu_blender51.utils.blender_compat import ensure_action_fcurve
from io_object_mu_blender51.tools import imported_animation as module

scene = bpy.context.scene
scene.frame_set(30)
root = bpy.data.objects.new('operator root', None)
scene.collection.objects.link(root)
root['ksp_model_root'] = True
root.ksp_assets.uid = uid()
action = bpy.data.actions.new('operator source')
fc = ensure_action_fcurve(action, root, 'location', 0)
fc.keyframe_points.insert(1, 0)
fc.keyframe_points.insert(25, 2)
root.animation_data.action = None
action.use_fake_user = True
clip = root.ksp_assets.clips.add()
clip.uid, clip.name, clip.start, clip.end, clip.fps = uid(), 'deploy', 1, 25, 24
set_binding(clip.bindings.add(), root, action, 'root', capture_rest(root, action))
root.ksp_assets.clip_choice = '0'
root.ksp_assets.insert_frame = 50
bpy.context.view_layer.objects.active = root
root.select_set(True)

# A failed expansion must leave neither cloned objects nor fake-user source copies.
source_collection = bpy.data.collections.new('rollback source')
scene.collection.children.link(source_collection)
source_collection.objects.link(root)
instance = bpy.data.objects.new('rollback part', None)
scene.collection.objects.link(instance)
instance.instance_type = 'COLLECTION'
instance.instance_collection = source_collection
instance['ksp_part_root'] = True
instance.ksp_assets.uid = uid()
instance.ksp_assets.clip_choice = '0'
before_objects = {o.as_pointer() for o in bpy.data.objects}
before_data = data_snapshot()
with patch.object(module, 'assign_slot', side_effect=RuntimeError('injected staging failure')):
    try:
        module.add_clip(instance, bpy.context)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Injected error was not raised')
assert before_objects == {o.as_pointer() for o in bpy.data.objects}
assert before_data == data_snapshot()
assert instance.instance_type == 'COLLECTION'
bpy.context.view_layer.objects.active = root

# Failed active-Action preservation must restore it and remove staging tracks.
manual = bpy.data.actions.new('rollback active action')
fc = ensure_action_fcurve(manual, root, 'location', 0)
fc.keyframe_points.insert(1, 4)
fc.keyframe_points.insert(1000, 4)
before_data = data_snapshot()
with patch.object(module, 'assign_slot', side_effect=RuntimeError('injected preserve failure')):
    try:
        module.add_clip(root, bpy.context, 'REPLACE')
    except RuntimeError:
        pass
    else:
        raise AssertionError('Injected preserve error was not raised')
assert root.animation_data.action == manual
assert not root.animation_data.nla_tracks and not root.ksp_assets.scheduled
assert before_data == data_snapshot()
root.animation_data.action = None

# UI invoke builds a conflict dialog rather than silently changing old animation.
root, group = module.add_clip(root, bpy.context)
root.ksp_assets.insert_frame = 55
class Stub:
    details = ''
    report_name = ''
    conflict = 'CANCEL'
    def report(self, *args): pass
stub = Stub()
context = SimpleNamespace(active_object=root, scene=scene,
                          window_manager=SimpleNamespace(invoke_props_dialog=lambda *args, **kwargs: {'RUNNING_MODAL'}))
assert module.KSP_OT_ImportedClipAdd.invoke(stub, context, None) == {'RUNNING_MODAL'}
assert 'operator root' in stub.details and stub.report_name in bpy.data.texts
assert len(root.ksp_assets.scheduled) == 1

# Rename NLA tracks and strips: resolve by Action pointers, not display names.
entry = group.entries[0]
track = root.animation_data.nla_tracks[entry.track]
strip = track.strips[entry.strip]
track.name, strip.name = 'renamed user track', 'renamed user strip'
group.mute = True
assert strip.mute and not group.issue
group.mute = False
assert not strip.mute

# Removing a plugin strip must not delete user strips appended to that track.
user = bpy.data.actions.new('keep user strip')
fc = ensure_action_fcurve(user, root, 'location', 1)
fc.keyframe_points.insert(1, 3)
fc.keyframe_points.insert(25, 3)
root.animation_data.action = None
extra = track.strips.new('user strip', 200, user)
module.assign_slot(extra, user)
module.remove_scheduled(root, group.uid)
assert root.animation_data.nla_tracks['renamed user track'].strips['user strip'].action == user

# Nested covers can be removed in either order without orphaning playback
# Actions or prematurely restoring the original active user Action.
for oldest_first in (True, False):
    root.animation_data.action = manual
    root.ksp_assets.insert_frame = 50
    root, first = module.add_clip(root, bpy.context, 'REPLACE')
    first_uid = first.uid
    root.ksp_assets.insert_frame = 55
    root, second = module.add_clip(root, bpy.context, 'REPLACE')
    second_uid = second.uid
    module.remove_scheduled(root, first_uid if oldest_first else second_uid)
    assert root.animation_data.action is None
    assert len(root.ksp_assets.scheduled) == 1 and not root.ksp_assets.scheduled[0].issue
    scene.frame_set(100)
    assert abs(root.location.x - 2) < 0.001
    module.remove_scheduled(root, second_uid if oldest_first else first_uid)
    assert root.animation_data.action == manual
    assert not any(a.get('ksp_playback_uid') for a in bpy.data.actions)
root.animation_data.action = None

# Old records are accepted only for an unambiguous target.
legacy = bpy.data.objects.new('legacy unique', None)
scene.collection.objects.link(legacy)
old = bpy.data.actions.new('legacy action')
fc = ensure_action_fcurve(old, legacy, 'location', 0)
fc.keyframe_points.insert(1, 0)
fc.keyframe_points.insert(25, 2)
legacy.animation_data.action = None
old['ksp_imported_action'], old['ksp_target_object'], old['ksp_clip_name'] = True, legacy.name, 'old deploy'
bpy.context.view_layer.objects.active = legacy
assert bpy.ops.object.ksp_imported_assets_migrate() == {'FINISHED'}
assert legacy.ksp_assets.clips[0].bindings[0].object == legacy
for name in ('ambiguous A', 'ambiguous B'):
    obj = bpy.data.objects.new(name, None)
    scene.collection.objects.link(obj)
    obj['ksp_original_name'] = 'ambiguous alias'
old = bpy.data.actions.new('ambiguous old action')
old['ksp_imported_action'], old['ksp_target_object'] = True, 'ambiguous alias'
bpy.context.view_layer.objects.active = bpy.data.objects['ambiguous A']
assert bpy.ops.object.ksp_imported_assets_migrate() == {'CANCELLED'}

# Undo/redo integration with an explicitly bracketed headless undo history.
bpy.context.view_layer.objects.active = root
root.ksp_assets.insert_frame = 300
bpy.context.preferences.edit.use_global_undo = True
bpy.context.view_layer.update()
bpy.ops.ed.undo_push(message='before KSP add')
assert bpy.ops.object.ksp_imported_clip_add('EXEC_DEFAULT') == {'FINISHED'}
bpy.ops.ed.undo_push(message='after KSP add')
assert bpy.ops.ed.undo() == {'FINISHED'}
root = bpy.data.objects['operator root']
assert len(root.ksp_assets.scheduled) == 0
assert bpy.ops.ed.redo() == {'FINISHED'}
root = bpy.data.objects['operator root']
assert len(root.ksp_assets.scheduled) == 1

# Direct .mu operator owns a fresh collection and an unanimated cursor anchor.
from io_object_mu_blender51.utils.import_assets import collect_clips, walk_objects
scene = bpy.context.scene
scene.cursor.location = (12, -7, 3)
scene.frame_set(177)
scene.render.fps, scene.render.fps_base = 30, 1.001
timeline = (scene.frame_current_final, scene.frame_start, scene.frame_end,
            scene.render.fps, scene.render.fps_base)
old_names = {c.as_pointer(): c.name for c in bpy.data.collections}
sample = str(Path(os.environ.get('KSP_EXTRA_GAMEDATA', 'D:/Steam/steamapps/common/Kerbal Space Program/GameData')) / 'ReStock/Assets/Electrical/restock-solarpanel-1x6.mu')
assert bpy.ops.import_object.ksp_mu(filepath=sample) == {'FINISHED'}
anchor = bpy.context.active_object
assert anchor.get('ksp_original_name') == 'ksp_import_anchor'
assert tuple(anchor.location) == (12, -7, 3)
assert anchor.animation_data is None and collect_clips(anchor)
assert timeline == (scene.frame_current_final, scene.frame_start, scene.frame_end,
                    scene.render.fps, scene.render.fps_base)
for c in bpy.data.collections:
    if c.as_pointer() in old_names:
        assert c.name == old_names[c.as_pointer()]
for obj in walk_objects(anchor):
    assert not obj.animation_data or (not obj.animation_data.action and not obj.animation_data.nla_tracks)
print('OPERATOR_LIFECYCLE_TEST_PASS')
