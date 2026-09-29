"""Render three actual stock assets with the importer; isolated QA scenes only."""
import os
import sys
from pathlib import Path
import bpy
from mathutils import Vector
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
sys.path.insert(0, args[0] if args else str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
version = '.'.join(str(v) for v in addon.bl_info['version'])
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.model import realize_model_instance

assets = Path(__file__).resolve().parent / 'artifacts'
db = GameData(os.environ.get('KSP_STOCK_GAMEDATA', 'E:/SteamLibrary/steamapps/common/Kerbal Space Program/GameData'))
for name, variant in [('noseCone', 'BlackAndWhite'), ('solidBooster.v2', 'YellowAndWhite'), ('parachuteSingle', '')]:
    scene = bpy.data.scenes.new('QA ' + name)
    bpy.context.window.scene = scene
    instance = db.find_definition(name).get_model([], variant=variant)
    scene.collection.objects.link(instance)
    root = realize_model_instance(instance, scene.collection)
    bpy.data.objects.remove(instance)
    bpy.context.view_layer.update()
    meshes = [o for o in root.children_recursive if o.type == 'MESH' and not o.hide_render]
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (low + high) / 2
    size = max(high - low)
    camera = bpy.data.objects.new('QA Camera', bpy.data.cameras.new('QA Camera'))
    scene.collection.objects.link(camera)
    camera.location = center + Vector((2.5, -4, 1.8)).normalized() * size * 2.3
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type, camera.data.ortho_scale = 'ORTHO', size * 1.5
    scene.camera = camera
    world = bpy.data.worlds.new('QA neutral world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.28, .28, .28, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .65
    scene.world = world
    for offset, energy in [((2, -3, 4), 350), ((-3, -1, 1), 150), ((0, 3, 3), 220)]:
        light = bpy.data.objects.new('QA softbox', bpy.data.lights.new('QA softbox', 'AREA'))
        scene.collection.objects.link(light)
        light.location = center + Vector(offset) * size
        light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
        light.data.energy, light.data.shape, light.data.size = energy * size * size, 'DISK', size * 2
    scene.render.engine = 'CYCLES'
    scene.cycles.device, scene.cycles.samples = 'CPU', 24
    scene.render.resolution_x, scene.render.resolution_y = 512, 512
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(assets / f'appearance-{version}-{name}.png')
    bpy.ops.render.render(write_still=True)
    print('APPEARANCE_RENDER_PASS', name, scene.render.filepath)
