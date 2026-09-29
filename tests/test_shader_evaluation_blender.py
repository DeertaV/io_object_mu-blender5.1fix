"""Render asserts for actual UV flipping/alpha clipping and independent tint drivers."""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.mu import MuMaterial, MuMatTex
from io_object_mu_blender51.shader.shader import make_shader
from io_object_mu_blender51.model.model import copy_material

image = bpy.data.images.new('RGBA corner fixture', 2, 2, alpha=True)
image.pixels[:] = [1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0]
image.muimageprop.invertY = True
source = MuMaterial()
source.name, source.shaderName = 'cutout fixture', 'KSP/Alpha/Cutoff'
source.colorProperties['_Color'] = (1, 1, 1, 1)
source.floatProperties3['_Cutoff'] = .5
tex = MuMatTex()
tex.index, tex.scale, tex.offset = 0, (1, 1), (0, 0)
source.textureProperties['_MainTex'] = tex
mu = SimpleNamespace(textures=[SimpleNamespace(name=image.name, type=0, blender_image_name=image.name)], data_issues=[])
mat = make_shader(source, mu)
mat.node_tree.nodes['_MainTex'].interpolation = 'Closest'
pbsdf = mat.node_tree.nodes['Principled BSDF']
pbsdf.inputs['Emission Strength'].default_value = 1
mat.node_tree.links.new(pbsdf.inputs['Base Color'].links[0].from_socket, pbsdf.inputs['Emission Color'])

scene = bpy.data.scenes.new('Shader pixel regression')
bpy.context.window.scene = scene
bpy.ops.mesh.primitive_plane_add(size=2)
plane = bpy.context.object
plane.data.materials.append(mat)
camera = bpy.data.objects.new('fixture camera', bpy.data.cameras.new('fixture camera'))
scene.collection.objects.link(camera)
camera.location = (0, 0, 3)
camera.data.type, camera.data.ortho_scale = 'ORTHO', 2
scene.camera = camera
scene.render.engine = 'CYCLES'
scene.cycles.device, scene.cycles.samples = 'CPU', 4
scene.render.resolution_x = scene.render.resolution_y = 32
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.view_settings.view_transform = 'Standard'
out = Path(__file__).resolve().parent / 'artifacts/shader-UV-alpha-pixels.png'
scene.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
pixels = bpy.data.images.load(str(out)).pixels[:]
def pixel(x, y):
    return pixels[(y * 32 + x) * 4:(y * 32 + x + 1) * 4]
# Blender image pixels are bottom-up. DDS inversion must swap red/blue rows.
bottom_left, top_left = pixel(6, 6), pixel(6, 25)
assert bottom_left[2] > .8 and bottom_left[0] < .1, bottom_left
assert top_left[0] > .8 and top_left[2] < .1, top_left
assert bottom_left[3] > .99 and pixel(25, 6)[3] < .01 and pixel(25, 25)[3] < .01

# A copied part's color drivers must evaluate its OWN source properties.
clone = copy_material(mat, {}, {})
clone.mumatprop.color.properties[0].value = (.2, .4, .6, 1)
other_plane = plane.copy()
other_plane.data = plane.data.copy()
other_plane.data.materials[0] = clone
scene.collection.objects.link(other_plane)
other_plane.location.x = 5
scene.frame_set(2)
depsgraph = bpy.context.evaluated_depsgraph_get()
value = clone.evaluated_get(depsgraph).node_tree.nodes['KSP 颜色与透明'].inputs['颜色'].default_value
assert all(abs(a - b) < 1e-5 for a, b in zip(value, (.2, .4, .6, 1))), tuple(value)
original = mat.evaluated_get(depsgraph).node_tree.nodes['KSP 颜色与透明'].inputs['颜色'].default_value
assert tuple(original) == (1, 1, 1, 1)
print('SHADER_PIXEL_AND_DRIVER_TEST_PASS')
