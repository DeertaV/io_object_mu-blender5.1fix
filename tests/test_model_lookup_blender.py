"""Path resolution, unique legacy fallback and actual latest craft regression."""
import os
import sys
import tempfile
import importlib
from pathlib import Path
from unittest.mock import patch
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.cfgnode import ConfigNode
from io_object_mu_blender51.model import compile_model
gamedata_module = importlib.import_module('io_object_mu_blender51.import_craft.gamedata')

class FakeModel:
    def __init__(self, path, url):
        self.url = url
    def instantiate(self, name, *args):
        return bpy.data.objects.new(name, None)

with tempfile.TemporaryDirectory() as tmp:
    game = Path(tmp) / 'game'
    gd = game / 'GameData'
    folder = gd / 'Example/Tank'
    folder.mkdir(parents=True)
    (folder / 'ActualTank.MU').write_bytes(b'lookup only')
    (folder / 'tank.cfg').write_text('PART\n{\nname = fixture\nmesh = model.mu\n}\n')
    hidden = gd / '_ValidMod'
    hidden.mkdir()
    (hidden / 'mesh.mu').write_bytes(b'lookup only')
    db = GameData(str(gd))
    assert hasattr(db, 'find_model_url'), 'Missing normalized/fallback resolver'
    assert GameData(str(game)).root == str(gd).replace('\\', '/')
    assert db.find_model_url(' "GameData\\example\\tank\\ActualTank.mu" ') == 'Example/Tank/ActualTank'
    assert db.find_model_url('_ValidMod/mesh') == '_ValidMod/mesh'
    notes = []
    assert db.find_model_url('Example/Tank/model', 'Example/Tank', True, notes) == 'Example/Tank/ActualTank'
    assert notes and 'ActualTank' in notes[-1]
    cfg = ConfigNode.load('PART\n{\nname = fixture\nmesh = model.mu\n}\n').GetNode('PART')
    with patch.object(gamedata_module, 'Model', FakeModel):
        missing = []
        result = compile_model(db, 'Example/Tank', 'part', 'fixture', cfg, bpy.context.scene.collection, missing)
    assert result and not missing and 'ActualTank' in result['ksp_lookup_notes']
    assert db.find_model_url('Example/Tank/model') is None, 'Modern MODEL must not guess a different file'
    assert db.find_model_url('../outside') is None
    (folder / 'Other.mu').write_bytes(b'lookup only')
    notes = []
    assert db.find_model_url('Example/Tank/model', 'Example/Tank', True, notes) is None
    assert notes and 'Other' in notes[-1] and 'ActualTank' in notes[-1]
    missing = []
    assert compile_model(db, 'Example/Tank', 'part', 'ambiguous', cfg, bpy.context.scene.collection, missing) is None
    assert 'Other' in missing[0] and 'ActualTank' in missing[0]
    notes = []
    assert db.find_model_url(None, 'Example/Tank', True, notes) is None
    # Newly copied exact files become available without restarting Blender.
    assert db.find_model_url('Example/Tank/Other.mu') == 'Example/Tank/Other'
    # A failed part is retried on the next import, but cached within one import.
    from io_object_mu_blender51.import_craft.part import Part
    recover_cfg = ConfigNode.load('PART\n{\nname = recover\nMODEL\n{\nmodel = New/Added\n}\n}\n').GetNode('PART')
    part = Part('New/recover.cfg', recover_cfg)
    part.db = db
    assert part.get_model([]) is None
    target = gd / 'New/Added.mu'
    target.parent.mkdir()
    target.write_bytes(b'lookup only')
    assert part.get_model([]) is None
    db.import_generation += 1
    with patch.object(gamedata_module, 'Model', FakeModel):
        problems = []
        assert part.get_model(problems) is not None and not problems

actual = Path(os.environ.get('KSP_STOCK_ROOT', str(Path(os.environ.get('KSP_STOCK_GAMEDATA', 'E:/SteamLibrary/steamapps/common/Kerbal Space Program/GameData')).parent)))
craft = actual / 'Ships/VAB/Kerbal 1.craft'
db = GameData(str(actual / 'GameData'))
notes = []
assert db.find_model_url('Squad/Parts/FuelTank/RCSFuelTankR25/model',
                         'Squad/Parts/FuelTank/RCSFuelTankR25', True, notes).endswith('/RCSFuelTankR25')
module = importlib.import_module('io_object_mu_blender51.import_craft.import_craft')
module.gamedata = db
missing, skipped = [], []
vessel = module.import_craft(str(craft), True, missing, skipped)
assert not missing and not skipped, (missing, skipped)
cfg = ConfigNode.loadfile(str(craft))
parts = [o for o in vessel.children if o.get('ksp_part_root')]
assert len(parts) == len(cfg.GetNodes('PART'))
assert any('RCSFuelTank' in o.name for o in parts)
assert any('RCSFuelTankR25' in line for line in db.lookup_messages)
class Operator:
    def __init__(self):
        self.messages = []
    def report(self, level, message):
        self.messages.append((level, message))
operator = Operator()
assert module.import_craft_op(operator, bpy.context, str(craft), False) == {'FINISHED'}
assert not any('WARNING' in levels or 'ERROR' in levels for levels, _ in operator.messages)
assert any('已恢复' in message for _, message in operator.messages)
assert 'RCSFuelTankR25.mu' in bpy.data.texts['KSP Model Lookup Report'].as_string()
assert not bpy.data.texts.get('KSP Craft Import Issues')
print('LATEST_CRAFT_FIXED', len(parts), 'part instances; skipped', len(skipped))
print('MODEL_LOOKUP_TEST_PASS')
