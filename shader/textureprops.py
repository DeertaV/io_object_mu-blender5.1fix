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

import sys, traceback
from struct import unpack
from pprint import pprint

import bpy
from mathutils import Vector
from bpy.props import BoolProperty, StringProperty
from bpy.props import CollectionProperty
from bpy.props import FloatVectorProperty, IntProperty

def texture_update_mapping(self, context):
    if not hasattr(context, "material") or not context.material:
        return
    mat = context.material
    nodes = mat.node_tree.nodes
    scale = Vector(self.scale)
    offset = Vector(self.offset)
    image_convertNorm = False
    if self.name in nodes:
        img = bpy.data.images.get(self.get('blender_image_name', self.tex))
        if img:
            if img.muimageprop.invertY:
                scale.y *= -1
                offset.y = 1 - offset.y
            image_convertNorm = img.muimageprop.convertNorm
        nodes[self.name].texture_mapping.translation.xy = offset
        nodes[self.name].texture_mapping.scale.xy = scale
        mapping = nodes.get(self.name + ' UV Transform')
        vector = nodes[self.name].inputs.get('Vector')
        if not mapping and vector and vector.is_linked and vector.links[0].from_node.type == 'MAPPING':
            mapping = vector.links[0].from_node
        if mapping:
            if len(mapping.outputs[0].links) > 1:
                # Identical transforms share one node by default. Editing one
                # texture's source transform must not shift the others.
                original = mapping
                mapping = nodes.new('ShaderNodeMapping')
                mapping.name = self.name + ' UV Transform'
                mapping.vector_type = original.vector_type
                mapping.location = original.location
                for name in ('Location', 'Rotation', 'Scale'):
                    mapping.inputs[name].default_value = original.inputs[name].default_value
                mat.node_tree.links.new(original.inputs['Vector'].links[0].from_socket, mapping.inputs['Vector'])
                mat.node_tree.links.new(mapping.outputs['Vector'], vector)
            mapping.inputs['Scale'].default_value = (*scale, 1)
            mapping.inputs['Location'].default_value = (*offset, 0)
        elif vector and (tuple(scale) != (1, 1) or tuple(offset) != (0, 0)):
            source = vector.links[0].from_socket if vector.is_linked else None
            if source is None:
                uv = next((n for n in nodes if n.type == 'UVMAP'), None) or nodes.new('ShaderNodeUVMap')
                source = uv.outputs['UV']
            mapping = nodes.new('ShaderNodeMapping')
            mapping.name = self.name + ' UV Transform'
            mapping.vector_type = 'POINT'
            mapping.inputs['Scale'].default_value = (*scale, 1)
            mapping.inputs['Location'].default_value = (*offset, 0)
            mat.node_tree.links.new(source, mapping.inputs['Vector'])
            mat.node_tree.links.new(mapping.outputs['Vector'], vector)
    #if "dxtNormal" in nodes:
    #    dxtNormal = nodes["dxtNormal"]
    #    fac = float(image_convertNorm or not self.rgbNorm)
    #    dxtNormal.inputs[0].default_value = fac

def texture_update_tex(self, context):
    if not hasattr(context, "material") or not context.material:
        return
    mat = context.material
    nodes = mat.node_tree.nodes
    image = bpy.data.images.get(self.get('blender_image_name', self.tex))
    if self.name in nodes and image:
        nodes[self.name].image = image

class MuTextureProperties(bpy.types.PropertyGroup):
    tex: StringProperty(name="tex", update=texture_update_tex)
    type: BoolProperty(name="type", description="Texture is a normal map", default = False, update=texture_update_tex)
    rgbNorm: BoolProperty(name="RGB Normal", description="Texture is RGB rather than GA (blender shader control, not exported)", update=texture_update_mapping)
    scale: FloatVectorProperty(name="scale", size = 2, subtype='XYZ', default = (1.0, 1.0), update=texture_update_mapping)
    offset: FloatVectorProperty(name="offset", size = 2, subtype='XYZ', default = (0.0, 0.0), update=texture_update_mapping)

class MuMaterialTexturePropertySet(bpy.types.PropertyGroup):
    bl_label = "Textures"
    properties: CollectionProperty(type=MuTextureProperties, name="Textures")
    index: IntProperty()
    expanded: BoolProperty()

    def draw_item(self, layout):
        item = self.properties[self.index]
        row = layout.row()
        col = row.column()
        col.prop(item, "name", text="Name")
        r = col.row()
        r.prop(item, "tex", text="")
        r.prop(item, "type", text="")
        r.prop(item, "rgbNorm", text="")
        col.prop(item, "scale", text="")
        col.prop(item, "offset", text="")

classes_to_register = (
    MuTextureProperties,
    MuMaterialTexturePropertySet,
)
