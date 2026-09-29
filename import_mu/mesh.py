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

import bpy
import bmesh

from ..mu import MuMesh, MuSkinnedMeshRenderer, MuCollider_Base
from ..utils import create_data_object

from .armature import create_vertex_groups, create_armature_modifier
from .armature import create_bindPose
from ..utils.blender_compat import enable_custom_normals

def attach_material(mesh, renderer, mu):
    if mu.materials and renderer.materials:
        slots = {}
        for slot, index in enumerate(renderer.materials):
            if 0 <= index < len(mu.materials):
                slots[slot] = len(mesh.materials)
                mesh.materials.append(mu.materials[index].material)
            else:
                mu.data_issues.append(f"Invalid material index {index}: {mesh.name}")
        for polygon in mesh.polygons:
            polygon.material_index = slots.get(polygon.material_index, 0)

def create_uvs(mu, uvs, mesh, name):
    uv_layer = mesh.uv_layers.new(name=name).data
    for i, loop in enumerate(mesh.loops):
        uv_layer[i].uv = uvs[loop.vertex_index]

def create_normals(mu, normals, mesh):
    custom_normals = [None] * len(mesh.loops)
    for i, loop in enumerate(mesh.loops):
        custom_normals[i] = normals[loop.vertex_index]
    mesh.normals_split_custom_set(custom_normals)
    enable_custom_normals(mesh)

def create_mesh(mu, mumesh, name):
    mesh = bpy.data.meshes.new(name)
    faces = []
    for sm in mumesh.submeshes:
        faces.extend(sm)
    mesh.from_pydata(mumesh.verts, [], faces)
    offset = 0
    for slot, submesh in enumerate(mumesh.submeshes):
        for polygon in mesh.polygons[offset:offset + len(submesh)]:
            polygon.material_index = slot
        offset += len(submesh)
    if mumesh.uvs:
        create_uvs(mu, mumesh.uvs, mesh, "UVMap")
    if mumesh.uv2s:
        create_uvs(mu, mumesh.uv2s, mesh, "UVMap2")
    if mumesh.normals:
        create_normals(mu, mumesh.normals, mesh)
    if len(mumesh.colors) == len(mumesh.verts):
        colors = mesh.color_attributes.new(name="KSP Vertex Color", type='FLOAT_COLOR', domain='CORNER')
        for loop in mesh.loops:
            colors.data[loop.index].color = mumesh.colors[loop.vertex_index]
    if len(mumesh.tangents) == len(mumesh.verts):
        tangent = mesh.attributes.new(name="ksp_source_tangent", type='FLOAT_VECTOR', domain='POINT')
        sign = mesh.attributes.new(name="ksp_source_tangent_sign", type='FLOAT', domain='POINT')
        for index, value in enumerate(mumesh.tangents):
            tangent.data[index].vector = value[:3]
            sign.data[index].value = value[3]
        mu.data_issues.append(f"Source tangents retained as mesh attributes: {name}")
    #FIXME how to set tangents?
    #if mumesh.tangents:
    #    for i, t in enumerate(mumesh.tangents):
    #        bv[i].tangent = t
    return mesh

def mesh_post(obj, renderer):
    obj.muproperties.castShadows = renderer.castShadows
    obj.muproperties.receiveShadows = renderer.receiveShadows

def create_mesh_component(mu, muobj, mumesh, name):
    # Unity often exports both a collider component AND its MeshFilter.  Turning
    # off the collider handler alone used to leave that second white mesh behind.
    # Component identity (not COL-like names) distinguishes collision-only nodes.
    if not hasattr(muobj, 'renderer') and any(isinstance(c, MuCollider_Base)
                                             for c in muobj.components):
        mu.data_issues.append(f"Collision-only MeshFilter omitted; transform retained: {muobj.path}")
        return None
    if not mu.force_mesh and not hasattr(muobj, "renderer"):
        return None
    mesh = create_mesh (mu, mumesh, name)
    if hasattr(muobj, "renderer"):
        attach_material(mesh, muobj.renderer, mu)
        return "mesh", mesh, None, (mesh_post, muobj.renderer)
    else:
        return "mesh", mesh, None

def create_skinned_mesh_component(mu, muobj, skin, name):
    create_bindPose(mu, muobj, skin)
    mesh = create_mesh(mu, skin.mesh, name)
    obj = create_data_object(mu.collection, name + ".skin", mesh, None)
    create_vertex_groups(obj, skin.bones, skin.mesh.boneWeights)
    attach_material(mesh, skin, mu)
    obj.parent = skin.bindPose_obj
    create_armature_modifier(obj, "BindPose", skin.bindPose_obj)
    return "armature", skin.bindPose_obj, None
    #return None

type_handlers = {
    MuMesh: create_mesh_component,
    MuSkinnedMeshRenderer: create_skinned_mesh_component
}
