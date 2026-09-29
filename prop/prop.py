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
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector, Quaternion
from bpy.props import StringProperty, EnumProperty

from ..preferences import Preferences
from ..cfgnode import ConfigNode, ConfigNodeError
from ..utils import collect_objects, strip_nnn, util_collection
from ..model import compile_model, instantiate_model

def loaded_props_collection():
    return util_collection("loaded_props")

class Prop:
    @classmethod
    def Preloaded(cls):
        preloaded = {}
        for g in bpy.data.collections:
            if g.name[:5] == "prop:":
                url = g.name[5:]
                prop = Prop("", ConfigNode.load(g.mumodelprops.config, allow_unnamed=True))
                prop.model = g
                preloaded[url] = prop
        return preloaded
    def __init__(self, path, cfg):
        self.cfg = cfg
        self.path = os.path.dirname(path)
        self.name = cfg.GetValue("name")
        self.model = None
    def get_model(self, missing_models=None):
        if not self.model:
            self.model = compile_model(self.db, self.path, "prop", self.name,
                                       self.cfg, loaded_props_collection(), missing_models)
            if self.model is None:
                return None
            props = self.model.mumodelprops
            props.config = self.cfg.ToString(-1)
        model = self.instantiate(Vector((0, 0, 0)),
                                 Quaternion((1,0,0,0)),
                                 Vector((1, 1, 1)))
        return model

    def instantiate(self, loc, rot, scale):
        obj = bpy.data.objects.new(self.name, None)
        from ..utils.import_assets import uid, auxiliary, collect_clips
        obj['ksp_part_root'] = True
        obj.ksp_assets.uid, obj.ksp_assets.source = uid(), self.path
        obj.instance_type = 'COLLECTION'
        obj.instance_collection = self.model
        auxiliary(obj, 'PROP 根节点')
        if collect_clips(obj):
            obj.ksp_assets.clip_choice = '0'
        obj.location = loc
        return obj

gamedata = None
def import_prop(filepath):
    global gamedata
    from ..import_craft.gamedata import GameData, game_data_root
    configured = Preferences().GameData
    if (not gamedata or game_data_root(configured) != gamedata.root
            or gamedata.configuration_stamp() != gamedata.cache_stamp):
        gamedata = GameData(configured)
    gamedata.sync_aliases()
    try:
        propcfg = ConfigNode.loadfile(filepath, allow_unnamed=True)
    except ConfigNodeError as e:
        print(filepath+e.message)
        return
    from ..import_mu import MuImportError
    propnode = propcfg.GetNode('PROP') if isinstance(propcfg, ConfigNode) else None
    if not propnode:
        raise MuImportError('Prop', f'No PROP definition in {filepath}')
    filepath = os.path.abspath(filepath).replace('\\', '/')
    if filepath.casefold().startswith(gamedata.root.casefold() + '/'):
        #the prop is in GameData
        name = propnode.GetValue("name")
        notes = []
        result = gamedata.find_definition(name, 'PROP', notes)
        if result is None:
            raise MuImportError('Prop', f'PROP {name!r} missing or ambiguous: ' + '; '.join(notes))
        return result
    # load it directly
    result = Prop(filepath, propnode)
    result.db = gamedata
    return result

def make_prop(obj):
    name = strip_nnn(obj.name)
    obj.select_set(False)
    prop = collect_objects("prop:"+name, obj)
    obj.muproperties.modelType = 'PROP'
    loc = Vector(obj.location)
    rot = Quaternion(obj.rotation_quaternion)
    scale = Vector(obj.scale)
    parent = obj.parent
    obj.location = Vector((0, 0, 0))
    obj.rotation_quaternion = Quaternion((1, 0, 0, 0))
    obj.scale = Vector((1, 1, 1))
    obj.parent = None
    prop.mumodelprops.name = name
    prop.mumodelprops.type = "prop"
    loaded_props = loaded_props_collection()
    loaded_props.children.link(prop)
    for c in bpy.data.collections:
        if c == prop:
            continue
        for o in prop.objects:
            if o.name in c.objects:
                c.objects.unlink(o)
    obj = instantiate_model(prop, prop.mumodelprops.name, loc, rot, scale)
    obj.muproperties.modelType = 'PROP'
    bpy.context.layer_collection.collection.objects.link(obj)
    obj.parent = parent
    return obj
