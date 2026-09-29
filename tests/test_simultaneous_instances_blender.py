"""UI-selected instance ownership, simultaneous playback and local conflicts."""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.utils.import_assets import (uid, model_root, collect_clips,
    binding_target, set_binding, capture_rest, resolve_playback)
from io_object_mu_blender51.utils.blender_compat import ensure_action_fcurve
from io_object_mu_blender51.tools import imported_animation as animation

scene = bpy.context.scene
scene.frame_set(113)
scene.render.fps, scene.render.fps_base = 30, 1.001
initial_timing = (scene.frame_current, scene.frame_start, scene.frame_end,
                  scene.render.fps, scene.render.fps_base)


def fixture(name, kind='ANCHOR', parent=None):
    owner = bpy.data.objects.new(name, None)
    scene.collection.objects.link(owner)
    owner.parent = parent
    owner.ksp_assets.uid = uid()
    owner['ksp_model_root'] = True
    if kind == 'PART':
        owner['ksp_part_root'] = True
    elif kind == 'ANCHOR':
        # Existing 0.11.x direct-import anchors already have this stable marker.
        owner['ksp_original_name'] = 'ksp_import_anchor'
    if kind == 'RAW':
        source_root = owner
    else:
        source_root = bpy.data.objects.new(name + ' source', None)
        scene.collection.objects.link(source_root)
        source_root.parent = owner
        source_root['ksp_model_root'] = True
        source_root.ksp_assets.uid = uid()
    target = bpy.data.objects.new(name + ' rotating child', None)
    scene.collection.objects.link(target)
    target.parent = source_root
    helper = bpy.data.objects.new(name + ' helper', None)
    scene.collection.objects.link(helper)
    helper.parent = target
    lamp = bpy.data.lights.new(name + ' light data', 'POINT')
    light = bpy.data.objects.new(name + ' light', lamp)
    scene.collection.objects.link(light)
    light.parent = source_root
    material = bpy.data.materials.new(name + ' material')
    armature = bpy.data.armatures.new(name + ' rig data')
    rig = bpy.data.objects.new(name + ' rig', armature)
    scene.collection.objects.link(rig)
    rig.parent = source_root
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bone = armature.edit_bones.new('shared game bone name')
    bone.head, bone.tail = (0,0,0), (0,0,1)
    bpy.ops.object.mode_set(mode='OBJECT')
    clip = source_root.ksp_assets.clips.add()
    # Same clip identity/name intentionally reused by instances of one source.
    clip.uid, clip.name, clip.start, clip.end, clip.fps = 'shared-clip-uid', 'Deploy', 1, 31, 30 / 1.001
    channels = [(target, 'location', 0, 0, 2),
                (lamp, 'energy', 0, 1, 3),
                (material, 'diffuse_color', 0, .1, .9),
                (rig, 'pose.bones["shared game bone name"].location', 0, 0, 1)]
    for data, path, index, first, last in channels:
        action = bpy.data.actions.new(name + ' source action')
        action.use_fake_user = True
        fc = ensure_action_fcurve(action, data, path, index)
        for frame, value in [(1,first), (31,last)]:
            fc.keyframe_points.insert(frame, value).interpolation = 'LINEAR'
        data.animation_data.action = None
        set_binding(clip.bindings.add(), data, action, path, capture_rest(data, action))
    owner.ksp_assets.clip_choice = '0'
    owner.ksp_assets.insert_frame = 200
    return owner, target, helper, rig, light, material


# A new direct .mu attached beneath an already animated model is still its own
# instance. Old model_root() incorrectly returned the highest imported ancestor.
a = fixture('direct A')
b = fixture('direct B', parent=a[0])
for node in (b[0], b[1], b[2], b[3], b[4]):
    assert model_root(node) == b[0], 'Selecting B must not resolve to A'
assert len(collect_clips(a[0])) == 1, 'A must not list the separately imported B clips'
assert len(collect_clips(b[0])) == 1


def invoke_add(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    # Exercise the same invoke path as the panel, not just add_clip(root,...).
    class Stub:
        conflict = 'CANCEL'
        details = ''
        report_name = ''
        def report(self, kinds, message):
            if 'ERROR' in kinds or 'WARNING' in kinds:
                raise AssertionError(message)
        def execute(self, context):
            return animation.KSP_OT_ImportedClipAdd.execute(self, context)
    dialogs = []
    context = SimpleNamespace(active_object=obj, scene=scene,
        view_layer=bpy.context.view_layer,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *args, **kw: dialogs.append(True) or {'RUNNING_MODAL'}))
    result = animation.KSP_OT_ImportedClipAdd.invoke(Stub(), context, None)
    assert result == {'FINISHED'} and not dialogs, 'Independent instance must add without a conflict dialog'


invoke_add(a[1])
invoke_add(b[3])
assert len(a[0].ksp_assets.scheduled) == len(b[0].ksp_assets.scheduled) == 1
ag, bg = a[0].ksp_assets.scheduled[0], b[0].ksp_assets.scheduled[0]
assert ag.uid != bg.uid and ag.source_key == bg.source_key
assert not {binding_target(e) for e in ag.entries} & {binding_target(e) for e in bg.entries}
for group in (ag,bg):
    assert not group.overrides
    assert all(resolve_playback(e)[1] and not resolve_playback(e)[1].mute for e in group.entries)
scene.frame_set(215)
assert abs(a[1].location.x - 1) < .002 and abs(b[1].location.x - 1) < .002
assert abs(a[4].data.energy - 2) < .002 and abs(b[4].data.energy - 2) < .002
assert abs(a[5].diffuse_color[0] - .5) < .002 and abs(b[5].diffuse_color[0] - .5) < .002
assert abs(a[3].pose.bones[0].location.x - .5) < .002
assert abs(b[3].pose.bones[0].location.x - .5) < .002
ag.mute = True
assert not any(resolve_playback(e)[1].mute for e in bg.entries)
ag.mute = False

# Exact duplicate remains blocked only on the same owner.
try:
    animation.add_clip(b[0], bpy.context)
except ValueError as exc:
    assert '已存在' in str(exc)
else:
    raise AssertionError('Same-instance duplicate must still be rejected')
duplicate_reports, duplicate_dialogs = [], []
stub = SimpleNamespace(conflict='CANCEL',
    report=lambda kinds, message: duplicate_reports.append(message))
context = SimpleNamespace(active_object=b[1], scene=scene,
    window_manager=SimpleNamespace(invoke_props_dialog=lambda *args, **kw: duplicate_dialogs.append(True)))
assert animation.KSP_OT_ImportedClipAdd.invoke(stub, context, None) == {'CANCELLED'}
assert not duplicate_dialogs and any('当前零件' in r and '已存在' in r for r in duplicate_reports)
b[0].ksp_assets.insert_frame = 205
assert animation.clip_conflicts(collect_clips(b[0])[0][1], 205, 235)
try:
    animation.add_clip(b[0], bpy.context)
except ValueError as exc:
    assert '冲突' in str(exc)
else:
    raise AssertionError('Real overlap on B must still require explicit choice')
assert len(a[0].ksp_assets.scheduled) == 1

# Raw import callers without a placement anchor also use their nearest model.
c = fixture('raw C', 'RAW')
d = fixture('raw D', 'RAW', parent=c[0])
assert model_root(d[1]) == d[0] and len(collect_clips(c[0])) == 1
invoke_add(c[2])
invoke_add(d[4])

# Parent/child craft parts remain separate even though each contains .mu roots.
e = fixture('part E', 'PART')
f = fixture('part F', 'PART', parent=e[0])
assert model_root(e[3]) == e[0] and model_root(f[2]) == f[0]
assert len(collect_clips(e[0])) == len(collect_clips(f[0])) == 1
invoke_add(e[3])
invoke_add(f[1])

# Removing A cannot remove or mute B, including after serialization.
animation.remove_scheduled(a[0], ag.uid)
assert len(b[0].ksp_assets.scheduled) == 1
for item in (a,b,c,d,e,f):
    item[0].name = '中文整理_' + item[0].name
out = Path(__file__).resolve().parent / 'artifacts' / 'simultaneous-instances.blend'
out.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out))
bpy.ops.wm.open_mainfile(filepath=str(out))
b_root = bpy.data.objects['中文整理_direct B']
b_child = bpy.data.objects['direct B rotating child']
assert model_root(b_child) == b_root and len(b_root.ksp_assets.scheduled) == 1
assert all(resolve_playback(e)[1] for e in b_root.ksp_assets.scheduled[0].entries)
scene = bpy.context.scene
scene.frame_set(113)
assert initial_timing == (scene.frame_current, scene.frame_start, scene.frame_end,
                           scene.render.fps, scene.render.fps_base)
print('SIMULTANEOUS_INSTANCE_TEST_PASS')
