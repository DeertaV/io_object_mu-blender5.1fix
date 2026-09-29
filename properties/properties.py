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
from bpy.props import BoolProperty, FloatProperty, StringProperty, EnumProperty
from bpy.props import PointerProperty
from bpy.props import FloatVectorProperty, IntProperty

class MuSpringProp(bpy.types.PropertyGroup):
    spring: FloatProperty(name = "弹簧")
    damper: FloatProperty(name = "阻尼")
    targetPosition: FloatProperty(name = "目标")

    def draw(self, context, layout):
        row = layout.row()
        col = row.column()
        col.prop(self, "spring")
        col.prop(self, "damper")
        col.prop(self, "targetPosition")

class MuFrictionProp(bpy.types.PropertyGroup):
    extremumSlip: FloatProperty(name = "滑移")
    extremumValue: FloatProperty(name = "数值")
    asymptoteSlip: FloatProperty(name = "滑移")
    asymptoteValue: FloatProperty(name = "数值")
    stiffness: FloatProperty(name = "刚度")

    def draw(self, context, layout):
        row = layout.row()
        col = row.column()
        col.label(text="极值")
        col.prop(self, "extremumSlip")
        col.prop(self, "extremumValue")
        col.label(text="渐近")
        col.prop(self, "asymptoteSlip")
        col.prop(self, "asymptoteValue")
        col.separator()
        col.prop(self, "stiffness")

dir_map = {
    'MU_X':0,
    'MU_Y':2,   # unity is LHS, blender is RHS
    'MU_Z':1,   # unity is LHS, blender is RHS
    0:'MU_X',
    2:'MU_Y',   # unity is LHS, blender is RHS
    1:'MU_Z',   # unity is LHS, blender is RHS
}

dir_items = (
    ('MU_X', "X", ""),
    ('MU_Y', "Y", ""),
    ('MU_Z', "Z", ""),
)

modelType_items = (
    ('NONE', "无", "不指定模型类型。"),
    ('PART', "部件", "对象及其子对象组成 KSP 部件模型。"),
    ('PROP', "舱内道具", "对象及其子对象组成 KSP Prop 模型。"),
    ('INTERNAL', "舱内空间", "对象及其子对象组成 KSP Internal Space 模型。"),
    ('STATIC', "KK 静态物", "Kerbal Konstructs 静态模型。"),
    ('MODEL', "子模型", "KSP MODEL{} 子模型。"),
    ('VOLUME', "体积", "用于体积计算，不会导出。"),
    ('UTILITY', "辅助", "辅助对象，不参与导出。"),
)
collider_items = (
    ('MU_COL_NONE', "", ""),
    ('MU_COL_MESH', "网格", ""),
    ('MU_COL_SPHERE', "球体", ""),
    ('MU_COL_CAPSULE', "胶囊", ""),
    ('MU_COL_BOX', "盒子", ""),
    ('MU_COL_WHEEL', "轮子", ""),
)
method_items = (
    ('FIXED_JOINT', "固定关节", ""),
    ('HINGE_JOINT', "铰链关节", ""),
    ('LOCKED_JOINT', "锁定关节", ""),
    ('MERGED_PHYSICS', "合并物理", ""),
    ('NO_PHYSICS', "无物理", ""),
    ('NONE', "无", ""),
)

def SetPropMask(prop, mask):
    for i in range(32):
       prop[i] = (mask & (1 << i)) and True or False

def GetPropMask(prop):
    mask = 0
    for i in range(32):
        mask |= int(prop[i]) << i;
    return mask

def collider_update(self, context):
    #FIXME
    from ..collider import update_collider
    obj = context.active_object
    update_collider(obj)

class MuProperties(bpy.types.PropertyGroup):
    modelType: EnumProperty(items = modelType_items, name = "模型类型")
    nodeSize: IntProperty(name = "尺寸", default = 1)
    nodeMethod: EnumProperty(items = method_items, name = "连接方式")
    nodeCrossfeed: BoolProperty(name = "允许交叉供给", default = True)
    nodeRigid: BoolProperty(name = "刚性连接", default = False)

    tag: StringProperty(name = "标签", default="Untagged")
    layer: IntProperty(name = "层")

    castShadows: BoolProperty(name = "投射阴影", default = True)
    receiveShadows: BoolProperty(name = "接收阴影", default = True)

    collider: EnumProperty(items = collider_items, name = "碰撞体")
    isTrigger: BoolProperty(name = "触发器")
    isConvex: BoolProperty(name = "凸面", default = True, description = "指定为 Unity 凸面网格碰撞体。")
    separate: BoolProperty(name = "单独对象", description = "导出时强制碰撞体位于单独 GameObject")
    center: FloatVectorProperty(name = "中心", subtype = 'XYZ', update=collider_update)
    radius: FloatProperty(name = "半径", update=collider_update)
    height: FloatProperty(name = "高度", update=collider_update)
    direction: EnumProperty(items = dir_items, name = "方向", update=collider_update)
    size: FloatVectorProperty(name = "尺寸", subtype = 'XYZ', update=collider_update)

    mass: FloatProperty(name = "质量")
    suspensionDistance: FloatProperty(name = "悬挂距离")
    suspensionSpring: PointerProperty(type=MuSpringProp, name = "弹簧")
    forwardFriction: PointerProperty(type=MuFrictionProp, name = "前向摩擦")
    sideFriction: PointerProperty(type=MuFrictionProp, name = "侧向摩擦")

class MuModelProperties(bpy.types.PropertyGroup):
    name: StringProperty(name = "名称", default="")
    type: StringProperty(name = "类型", default="")
    config: StringProperty(name = "配置", default="")

class MuSceneProperties(bpy.types.PropertyGroup):
    modelType: EnumProperty(items = modelType_items[1:], name = "模型类型",
        description="根对象未指定时使用的导出模型类型。")
    internal: PointerProperty(name="舱内根对象",
        description="KSP internal 模型根对象，用于 prop 放置。",
        type = bpy.types.Object)
    modelPath: StringProperty(name = "模型路径", default = "",
        description = "MODEL{} 节点中的默认模型路径")

class OBJECT_PT_MuScenePropertyPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'
    bl_label = "Mu 场景"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        muprops = scene.musceneprops

        col = layout.column()
        col.prop(muprops, "modelType")
        col.prop(muprops, "internal")
        col.prop(muprops, "modelPath")

class VIEW3D_PT_MuScenePanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "View"
    bl_label = "Mu 场景"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        muprops = scene.musceneprops

        col = layout.column()
        col.prop(muprops, "modelType")
        col.prop(muprops, "internal")
        col.prop(muprops, "modelPath")

class OBJECT_PT_MuAttachNodePanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = '连接节点'

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'EMPTY' and obj.name[:5] == "node_"

    def draw(self, context):
        layout = self.layout
        muprops = context.active_object.muproperties
        row = layout.row()
        col = row.column()
        col.prop(muprops, "nodeSize")
        col.prop(muprops, "nodeMethod")
        col.prop(muprops, "nodeCrossfeed")
        col.prop(muprops, "nodeRigid")

class OBJECT_PT_MuPropertiesPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_label = 'Mu 属性'

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        muprops = context.active_object.muproperties
        row = layout.row()
        col = row.column()
        col.prop(muprops, "modelType")
        col.prop(muprops, "tag")
        col.prop(muprops, "layer")
        col.prop(muprops, "castShadows")
        col.prop(muprops, "receiveShadows")

classes_to_register = (
    MuSpringProp,
    MuFrictionProp,
    MuProperties,
    MuModelProperties,
    MuSceneProperties,
    OBJECT_PT_MuScenePropertyPanel,
    VIEW3D_PT_MuScenePanel,
    OBJECT_PT_MuAttachNodePanel,
    OBJECT_PT_MuPropertiesPanel,
)
custom_properties_to_register = (
    (bpy.types.Object, "muproperties", MuProperties),
    (bpy.types.Collection, "mumodelprops", MuModelProperties),
    (bpy.types.Scene, "musceneprops", MuSceneProperties),
)
