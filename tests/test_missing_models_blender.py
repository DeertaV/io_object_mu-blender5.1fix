"""Run with: blender --background --factory-startup --python this_file.py"""

import sys
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io_object_mu_blender51 as addon

addon.register()

from io_object_mu_blender51.import_craft.part import Part
from io_object_mu_blender51.model import compile_model
import importlib

craft_module = importlib.import_module(
    "io_object_mu_blender51.import_craft.import_craft")


class Config:
    def __init__(self, values=None, nodes=None):
        self.values = values or {}
        self.nodes = nodes or {}

    def GetValue(self, key):
        return self.values.get(key)

    def HasValue(self, key):
        return key in self.values

    def GetNodes(self, key):
        return self.nodes.get(key, [])

    def ToString(self, _):
        return ""


class FakeModel:
    def instantiate(self, name, *_):
        return bpy.data.objects.new(name, None)


class FakeDB:
    root = "C:/KSP/GameData"
    model_by_path = {}

    def model(self, url):
        return FakeModel() if url == "Example/available" else None


db = FakeDB()
partial_cfg = Config(
    {"name": "partial"},
    {"MODEL": [Config({"model": "Example/missing"}),
               Config({"model": "Example/available"})]},
)
all_missing_cfg = Config(
    {"name": "allMissing"},
    {"MODEL": [Config({"model": "Example/absent"})]},
)

messages = []
model = compile_model(db, "Example", "part", "partial", partial_cfg,
                      bpy.context.scene.collection, messages)
assert model is not None
assert len(model.objects) == 2  # root plus surviving submodel
assert len(messages) == 1 and "Example/missing" in messages[0]
assert "C:/KSP/GameData" in messages[0]

messages = []
model = compile_model(db, "Example", "part", "allMissing", all_missing_cfg,
                      bpy.context.scene.collection, messages)
assert model is None and len(messages) == 1
assert bpy.data.collections.get("allMissing:partmodel") is None

messages = []
model = compile_model(db, "Example", "part", "legacyMissing",
                      Config({"mesh": "absent.mu"}),
                      bpy.context.scene.collection, messages)
assert model is None and len(messages) == 1
assert "Example/absent" in messages[0]

messages = []
model = compile_model(db, "NoModels", "part", "defaultMissing",
                      Config(), bpy.context.scene.collection, messages)
assert model is None and len(messages) == 1
assert "<default mesh>" in messages[0]

partial = Part("Example/partial.cfg", partial_cfg)
partial.db = db
missing = Part("Example/missing.cfg", all_missing_cfg)
missing.db = db

craft = Config(
    {"ship": "Missing Model Test"},
    {"PART": [Config({"part": "unknown_1", "pos": "0,0,0", "rot": "0,0,0,1"}),
              Config({"part": "allMissing_2", "pos": "1,0,0", "rot": "0,0,0,1"}),
              Config({"part": "partial_3", "pos": "2,0,0", "rot": "0,0,0,1"})]},
)
db.parts = {"allMissing": missing, "partial": partial}
db.localizations = {}
craft_module.gamedata = db


class Operator:
    def __init__(self):
        self.reports = []

    def report(self, levels, message):
        self.reports.append((levels, message))


operator = Operator()
with patch.object(craft_module.ConfigNode, "loadfile", return_value=craft):
    result = craft_module.import_craft_op(
        operator, bpy.context, "missing-model-test.craft", True)
assert result == {'FINISHED'}
assert len(operator.reports) == 1
assert "2" in operator.reports[0][1]
report = bpy.data.texts.get("KSP Craft Import Issues")
assert report is not None
report_text = report.as_string()
assert "unknown" in report_text
assert "Example/absent" in report_text
assert "Example/missing" in report_text
assert len([o for o in bpy.context.scene.objects
            if o.instance_type == 'COLLECTION'
            and o.get('ksp_part_root')]) == 1

operator = Operator()
with patch.object(craft_module.ConfigNode, "loadfile", return_value=craft):
    result = craft_module.import_craft_op(
        operator, bpy.context, "missing-model-test.craft", False)
assert result == {'FINISHED'}
assert len(operator.reports) == 1
assert "2" in operator.reports[0][1]
assert "Example/missing" in bpy.data.texts["KSP Craft Import Issues.001"].as_string()

print("MISSING_MODEL_TEST_PASS")
