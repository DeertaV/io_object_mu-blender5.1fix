"""Blender 5.1 regression suite; real installed KSP samples plus synthetic clips."""
import os
import sys
from pathlib import Path
import importlib
import math
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()

from io_object_mu_blender51.import_mu import import_mu
from io_object_mu_blender51.utils.import_assets import collect_clips, binding_target, uid, set_binding, capture_rest
from io_object_mu_blender51.tools.imported_animation import add_clip, remove_scheduled, clip_conflicts
from io_object_mu_blender51.utils.blender_compat import ensure_action_fcurve

scene = bpy.context.scene
scene.frame_start, scene.frame_end = 10, 777
scene.render.fps, scene.render.fps_base = 30, 1.001
scene.frame_set(137)
timeline = (scene.frame_start, scene.frame_end, scene.frame_current,
            scene.render.fps, scene.render.fps_base)
gd = Path(os.environ.get('KSP_EXTRA_GAMEDATA', 'D:/Steam/steamapps/common/Kerbal Space Program/GameData'))
solar = gd / 'ReStock/Assets/Electrical/restock-solarpanel-1x6.mu'

collection = bpy.data.collections.new('source model')
scene.collection.children.link(collection)
root, mu = import_mu(collection, str(solar), False, False)
assert timeline == (scene.frame_start, scene.frame_end, scene.frame_current,
                    scene.render.fps, scene.render.fps_base)
assert collect_clips(root), 'Real solar panel must retain clips'
for _, clip in collect_clips(root):
    for b in clip.bindings:
        target = binding_target(b)
        ad = target.animation_data
        assert not ad or (ad.action is None and len(ad.nla_tracks) == 0)
        assert b.action.use_fake_user
assert all(o.muproperties.collider == 'MU_COL_NONE' for o in collection.all_objects)

# Rename every display name: pointers, not names, must drive activation.
for i, obj in enumerate(collection.all_objects):
    obj.name = f'中文对象 {i}'
root.ksp_assets.clip_choice = '0'
props = root.ksp_assets
clip = collect_clips(root)[0][1]
props.source_start = clip.start + (clip.end - clip.start) * 0.2
props.source_end = clip.start + (clip.end - clip.start) * 0.8
props.insert_frame = 200.5
bpy.context.view_layer.objects.active = root
root, group = add_clip(root, bpy.context)
assert len(group.entries) == len(clip.bindings)
for entry in group.entries:
    target = binding_target(entry)
    strip = target.animation_data.nla_tracks[entry.track].strips[entry.strip]
    assert abs(strip.frame_start - 200.5) < 0.001
    assert abs(strip.action_frame_start - props.source_start) < 0.001
    assert strip.extrapolation == 'HOLD_FORWARD'
assert timeline == (scene.frame_start, scene.frame_end, scene.frame_current,
                    scene.render.fps, scene.render.fps_base)
try:
    add_clip(root, bpy.context)
except ValueError:
    pass
else:
    raise AssertionError('Duplicate must be blocked')
group.mute = True
assert all(binding_target(e).animation_data.nla_tracks[e.track].strips[e.strip].mute for e in group.entries)
group.mute = False
group.hold = False
assert all(binding_target(e).animation_data.nla_tracks[e.track].strips[e.strip].extrapolation == 'NOTHING' for e in group.entries)
remove_scheduled(root, group.uid)
assert not props.scheduled

# Two collection instances of the same model: realize only the selected part.
def instance(name):
    obj = bpy.data.objects.new(name, None)
    scene.collection.objects.link(obj)
    obj.instance_type = 'COLLECTION'
    obj.instance_collection = collection
    obj['ksp_part_root'] = True
    obj.ksp_assets.uid = uid()
    obj.ksp_assets.clip_choice = '0'
    return obj

a, b = instance('part A'), instance('part B')
a.location = (3, 4, 5)
matrix = a.matrix_world.copy()
a.ksp_assets.insert_frame = 300
bpy.context.view_layer.objects.active = a
a, scheduled = add_clip(a, bpy.context)
assert a.instance_type == 'NONE'
assert b.instance_type == 'COLLECTION'
assert all(abs(a.matrix_world[i][j] - matrix[i][j]) < 1e-5 for i in range(4) for j in range(4))
for e in scheduled.entries:
    assert binding_target(e) not in {binding_target(src) for _, c in collect_clips(b) for src in c.bindings}
remove_scheduled(a, scheduled.uid)

# Synthetic active Action conflicts, replace/restore and blend/restore.
obj = bpy.data.objects.new('conflict target', None)
scene.collection.objects.link(obj)
obj['ksp_model_root'] = True
obj.ksp_assets.uid = uid()
source = bpy.data.actions.new('source')
fc = ensure_action_fcurve(source, obj, 'location', 0)
fc.keyframe_points.insert(1, 0)
fc.keyframe_points.insert(31, 2)
obj.animation_data.action = None
source.use_fake_user = True
c = obj.ksp_assets.clips.add()
c.uid, c.name, c.start, c.end, c.fps = uid(), 'clip', 1, 31, 30 / 1.001
set_binding(c.bindings.add(), obj, source, 'root')
obj.ksp_assets.clip_choice = '0'
obj.ksp_assets.insert_frame = 400
manual = bpy.data.actions.new('user authored')
fc = ensure_action_fcurve(manual, obj, 'location', 0)
fc.keyframe_points.insert(1, 4)
fc.keyframe_points.insert(1000, 4)
assert clip_conflicts(c, 400, 430)
try:
    add_clip(obj, bpy.context)
except ValueError:
    pass
else:
    raise AssertionError('Conflict must require explicit choice')
obj, g = add_clip(obj, bpy.context, 'REPLACE')
assert obj.animation_data.action is None
remove_scheduled(obj, g.uid)
assert obj.animation_data.action == manual

# Mixed object/material/light clip is synchronized and copied per instance.
mixed_collection = bpy.data.collections.new('mixed source')
scene.collection.children.link(mixed_collection)
mixed_root = bpy.data.objects.new('mixed root', None)
mixed_collection.objects.link(mixed_root)
mixed_root['ksp_model_root'] = True
mixed_root.ksp_assets.uid = uid()
mesh = bpy.data.meshes.new('mixed mesh')
mesh.from_pydata([(0,0,0), (1,0,0), (0,1,0)], [], [(0,1,2)])
mesh_obj = bpy.data.objects.new('mixed mesh', mesh)
mixed_collection.objects.link(mesh_obj)
mesh_obj.parent = mixed_root
mat = bpy.data.materials.new('mixed material')
mesh.materials.append(mat)
prop = mat.mumatprop.float2.properties.add()
prop.name, prop.value = '_Shininess', 0.2
light = bpy.data.lights.new('mixed light', 'POINT')
light_obj = bpy.data.objects.new('mixed light', light)
mixed_collection.objects.link(light_obj)
light_obj.parent = mixed_root
light.energy = 100
c = mixed_root.ksp_assets.clips.add()
c.uid, c.name, c.start, c.end, c.fps = uid(), 'all targets', 1, 31, 30 / 1.001
for target, path, start_value, end_value in ((mesh_obj, 'location', 0, 2),
                                            (light, 'energy', 100, 200),
                                            (mat, 'mumatprop.float2.properties[0].value', 0.2, 0.8)):
    action = bpy.data.actions.new('mixed source action')
    fc = ensure_action_fcurve(action, target, path, 0)
    fc.keyframe_points.insert(1, start_value)
    fc.keyframe_points.insert(31, end_value)
    target.animation_data.action = None
    action.use_fake_user = True
    set_binding(c.bindings.add(), target, action, path, capture_rest(target, action))
mixed = bpy.data.objects.new('mixed part', None)
scene.collection.objects.link(mixed)
mixed.instance_type = 'COLLECTION'
mixed.instance_collection = mixed_collection
mixed['ksp_part_root'] = True
mixed.ksp_assets.uid = uid()
mixed.ksp_assets.clip_choice = '0'
mixed.ksp_assets.insert_frame = 500
bpy.context.view_layer.objects.active = mixed
mixed, mixed_group = add_clip(mixed, bpy.context)
assert len(mixed_group.entries) == 3
scene.frame_set(int(mixed_group.end + 5))
for entry in mixed_group.entries:
    target = binding_target(entry)
    if entry.light:
        assert abs(target.energy - 200) < 0.001
        assert target != light and light.energy == 100
    if entry.material:
        assert abs(target.mumatprop.float2.properties[0].value - 0.8) < 0.001
        assert target != mat and abs(mat.mumatprop.float2.properties[0].value - 0.2) < 0.001
saved_mixed_name = mixed.name
saved_group_uid = mixed_group.uid
obj, g = add_clip(obj, bpy.context, 'BLEND')
assert obj.animation_data.action is None
assert g.blend == 'COMBINE'
# Live mode switches must expose/pause the original user animation correctly.
scene.frame_set(int(g.end + 5))
expected = g.entries[0].action
from io_object_mu_blender51.utils.blender_compat import iter_action_fcurves
value = next(fc for fc in iter_action_fcurves(expected) if fc.data_path == 'location' and fc.array_index == 0).evaluate(g.source_end)
assert abs(obj.location.x - (4 + value)) < 0.001, (obj.location.x, value)
g.blend = 'REPLACE'
scene.frame_set(int(g.end + 6))
assert abs(obj.location.x - value) < 0.001
g.mute = True
scene.frame_set(int(g.end + 7))
assert abs(obj.location.x - 4) < 0.001
g.mute = False
g.blend = 'COMBINE'
scene.frame_set(int(g.end + 8))
assert abs(obj.location.x - (4 + value)) < 0.001
remove_scheduled(obj, g.uid)
assert obj.animation_data.action == manual

# Saved source bindings survive a .blend reopen.
saved_name = obj.name
path = str(Path(__file__).resolve().parent / 'animation-regression.blend')
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
obj = bpy.data.objects[saved_name]
assert obj.ksp_assets.clips[0].bindings[0].object == obj
assert obj.ksp_assets.clips[0].bindings[0].action.use_fake_user
mixed = bpy.data.objects[saved_mixed_name]
assert mixed.ksp_assets.scheduled[0].uid == saved_group_uid
remove_scheduled(mixed, saved_group_uid)
assert not mixed.ksp_assets.scheduled and not mixed.ksp_assets.baselines
print('IMPORTED_ANIMATION_TEST_PASS')
