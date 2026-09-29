# vim:ts=4:et
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>
import os

import bpy
from mathutils import Vector, Quaternion

from ..cfgnode import ConfigNode
from ..cfgnode import parse_float
from ..model import compile_model
from ..utils import util_collection

def loaded_parts_collection():
    return util_collection("loaded_parts")

class Part:
    @classmethod
    def Preloaded(cls):
        preloaded = {}
        for g in bpy.data.collections:
            if g.name[:5] == "part:":
                url = g.name[5:]
                part = Part("", ConfigNode.load(g.mumodelprops.config, allow_unnamed=True))
                #part.model = bpy.data.collections[g.name]
                part.model = g
                preloaded[part.name] = part
        return preloaded
    def __init__(self, path, cfg):
        self.cfg = cfg
        self.path = os.path.dirname(path)
        if not cfg.HasValue("name"):
            print("PART missing name in " + path)
            self.name = ""
        else:
            self.name = cfg.GetValue("name").replace("_", ".")
        self.model = None
        self.variant_models = {}
        self.model_unavailable = False
        self.unavailable_generation = -1
        self.missing_model_messages = []
        self.scale = 1.0
        self.rescaleFactor = 1.25
        if cfg.HasValue("scale"):
            self.scale = parse_float(cfg.GetValue("scale"))
        if cfg.HasValue("rescaleFactor"):
            self.rescaleFactor = parse_float(cfg.GetValue("rescaleFactor"))
    def get_model(self, missing_models=None, variant=''):
        generation = getattr(self.db, 'import_generation', 0)
        if self.model_unavailable and self.unavailable_generation != generation:
            # A later craft import may follow copying/installing missing files.
            # Retry once per import, without retrying every repeated PART instance.
            self.model_unavailable = False
            self.missing_model_messages = []
        if missing_models is not None:
            for message in self.missing_model_messages:
                if message not in missing_models:
                    missing_models.append(message)
        if self.model_unavailable:
            return None
        if not self.model:
            messages = [] if missing_models is not None else None
            self.model = compile_model(self.db, self.path, "part", self.name,
                                       self.cfg, loaded_parts_collection(),
                                       messages)
            if messages:
                self.missing_model_messages = messages
                for message in messages:
                    if message not in missing_models:
                        missing_models.append(message)
            if self.model is None:
                self.model_unavailable = True
                self.unavailable_generation = generation
                return None
            props = self.model.mumodelprops
            props.config = self.cfg.ToString(-1)
        if hasattr(self.db, 'lookup_messages'):
            for line in self.model.get('ksp_lookup_notes', '').splitlines():
                if line not in self.db.lookup_messages:
                    self.db.lookup_messages.append(line)
        scale = self.rescaleFactor
        selected_model = self.model
        if variant:
            if variant not in self.variant_models:
                from ..model.appearance import compile_variant, appearance_report
                notes = []
                self.variant_models[variant] = compile_variant(self.model, self.name, self.cfg, variant,
                    self.db, self.path, loaded_parts_collection(), notes)
                appearance_report(self.name, self.path, notes)
            selected_model = self.variant_models[variant]
        model = self.instantiate(Vector((0, 0, 0)),
                                 Quaternion((1,0,0,0)),
                                 Vector((1, 1, 1)) * scale, selected_model)
        model['ksp_variant'] = variant
        model['ksp_cfg_directory'] = self.path
        model['ksp_part_name'] = self.name
        return model

    def instantiate(self, loc, rot, scale, model_collection=None):
        obj = bpy.data.objects.new(self.name, None)
        from ..utils.import_assets import uid
        obj["ksp_part_root"] = True
        obj.ksp_assets.uid = uid()
        obj.ksp_assets.source = self.path
        obj.instance_type = 'COLLECTION'
        obj.instance_collection = model_collection or self.model
        from ..utils.import_assets import collect_clips, auxiliary
        auxiliary(obj, "零件根节点")
        if collect_clips(obj):
            obj.ksp_assets.clip_choice = '0'
        obj.location = loc
        obj.scale = scale
        return obj

