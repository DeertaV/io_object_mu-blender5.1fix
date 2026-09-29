"""Stock collision MeshFilters, materials, variants, remaps and packed save/reopen."""
import os
import sys, tempfile, importlib, json
from pathlib import Path
from types import SimpleNamespace
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.import_mu import import_mu
from io_object_mu_blender51.import_mu.textures import resolve_texture, load_texture_file
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.utils.import_assets import set_auxiliary_visibility, collect_clips
from io_object_mu_blender51.tools.imported_animation import data_objects
from io_object_mu_blender51.shader.shader import make_shader, ensure_principled_preview
from io_object_mu_blender51.mu import MuMaterial, MuMatTex, MuColliderMesh, Mu
from io_object_mu_blender51.cfgnode import ConfigNode
from io_object_mu_blender51.model import compile_model, realize_model_instance
from io_object_mu_blender51.model.appearance import compile_variant

gd = Path(os.environ.get('KSP_STOCK_GAMEDATA', 'E:/SteamLibrary/steamapps/common/Kerbal Space Program/GameData'))
assets = Path(__file__).resolve().parent / 'artifacts'
scene = bpy.context.scene
scene.frame_set(123)
scene.frame_start, scene.frame_end = 11, 711
scene.render.fps, scene.render.fps_base = 30, 1.001
before = (scene.frame_current_final, scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
directs = []
for relative in ['Squad/Parts/Aero/aerodynamicNoseCone/aerodynamicNoseCone.mu',
                 'Squad/Parts/Aero/cones/Assets/rocketNoseCone_v3.mu',
                 'Squad/Parts/Utility/parachuteMk1/model.mu', 'Squad/Parts/Engine/Size1_SRBs/SRB10.mu']:
    collection = bpy.data.collections.new(relative)
    scene.collection.children.link(collection)
    root, mu = import_mu(collection, str(gd / relative), True, False)
    for path, node in mu.object_paths.items():
        if hasattr(node, 'collider') and not hasattr(node, 'renderer') and hasattr(node, 'shared_mesh'):
            assert node.bobj.type == 'EMPTY', (relative, path)
            assert 'Collision-only MeshFilter omitted' in '\n'.join(mu.data_issues)
    for mat in (m.material for m in mu.materials):
        main = mat.node_tree.nodes.get('_MainTex')
        assert main and main.image and all(main.image.size) and main.image.packed_file, (relative, mat.name)
        assert main.inputs['Vector'].links[0].from_node.type == 'MAPPING'
        mapping = main.inputs['Vector'].links[0].from_node
        assert mapping.inputs['Scale'].default_value.y == -1
        assert mapping.inputs['Location'].default_value.y == 1
        assert not main.image.colorspace_settings.is_data
        bump = mat.node_tree.nodes.get('_BumpMap')
        if bump:
            assert bump.image and bump.image.colorspace_settings.is_data
            assert mat.node_tree.nodes['Principled BSDF'].inputs['Normal'].is_linked
        alpha = mat.node_tree.nodes['Principled BSDF'].inputs['Alpha']
        assert alpha.is_linked == ('Cutoff' in mat.mumatprop.shaderName)
        if 'Cutoff' in mat.mumatprop.shaderName:
            assert any(n.operation == 'GREATER_THAN' for n in alpha.links[0].from_node.node_tree.nodes if n.type == 'MATH')
    directs.append((root, collection))
assert before == (scene.frame_current_final, scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)

# A visual mesh can legitimately have a collider AND a COL-like name. Keep it.
visual_source = Mu().read(str(gd / 'Squad/Parts/Engine/Size1_SRBs/SRB10.mu'))
visual_node = visual_source.obj.children[0]
visual_node.transform.name = 'COL_real_visual'
visual_node.collider = MuColliderMesh(True)
visual_node.collider.mesh = visual_node.shared_mesh
visual_node.collider.convex, visual_node.collider.isTrigger = True, False
fixture = assets / 'visual-with-collider.mu'
visual_source.write(str(fixture))
keep = bpy.data.collections.new('Keep genuine visual mesh')
scene.collection.children.link(keep)
_, parsed = import_mu(keep, str(fixture), False, False)
assert parsed.obj.children[0].bobj.type == 'MESH'
assert len(parsed.obj.children[0].bobj.data.vertices) == len(visual_node.shared_mesh.verts)

# Missing image must not silently bind a same-named resource from another model.
source_mat = MuMaterial()
source_mat.name, source_mat.shaderName = 'missing image test', 'KSP/Diffuse'
prop = MuMatTex()
prop.index, prop.scale, prop.offset = 0, (1, 1), (0, 0)
source_mat.textureProperties['_MainTex'] = prop
bpy.data.images.new('unavailable', 8, 8)
fake = SimpleNamespace(textures=[SimpleNamespace(name='unavailable.png', type=0, blender_image_name='')], data_issues=[])
missing = make_shader(source_mat, fake)
assert missing.node_tree.nodes['_MainTex'].image is None

with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp) / 'GameData'
    (folder / 'A/Textures').mkdir(parents=True)
    image = bpy.data.images.new('fixture texture', 2, 2)
    image.pixels[:] = [1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1]
    image.filepath_raw = str(folder / 'A/Textures/UPPER.PNG')
    image.file_format = 'PNG'
    image.save()
    found, _ = resolve_texture('GameData\\a\\textures\\upper.png', str(folder / 'A'), str(folder))
    assert found.casefold() == str(folder / 'A/Textures/UPPER.PNG').casefold()
    assert resolve_texture('UPPER', str(folder / 'A'), str(folder))[0].casefold() == found.casefold()
    (folder / 'B').mkdir()
    (folder / 'B/UPPER.PNG').write_bytes(Path(found).read_bytes())
    from io_object_mu_blender51.import_mu.textures import _shared_index
    _shared_index.pop(str(folder), None)
    assert resolve_texture('UPPER', str(folder / 'A'), str(folder))[0] is None
    packed = load_texture_file(found)
    portable = str(assets / 'packed-texture-survival.blend')
    packed.use_fake_user = True
    packed_name = packed.name
    bpy.ops.wm.save_as_mainfile(filepath=portable)
    Path(found).unlink()
    bpy.ops.wm.open_mainfile(filepath=portable)
    packed = bpy.data.images.get(packed_name)
    assert packed.size[:] == (2, 2) and packed.packed_file

# Fresh GameData, then two independently colored instances of the SAME part.
scene = bpy.context.scene
db = GameData(str(gd))
nose = db.find_definition('noseCone')
first = nose.get_model([], variant='BlackAndWhite')
second = nose.get_model([], variant='White')
scene.collection.objects.link(first)
scene.collection.objects.link(second)
def main_images(root):
    return [m.node_tree.nodes['_MainTex'].image for o in data_objects(root) if o.type == 'MESH'
            for m in o.data.materials if m and m.node_tree.nodes.get('_MainTex')]
assert all(i['ksp_texture_source'].endswith('Rockomax_Adapters_diffuse_O.dds') for i in main_images(first))
assert all(i['ksp_texture_source'].endswith('Rockomax_Adapters_diffuse_W.dds') for i in main_images(second))
assert first.instance_collection != second.instance_collection
expanded = realize_model_instance(first, scene.collection)
assert second.instance_type == 'COLLECTION'
for obj in data_objects(expanded):
    if obj.type == 'MESH':
        for mat in obj.data.materials:
            if mat.node_tree.animation_data:
                assert all(t.id == mat for fc in mat.node_tree.animation_data.drivers
                           for v in fc.driver.variables for t in v.targets)

# A true rendererless mesh remains available, hidden in collection-instance mode.
helper = bpy.data.objects.new('rendererless helper', bpy.data.meshes.new('helper geometry'))
first.instance_collection.objects.link(helper)
from io_object_mu_blender51.utils.import_assets import auxiliary
auxiliary(helper, '不可见网格')
assert helper.hide_viewport and helper.hide_render
set_auxiliary_visibility(helper, True)
assert not helper.hide_viewport and not helper.hide_render
set_auxiliary_visibility(helper, False)
assert helper.hide_viewport and helper.hide_render

cfg = ConfigNode.load('PART\n{\nname = remapped\nMODEL\n{\nmodel = Squad/Parts/Engine/Size1_SRBs/SRB10\ntexture = SRB_O, Squad/Parts/Engine/Size1_SRBs/SRB_Y\n}\n}\n').GetNode('PART')
remapped = compile_model(db, 'Squad/Parts/Engine/Size1_SRBs', 'part', 'remapped', cfg, scene.collection, [])
remap_instance = bpy.data.objects.new('remap test', None)
remap_instance.instance_type, remap_instance.instance_collection = 'COLLECTION', remapped
assert any(i['ksp_texture_source'].endswith('SRB_Y.dds') for i in main_images(remap_instance))

# GAMEOBJECTS visibility retains geometry and propagates through its children.
hide_cfg = ConfigNode.load('PART\n{\nMODULE\n{\nname = ModulePartVariants\nVARIANT\n{\nname = Hidden\nGAMEOBJECTS\n{\nSRB10 = false\n}\n}\n}\n}\n').GetNode('PART')
hidden = compile_variant(remapped, 'hierarchical hide', hide_cfg, 'Hidden', db,
                         'Squad/Parts/Engine/Size1_SRBs', scene.collection, [])
hidden_meshes = [o for o in hidden.all_objects if o.type == 'MESH']
assert hidden_meshes and all(o.hide_viewport and o.hide_render for o in hidden_meshes)
assert all(len(o.data.vertices) for o in hidden_meshes)

craft_module = importlib.import_module('io_object_mu_blender51.import_craft.import_craft')
craft_module.gamedata = db
craft = str(gd.parent / 'Ships/VAB/Kerbal 1.craft')
for mode in (True, False):
    errors, skipped = [], []
    vessel = craft_module.import_craft(craft, mode, errors, skipped)
    assert not errors and not skipped
    parts = [o for o in vessel.children if o.get('ksp_part_root')]
    assert len(parts) == 33
    for part in parts:
        if part['ksp_part_name'] == 'noseCone':
            assert part['ksp_variant'] == 'BlackAndWhite'
            assert all(i['ksp_texture_source'].endswith('Rockomax_Adapters_diffuse_O.dds') for i in main_images(part))
        if part['ksp_part_name'] == 'solidBooster.v2':
            assert all(i['ksp_texture_source'].endswith('SRB_Y.dds') for i in main_images(part))
        for obj in data_objects(part):
            if obj.type == 'MESH':
                assert obj.muproperties.collider == 'MU_COL_NONE'
                assert not obj.get('ksp_auxiliary') or (obj.hide_render and obj.hide_viewport)
    print('STOCK_CRAFT_APPEARANCE_PASS', mode, len(parts))
    # These are test outputs, not replacements for the user's open scene.
    bpy.ops.wm.save_as_mainfile(filepath=str(assets / f'Kerbal-1-0.11.4-{mode}.blend'))

print('APPEARANCE_TEST_PASS')
