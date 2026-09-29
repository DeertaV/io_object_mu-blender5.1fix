"""Headless, bracketed undo/redo for opt-in legacy preview simplification."""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.shader.shader import make_shader
from io_object_mu_blender51.mu import MuMaterial
source = MuMaterial()
source.name, source.shaderName = 'Undo preview material', 'KSP/Diffuse'
source.colorProperties['_Color'] = (.1, .2, .3, 1)
mat = make_shader(source, SimpleNamespace(textures=[], data_issues=[]))
mat.node_tree.nodes.new('ShaderNodeValue').name = 'Handmade before simplify'
cube = bpy.context.active_object
cube.data.materials.clear()
cube.data.materials.append(mat)
name = mat.name
bpy.context.preferences.edit.use_global_undo = True
bpy.context.view_layer.update()
bpy.ops.ed.undo_push(message='before preview simplification')
assert bpy.ops.material.ksp_preview_simplify('EXEC_DEFAULT') == {'FINISHED'}
backup = bpy.data.materials[name]['ksp_preview_backup']
bpy.ops.ed.undo_push(message='after preview simplification')
assert not bpy.data.materials[name].node_tree.nodes.get('Handmade before simplify')
assert bpy.ops.ed.undo() == {'FINISHED'}
assert bpy.data.materials[name].node_tree.nodes.get('Handmade before simplify')
assert bpy.ops.ed.redo() == {'FINISHED'}
assert not bpy.data.materials[name].node_tree.nodes.get('Handmade before simplify')
assert bpy.data.materials[backup].node_tree.nodes.get('Handmade before simplify')
assert bpy.data.materials[backup].use_fake_user
print('PREVIEW_UNDO_REDO_TEST_PASS')
