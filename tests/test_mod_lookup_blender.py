"""Mod paths, ModuleManager fidelity, definition ambiguity, refresh and cache roots."""
import sys
import importlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.cfgnode import ConfigNode, ConfigNodeError
from io_object_mu_blender51.import_craft.gamedata import GameData
from io_object_mu_blender51.model import Model
from io_object_mu_blender51.mu import Mu, MuObject, MuTransform, MuTagLayer

craft_module = importlib.import_module('io_object_mu_blender51.import_craft.import_craft')
prop_module = importlib.import_module('io_object_mu_blender51.prop.prop')

def model_file(path, x=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    node = MuObject('source')
    node.transform = MuTransform()
    node.transform.name, node.transform.localPosition = 'source', (x, 0, 0)
    node.transform.localRotation, node.transform.localScale = (1, 0, 0, 0), (1, 1, 1)
    node.tag_and_layer = MuTagLayer()
    node.tag_and_layer.tag, node.tag_and_layer.layer = 'Untagged', 0
    mu = Mu()
    mu.name, mu.obj, mu.materials, mu.textures = 'fixture', node, [], []
    mu.write(str(path))

anonymous = 'PART\n{\nname = 元件_名称\n{\nname = OptionalModModule\n}\nMODEL\n{\nmodel = Maker/New/Shared/shape\n}\n}\n'
try:
    ConfigNode.load(anonymous)
except ConfigNodeError:
    pass
else:
    raise AssertionError('Strict parsing must not silently repair unknown malformed data')
assert ConfigNode.load(anonymous, allow_unnamed=True).GetNode('PART').nodes[0].name == ''

with tempfile.TemporaryDirectory() as tmp:
    gd = Path(tmp) / 'GameData'
    local = gd / 'Maker/Parts/item'
    model_file(local / 'Assets/shape.mu')
    model_file(local / 'shape.mu')
    model_file(local / 'model.mu')
    model_file(gd / 'Maker/New/Shared/shape.mu')
    model_file(gd / 'Foreign/elsewhere.mu')
    (local / 'raw.cfg').write_text('PART\n{\nname = Unpatched\n}\n', encoding='utf-8')
    cache = gd / 'ModuleManager.ConfigCache'
    cache.write_text('UrlConfig\n{\nparentUrl = Maker/Parts/item/patched.cfg\n' + anonymous + '''PROP
{
name = Mod_PROP
MODEL
{
model = Assets/shape
}
}
INTERNAL
{
name = Mod_INTERNAL
MODEL
{
model = Maker/New/Shared/shape
}
}
}
''', encoding='utf-8-sig')
    db = GameData(str(gd))
    assert db.use_module_manager and db.database_issues
    assert 'Unpatched' not in db.parts
    assert db.find_definition('元件_名称').name == '元件.名称'
    assert db.find_definition('mod_prop', 'PROP').name == 'Mod_PROP'
    assert db.find_definition('Mod_INTERNAL', 'INTERNAL').name == 'Mod_INTERNAL'
    assert db.find_model_url('Assets/shape', 'Maker/Parts/item') == 'Maker/Parts/item/Assets/shape'
    assert db.find_model_url('../item/Assets/shape', 'Maker/Parts/item') == 'Maker/Parts/item/Assets/shape'
    assert db.find_model_url('Maker/Old/Shared/shape', 'Maker/Parts/item') == 'Maker/Parts/item/shape'
    # A relocation with no local exact filename can use an exact two-component suffix.
    assert db.find_model_url('Maker/Old/Shared/shape', 'Maker/Other') == 'Maker/New/Shared/shape'
    model_file(gd / 'Maker/Duplicate/Shared/shape.mu')
    db.process_mu(str(gd / 'Maker/Duplicate/Shared/shape.mu').replace('\\', '/'))
    notes = []
    assert db.find_model_url('Maker/Old/Shared/shape', 'Maker/Other', diagnostics=notes) is None
    assert any('[ambiguous]' in n for n in notes)
    assert db.find_model_url('Foreign/shape', 'Maker/Parts/item') is None
    assert db.find_model_url('MissingMod/Assets/shape', 'Maker/Parts/item') is None
    notes = []
    assert db.find_model_url('Maker/Parts/item/renamed', 'Maker/Parts/item', diagnostics=notes) is None
    assert any('[suggestions only]' in n for n in notes)
    assert db.find_model_url('model/model.mu', 'Maker/Parts/item', True) == 'Maker/Parts/item/model'
    for source in ('Maker/a.cfg', 'Maker/b.cfg'):
        db.process_cfgnode(source, ConfigNode.load('PART\n{\nname = Duplicate_part\n}\n').GetNode('PART'))
    notes = []
    assert db.find_definition('Duplicate_part', diagnostics=notes) is None
    assert 'Maker/a.cfg' in notes[-1] and 'Maker/b.cfg' in notes[-1]
    # Missing identifiers produce suggestions, not substituted definitions.
    assert db.find_definition('Mod_PR0P', 'PROP', []) is None
    prefs = SimpleNamespace(GameData=str(gd))
    with patch.object(prop_module, 'Preferences', return_value=prefs):
        prop_cfg = local / 'modprop.cfg'
        prop_cfg.write_text('PROP\n{\nname = Mod_PROP\n}\n')
        prop_module.gamedata = db
        prop = prop_module.import_prop(str(prop_cfg))
        instance = prop.get_model()
        assert instance and instance.get('ksp_part_root')
    # Refresh creates a new database but leaves every scene object untouched.
    before = {o.as_pointer() for o in bpy.data.objects}
    with patch.object(craft_module, 'Preferences', return_value=prefs):
        assert bpy.ops.object.ksp_gamedata_refresh() == {'FINISHED'}
    assert before == {o.as_pointer() for o in bpy.data.objects}
    assert craft_module.gamedata.use_module_manager
    assert prop_module.gamedata is craft_module.gamedata
    assert bpy.data.texts.get('KSP GameData Diagnostics')
    # Wrong/renamed filenames require explicit confirmation; mappings persist
    # in .blend scene data, stay scoped to the CFG folder, and can be removed.
    with patch.object(craft_module, 'Preferences', return_value=prefs):
        assert bpy.ops.object.ksp_model_alias_add(reference='Maker/Parts/item/renamed',
                                                directory='Maker/Parts/item', target=str(local / 'shape.mu')) == {'FINISHED'}
    saved_path = str(Path(tmp) / 'confirmed-model-mappings.blend')
    bpy.ops.wm.save_as_mainfile(filepath=saved_path)
    bpy.ops.wm.open_mainfile(filepath=saved_path)
    notes = []
    saved_db = GameData(str(gd))
    assert saved_db.find_model_url('Maker/Parts/item/renamed', 'Maker/Parts/item', diagnostics=notes) == 'Maker/Parts/item/shape'
    assert any('User-confirmed' in note for note in notes)
    assert saved_db.find_model_url('Maker/Parts/item/renamed', 'Maker/Elsewhere') is None
    with patch.object(craft_module, 'Preferences', return_value=prefs):
        assert bpy.ops.object.ksp_model_alias_remove(reference='Maker/Parts/item/renamed', directory='Maker/Parts/item') == {'FINISHED'}
    saved_db.sync_aliases()
    assert saved_db.find_model_url('Maker/Parts/item/renamed', 'Maker/Parts/item') is None
    # Equal URLs in two different KSP installations must not share cached geometry.
    path_a, path_b = gd / 'Shared/model.mu', Path(tmp) / 'second/GameData/Shared/model.mu'
    model_file(path_a, 1)
    model_file(path_b, 2)
    a, b = Model(str(path_a), 'Shared/model'), Model(str(path_b), 'Shared/model')
    assert a.model != b.model
    assert Model.Preloaded(root=str(gd).replace('\\', '/'))['Shared/model'].model == a.model
    old = a.model
    model_file(path_a, 333)
    updated = Model(str(path_a), 'Shared/model')
    assert updated.model != old
    assert old.name in bpy.data.collections

print('MOD_LOOKUP_TEST_PASS')
