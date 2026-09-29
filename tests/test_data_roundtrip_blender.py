"""Real solar/leg/skinned drill/light/chute imports, geometry and source-clip export."""
import os
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.import_mu import import_mu
from io_object_mu_blender51.utils.import_assets import collect_clips, binding_target
from io_object_mu_blender51.tools.imported_animation import add_clip, remove_scheduled, validate_range
from io_object_mu_blender51.export_mu.export import export_object
from io_object_mu_blender51.import_mu.mesh import create_mesh, attach_material
from io_object_mu_blender51.export_mu.mesh import build_submeshes
from io_object_mu_blender51.mu import MuMesh, MuRenderer
from types import SimpleNamespace

gd = Path(os.environ.get('KSP_EXTRA_GAMEDATA', 'D:/Steam/steamapps/common/Kerbal Space Program/GameData'))
assets = Path(__file__).resolve().parent / 'artifacts'
assets.mkdir(exist_ok=True)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 10, 800
scene.frame_set(123)
samples = ['ReStock/Assets/Electrical/restock-solarpanel-1x6.mu',
           'ReStock/Assets/Ground/restock-leg-1.mu',
           'ReStock/Assets/Resource/restock-drill-radial-1.mu',
           'ReStock/Assets/Electrical/restock-light-deploy-1.mu',
           'ReStock/Assets/Utility/restock-parachute-125-1.mu',
           'KerbalReusabilityExpansion/AeroLandingLegs/AeroLandingLeg.mu']

for index, relative in enumerate(samples):
    collection = bpy.data.collections.new('sample ' + str(index))
    scene.collection.children.link(collection)
    root, mu = import_mu(collection, str(gd / relative), False, False)
    assert scene.frame_current == 123 and scene.frame_start == 10 and scene.frame_end == 800
    objects = list(collection.all_objects)
    assert all(o.muproperties.collider == 'MU_COL_NONE' for o in objects)
    bpy.context.view_layer.update()
    matrices = {o: o.matrix_basis.copy() for o in objects}
    for frame in (1, 30, 500):
        scene.frame_set(frame)
        for obj, matrix in matrices.items():
            assert all(abs(obj.matrix_basis[i][j] - matrix[i][j]) < 1e-5
                       for i in range(4) for j in range(4)), obj.name
    scene.frame_set(123)
    clip_list = collect_clips(root)
    if 'light-deploy' not in relative:
        assert clip_list, relative
    for ci, (_, clip) in enumerate(clip_list):
        for binding in clip.bindings:
            target = binding_target(binding)
            assert not target.animation_data.action
            assert not target.animation_data.nla_tracks
        if clip.bindings and clip.end > clip.start:
            validate_range(clip, clip.start, clip.end)
            from io_object_mu_blender51.utils.blender_compat import iter_action_fcurves
            rest = []
            for binding in clip.bindings:
                target = binding_target(binding)
                for fc in iter_action_fcurves(binding.action):
                    value = target.path_resolve(fc.data_path)
                    value = value[fc.array_index] if hasattr(value, '__len__') else value
                    rest.append((target, fc.data_path, fc.array_index, value))
            root.ksp_assets.clip_choice = str(ci)
            root.ksp_assets.insert_frame = 200
            bpy.context.view_layer.objects.active = root
            root, group = add_clip(root, bpy.context)
            for frame, source_frame in ((group.start, clip.start), (group.end + 2, clip.end)):
                scene.frame_set(int(frame), subframe=frame % 1)
                from io_object_mu_blender51.utils.blender_compat import iter_action_fcurves
                for entry in group.entries:
                    target = binding_target(entry)
                    for fc in iter_action_fcurves(entry.action):
                        if fc.data_path in {'hide_render', 'hide_viewport'}:
                            continue
                        value = target.path_resolve(fc.data_path)
                        actual = value[fc.array_index] if hasattr(value, '__len__') else value
                        expected = fc.evaluate(source_frame)
                        assert abs(actual - expected) < 0.002, (relative, target.name, fc.data_path, actual, expected)
            group.hold = False
            scene.frame_set(int(group.end + 4))
            for target, path, channel, expected in rest:
                value = target.path_resolve(path)
                value = value[channel] if hasattr(value, '__len__') else value
                assert abs(value - expected) < 0.002, ('not restoring outside strip', relative, path, value, expected)
            remove_scheduled(root, group.uid)
            scene.frame_set(123)
            for target, path, channel, expected in rest:
                value = target.path_resolve(path)
                value = value[channel] if hasattr(value, '__len__') else value
                assert abs(value - expected) < 0.002, ('remove did not restore', relative, path, value, expected)
    meshes = [o for o in objects if o.type == 'MESH']
    assert meshes
    for obj in meshes:
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE':
                assert modifier.object and len(modifier.object.data.bones)
                assert obj.vertex_groups
    output = assets / f'sample-{index}.mu'
    exported = export_object(root, str(output))
    restored_collection = bpy.data.collections.new('roundtrip ' + str(index))
    scene.collection.children.link(restored_collection)
    restored, restored_mu = import_mu(restored_collection, str(output), False, False)
    if clip_list:
        assert collect_clips(restored), 'Unbound source clips must survive export'
    assert sorted(c.name for _, c in collect_clips(restored)) == sorted(c.name for _, c in clip_list)
    print('REAL_SAMPLE_PASS', relative, 'clips', len(clip_list), 'meshes', len(meshes),
          'bones', sum(len(o.data.bones) for o in objects if o.type == 'ARMATURE'))

# Synthetic multi-material, colors and tangent retention.
mumesh = MuMesh()
mumesh.verts = [(0,0,0), (1,0,0), (0,1,0), (1,1,0)]
mumesh.submeshes = [[(0,1,2)], [(1,3,2)]]
mumesh.colors = [(1,0,0,1), (0,1,0,1), (0,0,1,1), (1,1,1,1)]
mumesh.tangents = [(1,0,0,1)] * 4
fake = SimpleNamespace(data_issues=[], materials=[SimpleNamespace(material=bpy.data.materials.new('red')),
                                                 SimpleNamespace(material=bpy.data.materials.new('blue'))])
mesh = create_mesh(fake, mumesh, 'multimaterial')
renderer = MuRenderer()
renderer.materials = [0,1]
attach_material(mesh, renderer, fake)
assert [p.material_index for p in mesh.polygons] == [0,1]
assert len(mesh.materials) == 2
assert mesh.attributes.get('ksp_source_tangent')
assert mesh.color_attributes.get('KSP Vertex Color')
mesh.calc_loop_triangles()
assert build_submeshes(mesh) == [[0], [1]]
for material in mesh.materials:
    material.mumatprop.shaderName = 'KSP/Diffuse'
obj = bpy.data.objects.new('multimaterial', mesh)
scene.collection.objects.link(obj)
exported = export_object(obj, str(assets / 'multimaterial.mu'))
def mesh_nodes(node):
    if hasattr(node, 'shared_mesh') or hasattr(node, 'mesh'):
        yield node
    for child in node.children:
        yield from mesh_nodes(child)
nodes = list(mesh_nodes(exported.obj))
assert len(nodes) == 1, (vars(exported.obj), exported.messages)
exported_mesh = getattr(nodes[0], 'shared_mesh', None) or nodes[0].mesh
assert len(exported_mesh.submeshes) == 2
assert len(nodes[0].renderer.materials) == 2
assert exported_mesh.colors
print('MODEL_DATA_ROUNDTRIP_PASS')
