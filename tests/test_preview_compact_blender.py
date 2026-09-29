"""Minimal graphs, real pod/emission/normal groups, backups and failed rebuilds."""
import os
import sys, json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.shader.shader import make_shader, ensure_principled_preview
from io_object_mu_blender51.shader import operators
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.tools.imported_animation import data_objects
from io_object_mu_blender51.mu import MuMaterial, MuMatTex
from io_object_mu_blender51.utils.import_assets import set_binding
from io_object_mu_blender51.utils.blender_compat import ensure_action_fcurve

image = bpy.data.images.new('preview fixture', 4, 4)
image.pixels[:] = [1, .3, .2, 1] * 16
source = MuMaterial()
source.name, source.shaderName = 'Simple diffuse', 'KSP/Diffuse'
tex = MuMatTex()
tex.index, tex.scale, tex.offset = 0, (1, 1), (0, 0)
source.textureProperties['_MainTex'] = tex
mu = SimpleNamespace(textures=[SimpleNamespace(name=image.name, type=0, blender_image_name=image.name)], data_issues=[])
simple = make_shader(source, mu)
assert len(simple.node_tree.nodes) == 3
assert {n.type for n in simple.node_tree.nodes} == {'TEX_IMAGE', 'BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'}

source.colorProperties['_Color'] = (1, 1, 1, 1)
source.colorProperties['_EmissiveColor'] = (0, 0, 0, 1)
source.shaderName = 'KSP/Emissive/Specular'
source.textureProperties['_Emissive'] = tex
source.textureProperties['_BumpMap'] = tex
image.muimageprop.convertNorm = True
full = make_shader(source, mu)
assert len(full.node_tree.nodes) <= 9, len(full.node_tree.nodes)
assert full.node_tree.nodes.get('KSP 法线转换')
assert full.node_tree.nodes.get('KSP 颜色与透明')
assert not any(n.type in {'MATH', 'MIX_RGB', 'RGB', 'VALUE'} for n in full.node_tree.nodes)
for node in full.node_tree.nodes:
    if node.type == 'GROUP':
        assert not node.node_tree.animation_data, 'Shared groups must not refer to a Material ID'
driver_count = len(full.node_tree.animation_data.drivers)
ensure_principled_preview(full)
assert len(full.node_tree.animation_data.drivers) == driver_count, 'Rebuild must not accumulate dangling drivers'

def shape(mat):
    return [(n.name, n.type, tuple(n.location), n.width) for n in mat.node_tree.nodes]

cube = bpy.context.active_object
cube.data.materials.clear()
cube.data.materials.append(full)
user = full.node_tree.nodes.new('ShaderNodeValue')
user.name, user.outputs[0].default_value = 'User handmade node', .37
root = bpy.data.objects.new('binding owner', None)
bpy.context.scene.collection.objects.link(root)
action = bpy.data.actions.new('source material action')
action.use_fake_user = True
fc = ensure_action_fcurve(action, full, 'mumatprop.color.properties[0].value', 0)
fc.keyframe_points.insert(1, .2)
fc.keyframe_points.insert(25, .8)
full.animation_data_create().action = action
clip = root.ksp_assets.clips.add()
binding = clip.bindings.add()
set_binding(binding, full, action, 'material')
profile = (bpy.context.scene.frame_current, bpy.context.scene.frame_start,
           bpy.context.scene.frame_end, bpy.context.scene.render.fps)
before = shape(full)
links = {(l.from_socket.path_from_id(), l.to_socket.path_from_id()) for l in full.node_tree.links}
assert bpy.ops.material.ksp_preview_arrange() == {'FINISHED'}
assert links == {(l.from_socket.path_from_id(), l.to_socket.path_from_id()) for l in full.node_tree.links}
assert full.node_tree.nodes['User handmade node'].outputs[0].default_value == user.outputs[0].default_value

before = shape(full)
materials = set(bpy.data.materials)
with patch.object(operators, 'ensure_principled_preview', side_effect=RuntimeError('injected build failure')):
    assert operators.KSPMU_OT_PreviewSimplify.execute(SimpleNamespace(report=lambda *a: None), bpy.context) == {'CANCELLED'}
assert shape(full) == before and set(bpy.data.materials) == materials
assert full.animation_data.action == action and binding.material == full and binding.action == action

assert bpy.ops.material.ksp_preview_simplify('EXEC_DEFAULT') == {'FINISHED'}
backup = bpy.data.materials[full['ksp_preview_backup']]
assert backup.use_fake_user and backup.node_tree.nodes.get('User handmade node')
assert not full.node_tree.nodes.get('User handmade node')
assert full.animation_data.action == action and binding.material == full and binding.action == action
assert all(t.id == full for fc in full.node_tree.animation_data.drivers for v in fc.driver.variables for t in v.targets)
assert profile == (bpy.context.scene.frame_current, bpy.context.scene.frame_start,
                   bpy.context.scene.frame_end, bpy.context.scene.render.fps)

# Editing one of three shared UV transforms must split it, not shift the others.
image.muimageprop.invertY = True
uv_test = make_shader(source, mu)
cube.data.materials[0] = uv_test
nodes = uv_test.node_tree.nodes
main, emission = nodes['_MainTex'], nodes['_Emissive']
assert main.inputs['Vector'].links[0].from_node == emission.inputs['Vector'].links[0].from_node
prop = next(p for p in uv_test.mumatprop.texture.properties if p.name == '_MainTex')
prop.offset = (.2, .3)
operators_context = SimpleNamespace(material=uv_test)
from io_object_mu_blender51.shader.textureprops import texture_update_mapping
texture_update_mapping(prop, operators_context)
first = main.inputs['Vector'].links[0].from_node
other = emission.inputs['Vector'].links[0].from_node
assert first != other and abs(first.inputs['Location'].default_value.x - .2) < 1e-5
assert other.inputs['Location'].default_value.x == 0 and other.inputs['Location'].default_value.y == 1

# A new non-identity mapping from implicit UV must be supplied actual UV input.
cube.data.materials[0] = simple
simple_prop = simple.mumatprop.texture.properties[0]
simple_prop.scale = (2, 3)
texture_update_mapping(simple_prop, SimpleNamespace(material=simple))
mapping = simple.node_tree.nodes['_MainTex'].inputs['Vector'].links[0].from_node
assert mapping.inputs['Vector'].is_linked

db = GameData(os.environ.get('KSP_STOCK_GAMEDATA', 'E:/SteamLibrary/steamapps/common/Kerbal Space Program/GameData'))
summary = {}
for name in ('mk1-3pod', 'noseCone', 'solidBooster.v2', 'parachuteSingle'):
    part = db.find_definition(name)
    assert part, name
    root = part.get_model([])
    mats = {mat for obj in data_objects(root) if obj.type == 'MESH' for mat in obj.data.materials if mat}
    summary[name] = {mat.name: len(mat.node_tree.nodes) for mat in mats}
    for mat in mats:
        assert len(mat.node_tree.nodes) <= 10, (name, mat.name, len(mat.node_tree.nodes))
        positions = [tuple(n.location) for n in mat.node_tree.nodes]
        assert len(set(positions)) == len(positions)
        for a in mat.node_tree.nodes:
            for b in mat.node_tree.nodes:
                if a != b and a.location.x == b.location.x:
                    assert abs(a.location.y - b.location.y) >= 300, (a.name, b.name)
        for fc in mat.node_tree.animation_data.drivers if mat.node_tree.animation_data else []:
            assert mat.node_tree.path_resolve(fc.data_path) is not None, fc.data_path
out = Path(__file__).resolve().parent / 'artifacts/compact-preview-counts.json'
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print('COMPACT_REAL_MATERIAL_COUNTS', summary)
saved = str(out.with_suffix('.blend'))
backup_name = backup.name
bpy.ops.wm.save_as_mainfile(filepath=saved, relative_remap=False)
bpy.ops.wm.open_mainfile(filepath=saved)
assert bpy.data.materials[backup_name].node_tree.nodes.get('User handmade node')
assert bpy.data.materials[backup_name].use_fake_user
print('COMPACT_PREVIEW_TEST_PASS')
