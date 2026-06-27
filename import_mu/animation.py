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

import re
import bpy
from mathutils import Vector, Quaternion
from math import pi
from .light import light_power
from ..utils.blender_compat import ensure_action_fcurve

#mess with the heads of 6.28... fans :P
tau = pi / 180

property_map = {
    "m_LocalPosition.x": ("obj", "location", 0, 1, 3),
    "m_LocalPosition.y": ("obj", "location", 2, 1, 3),
    "m_LocalPosition.z": ("obj", "location", 1, 1, 3),
    "m_LocalRotation.x": ("obj", "rotation_quaternion", 1, -1, 4),
    "m_LocalRotation.y": ("obj", "rotation_quaternion", 3, -1, 4),
    "m_LocalRotation.z": ("obj", "rotation_quaternion", 2, -1, 4),
    "m_LocalRotation.w": ("obj", "rotation_quaternion", 0, 1, 4),
    "m_LocalScale.x": ("obj", "scale", 0, 1, 3),
    "m_LocalScale.y": ("obj", "scale", 2, 1, 3),
    "m_LocalScale.z": ("obj", "scale", 1, 1, 3),
    "localEulerAnglesRaw.x": ("obj", "rotation_euler", 0, -tau, 3),
    "localEulerAnglesRaw.y": ("obj", "rotation_euler", 2, -tau, 3),
    "localEulerAnglesRaw.z": ("obj", "rotation_euler", 1, -tau, 3),
    "m_Intensity": ("data", "energy", 0, light_power),
    "m_Color.r": ("data", "color", 0, 1),
    "m_Color.g": ("data", "color", 1, 1),
    "m_Color.b": ("data", "color", 2, 1),
    "m_Color.a": ("data", "color", 3, 1),
}

vector_map = {
    "r": 0, "g": 1, "b": 2, "a":3,
    "x": 0, "y": 1, "z": 2, "w":3,  # shader props not read as quaternions
}

SUFFIX_RE = re.compile(r"( \(\d+\)|\.\d{3})$")

def debug_print(message):
    if bpy.app.debug:
        print(message)

def property_index(properties, prop):
    for i, p in enumerate(properties):
        if p.name == prop:
            return i
    return None

def strip_name_suffix(name):
    return SUFFIX_RE.sub("", name)

def normalize_path_suffixes(path):
    return "/".join(strip_name_suffix(part) for part in path.split("/"))

def path_in_subtree(candidate, root):
    return not root or candidate == root or candidate.startswith(root + "/")

def resolve_object_path(mu, root_path, object_path):
    if object_path in mu.object_paths:
        return object_path

    normalized_path = normalize_path_suffixes(object_path)
    if normalized_path in mu.object_paths:
        return normalized_path

    matches = [
        path for path in mu.object_paths
        if (path_in_subtree(path, root_path)
            and normalize_path_suffixes(path) == normalized_path)
    ]
    if len(matches) == 1:
        return matches[0]

    target_name = strip_name_suffix(object_path.rsplit("/", 1)[-1])
    matches = [
        path for path in mu.object_paths
        if (path_in_subtree(path, root_path)
            and strip_name_suffix(path.rsplit("/", 1)[-1]) == target_name)
    ]
    if len(matches) == 1:
        return matches[0]
    return None

def shader_property_on_mesh(obj, prop):
    if not obj or type(obj.data) != bpy.types.Mesh:
        return None
    if not obj.data.materials:
        return None
    for mat in obj.data.materials:
        mumat = mat.mumatprop
        for subpath in ["color", "vector", "float2", "float3", "texture"]:
            propset = getattr(mumat, subpath)
            propIndex = property_index(propset.properties, prop[0])
            if propIndex is None:
                continue
            if subpath == "texture":
                print("animated texture properties not yet supported")
                print(prop)
                return None
            if subpath[:5] == "float":
                rnaIndex = 0
            else:
                if len(prop) < 2 or prop[1] not in vector_map:
                    return None
                rnaIndex = vector_map[prop[1]]
            path = "mumatprop.%s.properties[%d].value" % (subpath, propIndex)
            return mat, path, rnaIndex
    return None

def iter_child_objects(obj):
    for child in obj.children:
        yield child
        yield from iter_child_objects(child)

def shader_property(obj, prop):
    prop = prop.split(".")
    sp = shader_property_on_mesh(obj, prop)
    if sp:
        return sp

    matches = []
    for child in iter_child_objects(obj):
        sp = shader_property_on_mesh(child, prop)
        if sp:
            matches.append(sp)
    if len(matches) == 1:
        return matches[0]
    return None

def create_fcurve(action, datablock, curve, propmap):
    dp, ind, mult = propmap
    fps = bpy.context.scene.render.fps
    fc = ensure_action_fcurve(action, datablock, dp, ind)
    fc.keyframe_points.add(len(curve.keys))
    for i, key in enumerate(curve.keys):
        x,y = key.time * fps + bpy.context.scene.frame_start, key.value * mult
        fc.keyframe_points[i].co = x, y
        fc.keyframe_points[i].handle_left_type = 'FREE'
        fc.keyframe_points[i].handle_right_type = 'FREE'
        if i > 0:
            dist = (key.time - curve.keys[i - 1].time) / 3
            dx, dy = dist * fps, key.tangent[0] * dist * mult
        else:
            dx, dy = 10, 0.0
        fc.keyframe_points[i].handle_left = x - dx, y - dy
        if i < len(curve.keys) - 1:
            dist = (curve.keys[i + 1].time - key.time) / 3
            dx, dy = dist * fps, key.tangent[1] * dist * mult
        else:
            dx, dy = 10, 0.0
        fc.keyframe_points[i].handle_right = x + dx, y + dy
    return fc

def create_enabled_fcurves(action, obj, curve):
    fps = bpy.context.scene.render.fps
    fcurves = []
    for data_path in ("hide_viewport", "hide_render"):
        fc = ensure_action_fcurve(action, obj, data_path, None)
        fc.keyframe_points.add(len(curve.keys))
        for i, key in enumerate(curve.keys):
            x = key.time * fps + bpy.context.scene.frame_start
            y = 0.0 if key.value > 0.5 else 1.0
            fc.keyframe_points[i].co = x, y
            fc.keyframe_points[i].interpolation = 'CONSTANT'
        fcurves.append(fc)
    return fcurves

def create_action(mu, path, clip):
    #print(clip.name)
    actions = {}
    bones = set()
    for curve in clip.curves:
        if not curve.keys:
            continue
        if not curve.path:
            mu_path = path
        else:
            mu_path = "/".join([path, curve.path])
        resolved_path = resolve_object_path(mu, path, mu_path)
        if not resolved_path:
            if mu_path not in mu.bad_paths:
                mu.bad_paths.add(mu_path)
                print("Unknown path: %s" % (mu_path))
            continue
        mu_path = resolved_path
        muobj = mu.object_paths[mu_path]
        dppref = ""
        if hasattr(muobj, "bone"):
            obj = muobj.armature.armature_obj
            dppref = f'pose.bones["{muobj.bone}"].'
        elif hasattr(muobj, "bobj"):
            obj = muobj.bobj
        else:
            print("No blender object at path: %s" % (mu_path))
            continue

        if curve.property[:-2] == "localEulerAnglesRaw":
            obj.rotation_mode = 'YXZ'
        if curve.property == "m_Enabled":
            name = ".".join([obj.name, "visibility"])
            actpath = "/".join([curve.path, name])
            if actpath not in actions:
                actions[actpath] = bpy.data.actions.new(name), obj
            act, obj = actions[actpath]
            create_enabled_fcurves(act, obj, curve)
            continue
        if curve.property not in property_map:
            sp = shader_property(obj, curve.property)
            if not sp:
                print("%s: Unknown property: %s" % (mu_path, curve.property))
                continue
            obj, dp, rnaIndex = sp
            propmap = dp, rnaIndex, 1
            subpath = "obj"
        else:
            propmap = property_map[curve.property]
            subpath, propmap = propmap[0], propmap[1:]
        fullpropmap = (dppref + propmap[0],) +  propmap[1:3]

        objname = ".".join([obj.name, subpath])

        if subpath != "obj":
            obj = getattr (obj, subpath)

        name = objname
        actpath = "/".join([curve.path, name])
        if actpath not in actions:
            actions[actpath] = bpy.data.actions.new(name), obj
        act, obj = actions[actpath]
        fcurve = create_fcurve(act, obj, curve, fullpropmap)
        if hasattr(muobj, "bone"):
            if not hasattr(muobj, "fcurves"):
                muobj.fcurves = {}
            if propmap[0] not in muobj.fcurves:
                muobj.fcurves[propmap[0]] = [None] * propmap[3]
            muobj.fcurves[propmap[0]][propmap[1]] = fcurve
            bones.add(muobj)
    for muobj in bones:
        xform = muobj.transform
        rrot = muobj.relRotation
        if "location" in muobj.fcurves:
            location = muobj.fcurves["location"]
            lloc = Vector(muobj.transform.localPosition)
            if None in location:
                debug_print("Skipping incomplete location fcurve set")
            elif ((len(location[0].keyframe_points)
                  != len(location[1].keyframe_points))
                  or (len(location[0].keyframe_points)
                      != len(location[2].keyframe_points))):
                debug_print("Skipping mismatched location fcurve set")
            else:
                for i in range(len(location[0].keyframe_points)):
                    def transformkey(kval):
                        xk = getattr(location[0].keyframe_points[i], kval)
                        yk = getattr(location[1].keyframe_points[i], kval)
                        zk = getattr(location[2].keyframe_points[i], kval)
                        loc = Vector((xk.y, yk.y, zk.y))
                        loc = rrot @ (loc - lloc)
                        (xk.y, yk.y, zk.y) = loc
                    transformkey("co")
                    transformkey("handle_left")
                    transformkey("handle_right")
        if "rotation_quaternion" in muobj.fcurves:
            rotation = muobj.fcurves["rotation_quaternion"]
            lrot = Quaternion(muobj.transform.localRotation).inverted()
            if None in rotation:
                debug_print("Skipping incomplete rotation fcurve set")
            elif ((len(rotation[0].keyframe_points)
                  != len(rotation[1].keyframe_points))
                  or (len(rotation[0].keyframe_points)
                      != len(rotation[2].keyframe_points))
                  or (len(rotation[0].keyframe_points)
                      != len(rotation[3].keyframe_points))):
                debug_print("Skipping mismatched rotation fcurve set")
            else:
                for i in range(len(rotation[0].keyframe_points)):
                    def rotkey(kval):
                        wk = getattr(rotation[0].keyframe_points[i], kval)
                        xk = getattr(rotation[1].keyframe_points[i], kval)
                        yk = getattr(rotation[2].keyframe_points[i], kval)
                        zk = getattr(rotation[3].keyframe_points[i], kval)
                        q = Quaternion((wk.y, xk.y, yk.y, zk.y))
                        q = lrot @ q
                        (wk.y, xk.y, yk.y, zk.y) = q
                    rotkey("co")
                    rotkey("handle_left")
                    rotkey("handle_right")
    for name in actions:
        act, obj = actions[name]
        if not obj.animation_data:
            obj.animation_data_create()
        track = obj.animation_data.nla_tracks.new()
        track.name = clip.name
        track.strips.new(act.name, 1, act)

def create_object_paths(mu):
    def recurse (mu, obj, parent_names, parent):
        obj.parent = parent
        obj.mu = mu
        name = obj.transform.name
        parent_names.append(name)
        obj.path = "/".join(parent_names)
        mu.objects[name] = obj
        mu.object_paths[obj.path] = obj
        for child in obj.children:
            recurse(mu, child, parent_names, obj)
        parent_names.pop()
    mu.objects = {}
    mu.object_paths = {}
    mu.bad_paths = set()
    recurse(mu, mu.obj, [], None)
