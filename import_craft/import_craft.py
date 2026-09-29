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
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty

from ..import_mu import MuImportError
from ..cfgnode import ConfigNode, ConfigNodeError
from ..cfgnode import parse_vector, parse_quaternion
from ..preferences import Preferences
from ..utils import util_collection, rename_import_collection
from ..utils import rename_import_hierarchy, rename_single_import_object
from ..utils import safe_display_base
from ..utils.import_assets import auxiliary
from ..model import realize_model_instance

from .gamedata import GameData, gamedata, game_data_root, database_report

def craft_collection():
    return util_collection("craft_collection")

def select_objects(obj):
    obj.select_set(True)
    for o in obj.children:
        select_objects(o)

def link_child_collection(parent, child):
    if child.name not in parent.children:
        parent.children.link(child)

def import_craft(filepath, use_collection_instances=False,
                 missing_models=None, skipped_parts=None):
    global gamedata
    try:
        configured = Preferences().GameData
    except KeyError:
        configured = None  # Test/embedded callers may supply their own database.
    if not gamedata or (isinstance(gamedata, GameData)
                       and ((configured and game_data_root(configured) != gamedata.root)
                            or gamedata.configuration_stamp() != gamedata.cache_stamp)):
        gamedata = GameData(configured or getattr(gamedata, 'root', ''))
    if hasattr(gamedata, 'lookup_messages'):
        gamedata.sync_aliases()
        gamedata.lookup_messages.clear()
        gamedata.import_generation += 1
    try:
        craft = ConfigNode.loadfile(filepath)
    except ConfigNodeError as e:
        raise MuImportError("Craft", e.message)
    scene = bpy.context.scene
    craft_name = craft.GetValue("ship")
    if craft_name[:9] == "#autoLOC_" and craft_name in gamedata.localizations:
        craft_name = gamedata.localizations[craft_name].strip()
    craft_display_name = safe_display_base(craft_name, filepath, "craft")
    vessel = bpy.data.collections.new(craft_name)
    rename_import_collection(vessel, craft_display_name, prefix="飞船")
    # Keep a selectable instance object per PART, rather than instancing the
    # entire vessel; otherwise an individual part cannot be selected in the UI.
    link_child_collection(bpy.context.layer_collection.collection, vessel)
    obj = bpy.data.objects.new(craft_name, None)
    obj.location = bpy.context.scene.cursor.location
    vessel.objects.link(obj)
    auxiliary(obj, "飞船根节点")
    rename_single_import_object(obj, craft_display_name, is_root=True)
    root_pos = None
    for p in craft.GetNodes("PART"):
        reference = p.GetValue('part') or ''
        prefix, separator, instance_id = reference.rpartition('_')
        pname = prefix if separator and instance_id.isdigit() else reference
        pos = parse_vector(p.GetValue("pos"))
        rot = parse_quaternion(p.GetValue("rot"))
        definition_notes = []
        definition = (gamedata.find_definition(pname, 'PART', definition_notes)
                      if hasattr(gamedata, 'find_definition') else gamedata.parts.get(pname))
        if definition is None:
            if skipped_parts is not None:
                skipped_parts.append(pname)
            if missing_models is not None:
                missing_models.append(
                    f"part '{pname}' not found or not uniquely defined in GameData: {gamedata.root}; "
                    + '; '.join(definition_notes))
            continue
        if hasattr(gamedata, 'lookup_messages'):
            gamedata.lookup_messages.extend(note for note in definition_notes
                                            if note.startswith('[resolved]') and note not in gamedata.lookup_messages)
        from ..model.appearance import variant_name
        part = (definition.get_model(missing_models, variant=variant_name(definition.cfg, p))
                if isinstance(gamedata, GameData) else definition.get_model(missing_models))
        if part is None:
            if skipped_parts is not None:
                skipped_parts.append(pname)
            continue
        if root_pos == None:
            root_pos = pos
        part.location = pos - root_pos
        part.rotation_mode = 'QUATERNION'
        part.rotation_quaternion = rot
        if use_collection_instances:
            vessel.objects.link(part)
            part.parent = obj
            rename_single_import_object(part, pname, is_root=True)
        else:
            realized = realize_model_instance(part, vessel, obj)
            rename_import_hierarchy(realized, pname)
            bpy.data.objects.remove(part)
    return obj

def import_craft_op(self, context, filepath, use_collection_instances):
    operator = self
    missing_models = []
    skipped_parts = []
    undo = bpy.context.preferences.edit.use_global_undo
    bpy.context.preferences.edit.use_global_undo = False

    try:
        obj = import_craft(filepath, use_collection_instances,
                           missing_models, skipped_parts)
    except MuImportError as e:
        operator.report({'ERROR'}, e.message)
        return {'CANCELLED'}
    else:
        for o in bpy.context.scene.objects:
            o.select_set(False)
        select_objects(obj)
        bpy.context.view_layer.objects.active = obj
        context.view_layer.update()
        if missing_models or skipped_parts:
            lines = ([f"Craft: {filepath}",
                      f"GameData: {gamedata.root}",
                      f"Skipped part instances: {len(skipped_parts)}", ""]
                     + missing_models)
            report = bpy.data.texts.new("KSP Craft Import Issues")
            report.write("\n".join(lines) + "\n")
            for line in lines:
                print("[KSP Craft Import]", line)
            operator.report(
                {'WARNING'},
                f"导入完成：{len(missing_models)} 项模型/零件缺失，"
                f"跳过 {len(skipped_parts)} 个零件实例；"
                f"缺失模型/零件详情见文本 {report.name}")
        lookup_notes = getattr(gamedata, 'lookup_messages', ())
        if lookup_notes:
            report = bpy.data.texts.new('KSP Model Lookup Report')
            report.write('\n'.join([f'Craft: {filepath}', f'GameData: {gamedata.root}',
                                    'Recovered model references (not missing):', ''] + list(lookup_notes)) + '\n')
            operator.report({'INFO'}, f"已恢复 {len(lookup_notes)} 项零件/模型匹配；详情见文本 {report.name}")
        if getattr(gamedata, 'database_issues', ()):
            report_name = database_report(gamedata)
            operator.report({'INFO'}, f'模组配置诊断见文本 {report_name}')
        return {'FINISHED'}
    finally:
        bpy.context.preferences.edit.use_global_undo = undo

class KSPMU_OT_ImportCraft(bpy.types.Operator, ImportHelper):
    '''Load a KSP craft file'''
    bl_idname = "import_object.ksp_craft"
    bl_label = "导入 Craft"
    bl_description = """导入 KSP .craft 飞船文件。"""
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".craft"
    filter_glob: StringProperty(default="*.craft", options={'HIDDEN'})
    use_collection_instances: BoolProperty(
        name="使用集合实例",
        description="使用轻量集合实例导入部件；关闭则展开为可编辑真实对象",
        default=False)

    def execute(self, context):
        keywords = self.as_keywords (ignore=("filter_glob",
                                             "axis_forward", "axis_up"))
        return import_craft_op(self, context, **keywords)


class KSPMU_OT_RefreshGameData(bpy.types.Operator):
    bl_idname = 'object.ksp_gamedata_refresh'
    bl_label = '重建模组资源索引'
    bl_description = '重新读取当前 GameData 和 ModuleManager 配置，不删除或替换已导入的场景对象'
    bl_options = {'REGISTER'}

    def execute(self, context):
        global gamedata
        try:
            rebuilt = GameData(Preferences().GameData)
        except (MuImportError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        gamedata = rebuilt
        from ..prop import prop as prop_module
        prop_module.gamedata = rebuilt
        name = database_report(rebuilt)
        self.report({'INFO'}, f'索引已重建：{len(rebuilt.parts)} 个零件 / {len(rebuilt.props)} 个 PROP；报告 {name}')
        return {'FINISHED'}


class VIEW3D_PT_KSPGameData(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'KSP'
    bl_label = '模组资源索引'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator('object.ksp_gamedata_refresh', icon='FILE_REFRESH')
        row = layout.row(align=True)
        row.operator('object.ksp_model_alias_add', text='确认替代模型')
        row.operator('object.ksp_model_alias_remove', text='移除替代规则')
        if not gamedata:
            layout.label(text='在插件设置中选择游戏或 GameData 目录')
            return
        layout.label(text=f'零件 {len(gamedata.parts)} / PROP {len(getattr(gamedata, "props", {}))}')
        layout.label(text=f'INTERNAL {len(getattr(gamedata, "internals", {}))} / 模型 {len(getattr(gamedata, "models", {}))}')
        layout.label(text='配置：ModuleManager 缓存' if getattr(gamedata, 'use_module_manager', False) else '配置：原始 CFG，未执行补丁')
        layout.label(text=f'当前场景确认的替代规则：{len(getattr(gamedata, "model_aliases", {}))}')


class KSPMU_OT_ModelAliasAdd(bpy.types.Operator):
    bl_idname = 'object.ksp_model_alias_add'
    bl_label = '确认替代模型'
    bl_description = '仅在用户核对后为缺失模型保存替代路径；规则只影响下一次导入，不修改游戏文件或已有对象'
    bl_options = {'REGISTER'}
    reference: StringProperty(name='报错模型路径', description='复制导入报告中 model 后的路径，不包含引号')
    directory: StringProperty(name='配置目录', description='复制报告中的 CFG directory，用于区分不同模组和零件')
    target: StringProperty(name='确认替代 .mu 文件', subtype='FILE_PATH')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        self.layout.label(text='先核对候选模型；不会按相似名称自动替换')
        for name in ('reference', 'directory', 'target'):
            self.layout.prop(self, name)

    def execute(self, context):
        global gamedata
        try:
            root = game_data_root(Preferences().GameData)
            if not isinstance(gamedata, GameData) or gamedata.root != root:
                gamedata = GameData(root)
            if not self.reference.strip() or not self.directory.strip():
                raise ValueError('请输入报错模型路径和配置目录')
            reference = gamedata._normalize_url(self.reference)
            directory = gamedata._normalize_url(self.directory)
            if not reference or not directory:
                raise ValueError('路径必须位于当前 GameData 范围内')
            import os
            target_file = bpy.path.abspath(self.target)
            if not target_file.lower().endswith('.mu') or not os.path.isfile(target_file):
                raise ValueError('请选择实际存在的 .mu 文件')
            target = gamedata.find_model_url(target_file)
            if not target:
                raise ValueError('替代文件必须是当前 GameData 内可准确找到的 .mu 模型')
            gamedata.set_alias(reference, directory, target)
            self.report({'INFO'}, '替代规则已保存到当前场景；重新导入对应零件时生效')
            return {'FINISHED'}
        except (MuImportError, OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class KSPMU_OT_ModelAliasRemove(bpy.types.Operator):
    bl_idname = 'object.ksp_model_alias_remove'
    bl_label = '移除替代规则'
    bl_options = {'REGISTER'}
    reference: StringProperty(name='报错模型路径')
    directory: StringProperty(name='配置目录')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        self.layout.prop(self, 'reference')
        self.layout.prop(self, 'directory')

    def execute(self, context):
        global gamedata
        try:
            root = game_data_root(Preferences().GameData)
            if not isinstance(gamedata, GameData) or gamedata.root != root:
                gamedata = GameData(root)
            key = gamedata.alias_key(self.reference, self.directory)
            if key not in gamedata.model_aliases:
                raise ValueError('当前场景没有这个替代规则')
            gamedata.set_alias(self.reference, self.directory)
            self.report({'INFO'}, '替代规则已移除；已有场景对象保持不变')
            return {'FINISHED'}
        except (MuImportError, OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def import_craft_menu_func(self, context):
    self.layout.operator(KSPMU_OT_ImportCraft.bl_idname, text="KSP 飞船 (.craft)")

classes_to_register = (
    KSPMU_OT_ImportCraft,
    KSPMU_OT_RefreshGameData,
    KSPMU_OT_ModelAliasAdd,
    KSPMU_OT_ModelAliasRemove,
    VIEW3D_PT_KSPGameData,
)

menus_to_register = (
    (bpy.types.TOPBAR_MT_file_import, import_craft_menu_func),
)
