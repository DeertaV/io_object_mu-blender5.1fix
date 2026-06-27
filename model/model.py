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
import posixpath
from math import pi

import bpy
from mathutils import Vector, Quaternion

from ..import_mu import import_mu
from ..cfgnode import parse_vector
from ..utils import util_collection

def normalize_model_url(path, model):
    model = model.strip().replace("\\", "/")
    if model.lower().endswith(".mu"):
        model = model[:-3]
    if "/" not in model:
        model = "/".join((path, model))
    return posixpath.normpath(model).replace("\\", "/")

def compile_model(db, path, type, name, cfg, collection):
    nodes = cfg.GetNodes("MODEL")
    model = bpy.data.collections.new(f"{name}:{type}model")
    if nodes:
        root = bpy.data.objects.new(name+":model", None)
        model.objects.link(root)
        for n in nodes:
            submodelname = n.GetValue("model")
            position = Vector((0, 0, 0))
            rotation = Vector((0, 0, 0))
            scale = Vector((1, 1, 1))
            if n.HasValue("position"):
                position = parse_vector(n.GetValue("position"))
            if n.HasValue("rotation"):
                rotation = parse_vector(n.GetValue("rotation"))
            if n.HasValue("scale"):
                scale = parse_vector(n.GetValue("scale"))
            mdl = db.model(submodelname)
            obj = mdl.instantiate(f"{name}:submodel", position, rotation, scale)
            model.objects.link(obj)
            obj.parent = root
    else:
        if cfg.HasValue("mesh"):
            url = normalize_model_url(path, cfg.GetValue("mesh"))
        else:
            mesh = db.model_by_path[path][0]
            url = '/'.join((path, mesh))
        submodel = db.model(url)
        position = Vector((0, 0, 0))
        rotation = Vector((0, 0, 0))
        scale = Vector((1, 1, 1))
        root = submodel.instantiate(f"{name}:submodel", position, rotation, scale)
        model.objects.link(root)
    collection.children.link(model)
    model.mumodelprops.name = name
    model.mumodelprops.type = type
    return model

def loaded_models_collection():
    return util_collection("loaded_models")

def instantiate_model(model, name, loc, rot, scale):
    obj = bpy.data.objects.new(name, None)
    obj.instance_type = 'COLLECTION'
    obj.instance_collection = model
    obj.location = loc
    obj.scale = scale
    if type(rot) == Vector:
        # blender is right-handed, KSP is left-handed
        # FIXME: it might be better to convert the given euler rotation
        # to a quaternion (for consistency)
        # this assumes the rot vector came straight from a ksp cfg file
        # Unity's rotation order is ZXY, which makes it YXZ for blender
        obj.rotation_mode = 'YXZ'
        obj.rotation_euler = -rot.xzy * pi / 180
    else:
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = rot
    return obj

def copy_id_animation(id_data, action_map):
    if not id_data or not id_data.animation_data:
        return
    ad = id_data.animation_data
    if ad.action:
        if ad.action not in action_map:
            action_map[ad.action] = ad.action.copy()
        ad.action = action_map[ad.action]
    for track in ad.nla_tracks:
        for strip in track.strips:
            if strip.action:
                if strip.action not in action_map:
                    action_map[strip.action] = strip.action.copy()
                strip.action = action_map[strip.action]

def copy_material(mat, material_map, action_map):
    if mat not in material_map:
        material_map[mat] = mat.copy()
        copy_id_animation(material_map[mat], action_map)
    return material_map[mat]

def make_object_data_unique(obj, data_map, material_map, action_map):
    if obj.data:
        if obj.data not in data_map:
            data_map[obj.data] = obj.data.copy()
            copy_id_animation(data_map[obj.data], action_map)
            if hasattr(data_map[obj.data], "materials"):
                for i, mat in enumerate(data_map[obj.data].materials):
                    if mat:
                        data_map[obj.data].materials[i] = copy_material(
                            mat, material_map, action_map)
        obj.data = data_map[obj.data]
    copy_id_animation(obj, action_map)

def collection_roots(collection):
    objects = list(collection.all_objects)
    object_set = set(objects)
    return [obj for obj in objects if obj.parent not in object_set]

def link_object(collection, obj):
    if obj.name not in collection.objects:
        collection.objects.link(obj)

def copy_object_tree(source, collection, parent, state):
    obj = source.copy()
    state["object_map"][source] = obj
    link_object(collection, obj)
    obj.parent = parent
    obj.parent_type = source.parent_type
    obj.parent_bone = source.parent_bone
    obj.matrix_parent_inverse = source.matrix_parent_inverse.copy()

    if source.instance_type == 'COLLECTION' and source.instance_collection:
        obj.instance_type = 'NONE'
        obj.instance_collection = None
    else:
        make_object_data_unique(obj, state["data_map"], state["material_map"],
                                state["action_map"])

    if source.instance_type == 'COLLECTION' and source.instance_collection:
        for root in collection_roots(source.instance_collection):
            copy_object_tree(root, collection, obj, state)
    for child in source.children:
        copy_object_tree(child, collection, obj, state)
    return obj

def remap_object_references(objects, object_map):
    for obj in objects:
        for mod in obj.modifiers:
            if hasattr(mod, "object") and mod.object in object_map:
                mod.object = object_map[mod.object]
        for constraint in obj.constraints:
            if hasattr(constraint, "target") and constraint.target in object_map:
                constraint.target = object_map[constraint.target]
            if hasattr(constraint, "targets"):
                for target in constraint.targets:
                    if target.target in object_map:
                        target.target = object_map[target.target]

def realize_model_instance(instance, collection, parent=None):
    state = {
        "object_map": {},
        "data_map": {},
        "material_map": {},
        "action_map": {},
    }
    root = copy_object_tree(instance, collection, parent, state)
    remap_object_references(state["object_map"].values(), state["object_map"])
    return root

class Model:
    @classmethod
    def Preloaded(cls):
        preloaded = {}
        for g in bpy.data.collections:
            if g.name[:6] == "model:":
                url = g.name[6:]
                preloaded[url] = Model(None, url)
        return preloaded
    def __init__(self, path, url):
        modelname = "model:" + url
        if bpy.app.debug:
            print(modelname)
        loaded_models = loaded_models_collection()
        if modelname in loaded_models:
            model = loaded_models[modelname]
        else:
            model = bpy.data.collections.new(modelname)
            loaded_models.children.link(model)
            obj, mu = import_mu(model, path, False, False)
            obj.location = Vector((0, 0, 0))
            obj.rotation_quaternion = Quaternion((1,0,0,0))
            obj.scale = Vector((1,1,1))
        self.model = model
    def instantiate(self, name, loc, rot, scale):
        return instantiate_model(self.model, name, loc, rot, scale)
