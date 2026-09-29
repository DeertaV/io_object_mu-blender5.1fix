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
import json
from math import pi

import bpy
from mathutils import Vector, Quaternion

from ..import_mu import import_mu, MuImportError
from ..cfgnode import parse_vector
from ..utils import util_collection
from ..utils.import_assets import remap_assets, set_auxiliary_visibility, auxiliary
from ..utils.import_assets import data_snapshot, cleanup_new_data, capture_rest

def normalize_model_url(path, model):
    model = model.strip().strip('"\'').replace("\\", "/")
    if model.lower().endswith(".mu"):
        model = model[:-3]
    if "/" not in model:
        model = "/".join((path, model))
    return posixpath.normpath(model).replace("\\", "/")

def compile_model(db, path, type, name, cfg, collection, missing_models=None):
    nodes = cfg.GetNodes("MODEL")
    model = bpy.data.collections.new(f"{name}:{type}model")
    loaded_count = 0
    lookup_notes = []
    attempted_notes = []

    def lookup(url, legacy=False):
        attempted_notes.clear()
        resolver = getattr(db, 'resolve_model', None)
        if resolver:
            result = resolver(url, path, legacy, attempted_notes)
            lookup_notes.extend(note for note in attempted_notes if note.startswith('[resolved]'))
            return result
        return db.model(url)

    def missing(url, expected):
        exists = "yes" if os.path.isfile(expected) else "no"
        message = (f"{type} '{name}' (CFG directory: {path}): model '{url}' "
                   f"not found in GameData index; expected: {expected}; "
                   f"file exists: {exists}")
        if getattr(cfg, 'source_url', None):
            message += f'; CFG source: {cfg.source_url}'
        modules = [node.GetValue('name') for node in cfg.GetNodes('MODULE') if node.GetValue('name')]
        if modules:
            message += '; CFG MODULEs (not simulated): ' + ', '.join(modules)
        detail = [note for note in attempted_notes if not note.startswith('[resolved]')]
        if detail:
            message += '; ' + '; '.join(detail)
        if missing_models is None:
            for obj in list(model.objects):
                bpy.data.objects.remove(obj)
            bpy.data.collections.remove(model)
            raise MuImportError("Model", message)
        missing_models.append(message)

    if nodes:
        root = bpy.data.objects.new(name+":model", None)
        auxiliary(root, "模型根节点")
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
            mdl = lookup(submodelname)
            if mdl is None:
                url = (submodelname or "").strip().replace("\\", "/")
                if url.lower().endswith(".mu"):
                    url = url[:-3]
                expected = (os.path.join(db.root, url + ".mu").replace("\\", "/")
                            if url else "MODEL model value is empty")
                missing(submodelname, expected)
                continue
            if n.HasValue('texture'):
                from .appearance import model_texture_remaps, appearance_report
                appearance_notes = []
                template = model_texture_remaps(mdl.model, n, db, path, loaded_models_collection(), appearance_notes)
                appearance_report(name, path, appearance_notes)
                obj = instantiate_model(template, f"{name}:submodel", position, rotation, scale)
            else:
                obj = mdl.instantiate(f"{name}:submodel", position, rotation, scale)
            model.objects.link(obj)
            obj.parent = root
            loaded_count += 1
        if not loaded_count:
            bpy.data.objects.remove(root)
    else:
        if cfg.HasValue("mesh"):
            url = normalize_model_url(path, cfg.GetValue("mesh"))
        else:
            meshes = db.model_by_path.get(path, ())
            if not meshes and not hasattr(db, 'resolve_model'):
                missing("<default mesh>", os.path.join(
                    db.root, path, "*.mu").replace("\\", "/"))
                bpy.data.collections.remove(model)
                return None
            url = None if hasattr(db, 'resolve_model') else '/'.join((path, meshes[0]))
        submodel = lookup(url, legacy=True)
        if submodel is None:
            missing(url or '<default mesh>', os.path.join(db.root, (url + '.mu') if url else path + '/*.mu').replace("\\", "/"))
            bpy.data.collections.remove(model)
            return None
        position = Vector((0, 0, 0))
        rotation = Vector((0, 0, 0))
        scale = Vector((1, 1, 1))
        root = submodel.instantiate(f"{name}:submodel", position, rotation, scale)
        model.objects.link(root)
        loaded_count = 1
    if not loaded_count:
        bpy.data.collections.remove(model)
        return None
    collection.children.link(model)
    model.mumodelprops.name = name
    model.mumodelprops.type = type
    model['ksp_lookup_notes'] = '\n'.join(f"{type} '{name}' (CFG directory: {path}): {note}" for note in lookup_notes)
    return model

def loaded_models_collection():
    return util_collection("loaded_models")

def instantiate_model(model, name, loc, rot, scale):
    obj = bpy.data.objects.new(name, None)
    auxiliary(obj, "模型实例")
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
        # Material.copy duplicates its node tree but driver targets still refer
        # to the original Material ID unless explicitly remapped.
        tree = material_map[mat].node_tree
        if tree and tree.animation_data:
            for fc in tree.animation_data.drivers:
                for variable in fc.driver.variables:
                    for target in variable.targets:
                        if target.id == mat:
                            target.id = material_map[mat]
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
    if source.get("ksp_auxiliary"):
        set_auxiliary_visibility(obj, source.get("ksp_aux_visible", False))

    if source.instance_type == 'COLLECTION' and source.instance_collection:
        obj.instance_type = 'NONE'
        obj.instance_collection = None
    else:
        make_object_data_unique(obj, state["data_map"], state["material_map"],
                                state["action_map"])

    if source.instance_type == 'COLLECTION' and source.instance_collection:
        scope = {"object_map": {}, "data_map": {}, "material_map": {}, "action_map": {},
                 "scopes": state["scopes"]}
        state["scopes"].append(scope)
        for root in collection_roots(source.instance_collection):
            copy_object_tree(root, collection, obj, scope)
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
        if obj.pose:
            for bone in obj.pose.bones:
                for constraint in bone.constraints:
                    if hasattr(constraint, "target") and constraint.target in object_map:
                        constraint.target = object_map[constraint.target]
                    if hasattr(constraint, "targets"):
                        for target in constraint.targets:
                            if target.target in object_map:
                                target.target = object_map[target.target]

def realize_model_instance(instance, collection, parent=None):
    snapshot = data_snapshot()
    state = {
        "object_map": {},
        "data_map": {},
        "material_map": {},
        "action_map": {},
        "scopes": [],
    }
    try:
        root = copy_object_tree(instance, collection, parent, state)
        for scope in [state] + state["scopes"]:
            remap_object_references(scope["object_map"].values(), scope["object_map"])
            remap_assets(scope)
    except Exception:
        for scope in [state] + state["scopes"]:
            for obj in list(scope["object_map"].values()):
                bpy.data.objects.remove(obj, do_unlink=True)
            for action in scope["action_map"].values():
                action.use_fake_user = False
                if not action.users:
                    bpy.data.actions.remove(action)
        cleanup_new_data(snapshot)
        raise
    return root

def model_source(collection):
    source = collection.get('ksp_model_source', '')
    if not source:
        source = next((o.ksp_assets.source for o in collection.all_objects
                       if o.ksp_assets.source.lower().endswith('.mu')), '')
    return os.path.abspath(source).replace('\\', '/') if source else ''


def model_stamp(path):
    try:
        stat = os.stat(path)
        return json.dumps([stat.st_size, stat.st_mtime_ns])
    except OSError:
        return ''


class Model:
    @classmethod
    def Preloaded(cls, root=None):
        preloaded = {}
        for g in bpy.data.collections:
            if g.name[:6] == "model:":
                source = model_source(g)
                if root and (not source or not source.casefold().startswith(root.casefold() + '/')
                             or not model_stamp(source)):
                    continue
                if g.get('ksp_model_stamp') and g.get('ksp_model_stamp') != model_stamp(source):
                    continue
                if g.get('ksp_import_pipeline') != '0.11.5':
                    continue
                url = g.get('ksp_model_url', g.name[6:])
                item = cls.__new__(cls)
                item.model = g
                preloaded[url] = item
        return preloaded
    def __init__(self, path, url):
        modelname = "model:" + url
        if bpy.app.debug:
            print(modelname)
        loaded_models = loaded_models_collection()
        source = os.path.abspath(path).replace('\\', '/') if path else ''
        cached = next((g for g in bpy.data.collections
                       if g.name.startswith('model:') and g.get('ksp_model_url', g.name[6:]) == url
                       and g.get('ksp_import_pipeline') == '0.11.5'
                       and (not source or (model_source(g).casefold() == source.casefold()
                            and (not g.get('ksp_model_stamp') or g.get('ksp_model_stamp') == model_stamp(source))))), None)
        if cached:
            model = cached
        else:
            model = bpy.data.collections.new(modelname)
            loaded_models.children.link(model)
            obj, mu = import_mu(model, path, False, False, force_mesh=True)
            obj.location = Vector((0, 0, 0))
            obj.rotation_quaternion = Quaternion((1,0,0,0))
            obj.scale = Vector((1,1,1))
            # Cached parts normalize the placement transform. Their static
            # fallback must use that normalized pose rather than file placement.
            for clip in obj.ksp_assets.clips:
                for binding in clip.bindings:
                    if binding.object == obj:
                        binding.rest = capture_rest(obj, binding.action)
            model['ksp_model_source'] = source
            model['ksp_model_url'] = url
            model['ksp_model_stamp'] = model_stamp(source)
            model['ksp_import_pipeline'] = '0.11.5'
        self.model = model
    def instantiate(self, name, loc, rot, scale):
        return instantiate_model(self.model, name, loc, rot, scale)
