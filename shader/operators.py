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
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty
from bl_operators.presets import AddPresetBase
from .shader_extract import record_material
from .shader import create_nodes, ensure_principled_preview
from .preview_layout import arrange_nodes, copy_preview_tree


def active_material(context):
    return getattr(context, 'material', None) or getattr(getattr(context, 'active_object', None), 'active_material', None)


class KSPMU_OT_PreviewArrange(bpy.types.Operator):
    bl_idname = 'material.ksp_preview_arrange'
    bl_label = '整理当前材质节点'
    bl_description = '只调整位置和显示尺寸，不重建节点、不改变连接、驱动、动画或材质内容'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mat = active_material(context)
        return bool(mat and mat.node_tree)

    def execute(self, context):
        arrange_nodes(active_material(context).node_tree)
        return {'FINISHED'}


class KSPMU_OT_PreviewSimplify(bpy.types.Operator):
    bl_idname = 'material.ksp_preview_simplify'
    bl_label = '精简当前 KSP 材质'
    bl_description = '保留一份原材质备份，再依据 KSP 源参数重建精简节点；材质源动画保留，手工节点编辑留在备份中'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mat = active_material(context)
        return bool(mat and mat.get('ksp_imported_material') and not mat.library)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        mat = active_material(context)
        self.layout.label(text='当前材质：' + mat.name)
        self.layout.label(text='先保留原节点备份，再按 KSP 源参数重建。')
        self.layout.label(text='手工节点编辑留在备份；源材质动画不会删除。')
        self.layout.label(text='使用同一材质的网格都会更新；其他材质不改。')

    def execute(self, context):
        mat = active_material(context)
        # Build and validate off to the side BEFORE touching the current graph.
        from ..model.model import copy_material
        from ..utils.import_assets import data_snapshot, cleanup_new_data
        snapshot = data_snapshot()
        working = copy_material(mat, {}, {})
        try:
            ensure_principled_preview(working)
        except Exception as exc:
            bpy.data.materials.remove(working)
            cleanup_new_data(snapshot)
            self.report({'ERROR'}, f'精简失败，当前材质保持不变：{exc}')
            return {'CANCELLED'}
        backup = copy_material(mat, {}, {})
        backup.name = mat.name + ' · 精简前备份'
        backup.use_fake_user = True
        backup['ksp_preview_backup_of'] = mat.name
        mat['ksp_preview_backup'] = backup.name
        mat.use_nodes = True
        copy_preview_tree(working, mat)
        mat.surface_render_method = working.surface_render_method
        mat.diffuse_color = working.diffuse_color
        mat['ksp_preview_version'] = 2
        bpy.data.materials.remove(working)
        snapshot['materials'].add(backup.as_pointer())
        cleanup_new_data(snapshot)
        self.report({'INFO'}, f'当前材质已精简为 {len(mat.node_tree.nodes)} 个外层节点；原节点备份：{backup.name}')
        return {'FINISHED'}

class KSPMU_OT_MuShaderPropExpand(bpy.types.Operator):
    '''Expand/collapse mu shader property set'''
    bl_idname = "object.mushaderprop_expand"
    bl_label = "Mu shader prop expand"
    propertyset: StringProperty()
    def execute(self, context):
        matprops = context.material.mumatprop
        propset = getattr(matprops, self.propertyset)
        propset.expanded = not propset.expanded
        return {'FINISHED'}


class KSPMU_OT_MuShaderPropAdd(bpy.types.Operator):
    '''Add a mu shader property'''
    bl_idname = "object.mushaderprop_add"
    bl_label = "Mu shader prop Add"
    propertyset: StringProperty()
    def execute(self, context):
        matprops = context.material.mumatprop
        propset = getattr(matprops, self.propertyset)
        prop = propset.properties.add()
        prop.name = "New Property"
        for i, p in enumerate(propset.properties):
            if p == prop:
                propset.index = i
                break
        return {'FINISHED'}

class KSPMU_OT_MuShaderPropRemove(bpy.types.Operator):
    '''Remove a mu shader property'''
    bl_idname = "object.mushaderprop_remove"
    bl_label = "Mu shader prop Remove"
    propertyset: StringProperty()
    def execute(self, context):
        matprops = context.material.mumatprop
        propset = getattr(matprops, self.propertyset)
        if propset.index >= 0:
            propset.properties.remove(propset.index)
        return {'FINISHED'}

class IO_OBJECT_MU_OT_shader_presets(AddPresetBase, bpy.types.Operator):
    bl_idname = "io_object_mu.shader_presets"
    bl_label = "Shaders"
    bl_description = "Mu Shader Presets"
    preset_menu = "IO_OBJECT_MU_MT_shader_presets"
    preset_subdir = "io_object_mu/shaders"

    preset_defines = [
        "mat = bpy.context.material.mumatprop"
        ]
    preset_values = [
        "mat.name",
        "mat.shaderName",
        "mat.color",
        "mat.vector",
        "mat.float2",
        "mat.float3",
        "mat.texture",
        ]

def export_material(operator, context, filepath):
    mat = context.material
    matnode = record_material(mat)
    of = open(filepath,"wt")
    of.write("shader " + matnode.ToString())
    return {'FINISHED'}

class IO_OBJECT_MU_OT_shader_rebuild(bpy.types.Operator):
    '''Rebuild the material node tree'''
    bl_idname = "io_object_mu.shader_rebuild"
    bl_label = "Rebuild Shader"

    @classmethod
    def poll(cls, context):
        return hasattr(context, "material") and context.material != None

    def execute(self, context):
        create_nodes(context.material)
        return {'FINISHED'}

class IO_OBJECT_MU_OT_shader_export(bpy.types.Operator, ExportHelper):
    '''Save a material as a .cfg file'''
    bl_idname = "export_material.ksp_cfg"
    bl_label = "Export Material"

    filename_ext = ".cfg"
    filter_glob: StringProperty(default="*.cfg", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return hasattr(context, "material") and context.material != None

    def execute(self, context):
        keywords = self.as_keywords (ignore=("check_existing", "filter_glob",
                                             "axis_forward", "axis_up"))
        return export_material(self, context, **keywords)

classes_to_register = (
    KSPMU_OT_PreviewArrange,
    KSPMU_OT_PreviewSimplify,
    KSPMU_OT_MuShaderPropExpand,
    KSPMU_OT_MuShaderPropAdd,
    KSPMU_OT_MuShaderPropRemove,
    IO_OBJECT_MU_OT_shader_presets,
    IO_OBJECT_MU_OT_shader_rebuild,
    IO_OBJECT_MU_OT_shader_export,
)
