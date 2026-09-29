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
import os
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty

from .exception import MuImportError
from .import_mu import import_mu
from ..utils import rename_import_hierarchy, rename_import_collection
from ..utils.import_assets import uid, auxiliary, collect_clips, data_snapshot, cleanup_new_data

def import_mu_op(self, context, filepath, create_colliders, force_armature,
                 force_mesh, mute_imported_animations, clean_import_names):
    operator = self
    undo = bpy.context.preferences.edit.use_global_undo
    bpy.context.preferences.edit.use_global_undo = False

    snapshot = data_snapshot()
    collection = bpy.data.collections.new(os.path.basename(filepath))
    bpy.context.layer_collection.collection.children.link(collection)
    try:
        ret = import_mu(collection, filepath, create_colliders, force_armature,
                        force_mesh, mute_imported_animations)
    except MuImportError as e:
        for imported in list(collection.objects):
            bpy.data.objects.remove(imported, do_unlink=True)
        bpy.data.collections.remove(collection)
        cleanup_new_data(snapshot)
        operator.report({'ERROR'}, e.message)
        return {'CANCELLED'}
    else:
        obj, mu = ret
        if clean_import_names:
            rename_import_collection(collection, filepath, prefix="导入集合")
            rename_import_hierarchy(obj, filepath)
        # Placement is not an animated game transform: retain the imported
        # local hierarchy below an independent anchor at the user's cursor.
        anchor = bpy.data.objects.new(os.path.splitext(os.path.basename(filepath))[0] + "：导入定位", None)
        collection.objects.link(anchor)
        anchor["ksp_model_root"] = True
        anchor["ksp_instance_root"] = True
        anchor["ksp_original_name"] = "ksp_import_anchor"
        anchor.ksp_assets.uid = uid()
        anchor.ksp_assets.source = filepath
        auxiliary(anchor, "导入定位根节点")
        anchor.location = context.scene.cursor.location
        obj.parent = anchor
        obj = anchor
        if collect_clips(obj):
            obj.ksp_assets.clip_choice = '0'
        for o in bpy.context.scene.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = obj
        context.view_layer.update()
        obj.select_set(True)
        for m in mu.messages:
            operator.report(m[0], m[1])
        return {'FINISHED'}
    finally:
        bpy.context.preferences.edit.use_global_undo = undo

class KSPMU_OT_ImportMu(bpy.types.Operator, ImportHelper):
    '''Load a KSP Mu (.mu) File'''
    bl_idname = "import_object.ksp_mu"
    bl_label = "导入 Mu"
    bl_description = """导入 KSP .mu 模型。"""
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".mu"
    filter_glob: StringProperty(default="*.mu", options={'HIDDEN'})

    create_colliders: BoolProperty(name="创建碰撞体",
            description="关闭后只导入可见模型和层级",
                                    default=False, options={'HIDDEN'})
    force_armature: BoolProperty(name="强制骨架",
            description="仅保留旧接口兼容；只读取源文件实际骨架", default=False, options={'HIDDEN'})
    force_mesh: BoolProperty(name="强制不可见网格",
            description="为没有 renderer 的对象也创建网格对象", default=True)
    mute_imported_animations: BoolProperty(
            name="动画先不接入时间线",
            description="保留动画资源，不自动接入时间线；需要时在 KSP 页面加入所选区间",
            default=True)
    clean_import_names: BoolProperty(
            name="整理导入命名",
            description="使用中文类型前缀整理 Blender 显示名，并保留原始 KSP 名用于导出",
            default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        keywords = self.as_keywords (ignore=("filter_glob",
                                             "axis_forward", "axis_up"))
        return import_mu_op(self, context, **keywords)
