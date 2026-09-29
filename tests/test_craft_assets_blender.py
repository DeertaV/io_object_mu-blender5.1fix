"""Selectable per-part craft instances, nested remapping, skinned part isolation."""
import os
import sys
from pathlib import Path
import importlib
from unittest.mock import patch
from types import SimpleNamespace
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.cfgnode import ConfigNode
from io_object_mu_blender51.import_craft.part import Part
from io_object_mu_blender51.model import Model
from io_object_mu_blender51.utils.import_assets import collect_clips, binding_target, model_root, walk_objects
from io_object_mu_blender51.tools.imported_animation import (add_clip, remove_scheduled, data_objects,
                                                           VIEW3D_PT_KSPImportedData, VIEW3D_PT_KSPAuxiliaryData)

module = importlib.import_module('io_object_mu_blender51.import_craft.import_craft')
gd = Path(os.environ.get('KSP_EXTRA_GAMEDATA', 'D:/Steam/steamapps/common/Kerbal Space Program/GameData'))

class Database:
    root = str(gd)
    localizations = {}
    model_by_path = {}
    parts = {}
    models = {}

    def model(self, name):
        if name not in self.models:
            paths = {'Test/drill': 'ReStock/Assets/Resource/restock-drill-radial-1.mu',
                     'Test/solar': 'ReStock/Assets/Electrical/restock-solarpanel-1x6.mu'}
            if name not in paths:
                return None
            self.models[name] = Model(str(gd / paths[name]), name)
        return self.models[name]

db = Database()
for name in ('drill', 'solar'):
    cfg = ConfigNode.load('PART\n{\nname = ' + name + '\nMODEL\n{\nmodel = Test/' + name + '\n}\n}\n').GetNode('PART')
    part = Part('Test/' + name + '.cfg', cfg)
    part.db = db
    db.parts[name] = part
module.gamedata = db
craft = ConfigNode.load('''ship = two skinned parts
PART
{
part = drill_100
pos = 0,0,0
rot = 0,0,0,1
}
PART
{
part = drill_101
pos = 2,0,0
rot = 0,0,0,1
}
PART
{
part = solar_102
pos = 4,0,0
rot = 0,0,0,1
}
''')
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 20, 900
scene.frame_set(137)
scene.cursor.location = (1,2,3)

# Mock layouts exercise drawing all registered panel branches in headless Blender.
class Layout:
    def box(self): return self
    def row(self, **kwargs): return self
    def label(self, **kwargs): pass
    def prop(self, *args, **kwargs): pass
    def operator(self, *args, **kwargs): return SimpleNamespace()

for instanced in (True, False):
    with patch.object(ConfigNode, 'loadfile', return_value=craft):
        vessel = module.import_craft('regression.craft', instanced, [], [])
    bpy.context.view_layer.update()
    assert scene.frame_current == 137 and scene.frame_start == 20 and scene.frame_end == 900
    parts = [o for o in vessel.children if o.get('ksp_part_root')]
    assert len(parts) == 3
    selected, other = parts[0], parts[1]
    assert len(collect_clips(selected)) == 2
    if instanced:
        assert all(p.instance_type == 'COLLECTION' for p in parts)
        assert all(p.name in bpy.context.view_layer.objects for p in parts)
    selected.ksp_assets.clip_choice = '0'
    selected.ksp_assets.insert_frame = 200
    bpy.context.view_layer.objects.active = selected
    matrix = selected.matrix_world.copy()
    selected, group = add_clip(selected, bpy.context)
    assert selected.instance_type == 'NONE'
    if instanced:
        assert other.instance_type == 'COLLECTION'
    assert all(abs(matrix[i][j] - selected.matrix_world[i][j]) < 1e-5 for i in range(4) for j in range(4))
    own_ids = {binding_target(e) for e in group.entries}
    other_ids = {binding_target(e) for _, c in collect_clips(other) for e in c.bindings}
    assert not own_ids & other_ids
    nodes = list(walk_objects(selected))
    for node in nodes:
        assert model_root(node) == selected
        for mod in node.modifiers:
            if mod.type == 'ARMATURE':
                assert mod.object in nodes
        for bone in getattr(getattr(node, 'pose', None), 'bones', []):
            for constraint in bone.constraints:
                if hasattr(constraint, 'target') and constraint.target:
                    assert constraint.target in nodes, 'Pose constraints must not target cached source rigs'
    for panel in (VIEW3D_PT_KSPImportedData, VIEW3D_PT_KSPAuxiliaryData):
        panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
    # Add the identical source clip to a second drill at exactly the same time,
    # then add the different solar part. Existing coverage only inspected the
    # untouched second part and never actually scheduled it through the UI.
    previous_ids = {binding_target(e) for e in group.entries}
    for next_part in (other, parts[2]):
        next_part.ksp_assets.clip_choice = '0'
        next_part.ksp_assets.insert_frame = 200
        bpy.context.view_layer.objects.active = next_part
        assert bpy.ops.object.ksp_imported_clip_add('EXEC_DEFAULT') == {'FINISHED'}
        next_root = bpy.context.active_object
        assert len(next_root.ksp_assets.scheduled) == 1
        next_group = next_root.ksp_assets.scheduled[0]
        targets = {binding_target(e) for e in next_group.entries}
        assert not targets & previous_ids
        previous_ids.update(targets)
        assert not next_group.overrides
        assert len(selected.ksp_assets.scheduled) == 1
    # Removing one instance leaves all independently scheduled parts intact.
    remove_scheduled(selected, group.uid)
    assert sum(len(p.ksp_assets.scheduled) for p in vessel.children
               if p.get('ksp_part_root')) == 2

# Cache recovery must use real collection IDs, not Collection custom properties.
assert Model(None, 'Test/drill').model == db.models['Test/drill'].model
addon.unregister()
assert not hasattr(bpy.types.Object, 'ksp_assets')
addon.register()
assert hasattr(bpy.types.Object, 'ksp_assets')
print('CRAFT_ASSET_TEST_PASS')
