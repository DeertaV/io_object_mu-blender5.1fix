"""Read actual kOS/ASET/FASA mod models, including explicit stale-path repairs."""
import os
import sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.tools.imported_animation import data_objects

scene = bpy.context.scene
scene.frame_set(177)
scene.render.fps, scene.render.fps_base = 30, 1.001
before = (scene.frame_current_final, scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
db = GameData(os.environ.get('KSP_MOD_GAMEDATA', 'K:/Real Kerbal Space Program/GameData'))
assert db.use_module_manager and len(db.parts) > 1700 and len(db.props) > 1400
for name in ('KR-2042', 'ALCOR.LanderCapsule'):
    part = db.find_definition(name)
    missing = []
    obj = part.get_model(missing)
    assert obj and not missing, (name, missing)
    objects = data_objects(obj)
    assert any(o.type == 'MESH' for o in objects)
    assert all(o.muproperties.collider == 'MU_COL_NONE' for o in objects)
    assert all(not o.animation_data or (not o.animation_data.action and not o.animation_data.nla_tracks) for o in objects)
    print('REAL_MOD_PART_PASS', name, 'objects', len(objects))

repairs = [('FASALM.DockingCone', 'FASA/Apollo/LEM/DockingCone/LM_DockinCone',
            'FASA/Apollo/LEM/DockingCone/FASA_Apollo_DockinCone_LM'),
           ('FASA.Gemini.RCS.Thrusters', 'FASA/Gemini2/FASA_Gemini_RCS_Thruster/model',
            'FASA/Gemini2/FASA_Gemini_RCS_Thruster/GeminiRCSThruster')]
for name, missing_url, target in repairs:
    part = db.find_definition(name)
    missing = []
    result = part.get_model(missing)
    assert missing, (name, part.path, result)
    # Multi-MODEL parts can already retain their valid submodels; the missing
    # reference is still reported rather than silently replaced or duplicated.
    assert 'suggestions only' in missing[0] and target in missing[0]
    db.set_alias(missing_url, part.path, target)
    missing = []
    obj = part.get_model(missing)
    assert obj and not missing
    assert any(o.type == 'MESH' for o in data_objects(obj))
    print('REAL_MOD_CONFIRMED_REPAIR_PASS', name)
prop = next(prop for name, prop in sorted(db.props.items())
            if prop.path.startswith('ASET/') and prop.cfg.GetNodes('MODEL'))
obj = prop.get_model()
assert obj and obj.get('ksp_part_root') and any(o.type == 'MESH' for o in data_objects(obj))
print('REAL_MOD_PROP_PASS', prop.name)
assert before == (scene.frame_current_final, scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
print('MOD_ASSET_TEST_PASS')
