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

# copied from io_scene_obj

# <pep8 compliant>

import bpy, os
from bpy.types import AddonPreferences
from bpy.props import StringProperty, BoolProperty

from . import colorpalettes

def addon_package_name():
    parts = (__package__ or "").split(".")
    if len(parts) >= 3 and parts[0] == "bl_ext":
        return ".".join(parts[:3])
    if len(parts) >= 2 and parts[-1] == "preferences":
        return ".".join(parts[:-1])
    return parts[0]

package_name = addon_package_name()

def install_presets(dstsubdir, srcsubdir):
    presets=bpy.utils.script_paths()
    dst = "/".join((presets[-1], "presets", dstsubdir))
    src=os.path.dirname(os.path.abspath(__file__)) + "/" + srcsubdir
    if not os.access(dst, os.F_OK):
        os.makedirs(dst)
    names = os.listdir(src)
    for name in names:
        s = src + "/" + name
        d = dst + "/" + name
        with open(s, "rb") as fsrc:
            with open(d, "wb") as fdst:
                while True:
                    buf = fsrc.read(16*1024)
                    if not buf:
                        break
                    fdst.write(buf)

class KSPMU_OT_InstallShaders(bpy.types.Operator):
    bl_idname = 'io_object_mu_presets.shaders'
    bl_label = 'Install KSP Shader Presets'

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        install_presets(package_name + "/shaders", "shaders")
        self.report({'INFO'}, 'Shader presets installed.')
        return {'FINISHED'}

class KSPMU_OT_InstallCfgTemplates(bpy.types.Operator):
    bl_idname = 'io_object_mu_presets.cfgtemplates'
    bl_label = 'Install KSP Config Templates'

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        install_presets(package_name + "/kspcfg", "cfgtemplates")
        self.report({'INFO'}, 'Config templates installed.')
        return {'FINISHED'}

class KSPMU_OT_CreateColorPalettes(bpy.types.Operator):
    bl_idname = 'io_object_mu_presets.color_palettes'
    bl_label = 'Create Community Color Palettes'

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        colorpalettes.install()
        self.report({'INFO'}, 'Color palettes created.')
        return {'FINISHED'}

class IOObjectMu_AddonPreferences(AddonPreferences):
    bl_idname = package_name

    GameData: StringProperty(
        name="KSP 游戏 / GameData 目录",
        description="选择 KSP 游戏目录或其中的 GameData 目录；更改模组后可在 KSP 页面重建索引",
        subtype='DIR_PATH')

    AutohideColliders: BoolProperty(
        name="Autohide Mesh Colliders",
        description="Automatically hide new mesh colliders",
        default=False)

    def draw(self, context):
        layout = self.layout
        box = layout.box ()
        box.label(text="Editing:")
        box.prop(self, "AutohideColliders")
        box.label(text="KSP:")
        box.prop(self, "GameData")
        box.label(text="Shaders:")
        box.operator(KSPMU_OT_InstallShaders.bl_idname,
                     text=KSPMU_OT_InstallShaders.bl_label);
        box.label(text="Config Templates:")
        box.operator(KSPMU_OT_InstallCfgTemplates.bl_idname,
                     text=KSPMU_OT_InstallCfgTemplates.bl_label);
        box.label(text="Color Paletes:")
        cbox = box.box()
        cbox.operator(KSPMU_OT_CreateColorPalettes.bl_idname,
                      text=KSPMU_OT_CreateColorPalettes.bl_label);
        cbox.label(text="NOTE: this must be done for each new blend file or saved to your startup file.", icon="LAYER_USED")
        cbox.label(text="NOTE2: overwrites existing palettes that have the same names", icon="LAYER_USED")

def Preferences():
    preferences = bpy.context.preferences
    addons = preferences.addons
    keys = [package_name]
    parts = (__package__ or "").split(".")
    if len(parts) >= 3 and parts[0] == "bl_ext":
        keys.append(".".join(parts[:3]))
    if len(parts) >= 2 and parts[-1] == "preferences":
        keys.append(".".join(parts[:-1]))
    keys.append("io_object_mu_blender51")
    for key in keys:
        if key in addons:
            prefs = addons[key]
            return prefs.preferences
    for key in addons.keys():
        if key.endswith(".io_object_mu_blender51"):
            prefs = addons[key]
            return prefs.preferences
    prefs = addons[package_name]
    return prefs.preferences

classes_to_register = (
    IOObjectMu_AddonPreferences,
    KSPMU_OT_InstallShaders,
    KSPMU_OT_InstallCfgTemplates,
    KSPMU_OT_CreateColorPalettes,
)
