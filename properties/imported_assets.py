"""Persistent source-animation bindings, independent of display names."""
import bpy
from bpy.props import (StringProperty, FloatProperty, IntProperty, BoolProperty,
                       PointerProperty, CollectionProperty, EnumProperty)


def target_fields():
    return {
        "object": PointerProperty(type=bpy.types.Object),
        "material": PointerProperty(type=bpy.types.Material),
        "light": PointerProperty(type=bpy.types.Light),
        "camera": PointerProperty(type=bpy.types.Camera),
        "action": PointerProperty(type=bpy.types.Action),
        "path": StringProperty(),
        "rest": StringProperty(),
    }


class KSPSourceBinding(bpy.types.PropertyGroup):
    __annotations__ = target_fields()


class KSPSourceClip(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty()
    path: StringProperty()
    start: FloatProperty(default=1)
    end: FloatProperty(default=2)
    fps: FloatProperty(default=24, min=0.001)
    issues: StringProperty()
    bindings: CollectionProperty(type=KSPSourceBinding)


class KSPPlaybackBinding(bpy.types.PropertyGroup):
    __annotations__ = target_fields()
    track: StringProperty()
    strip: StringProperty()


class KSPOverrideState(bpy.types.PropertyGroup):
    __annotations__ = target_fields()
    track: StringProperty()
    strip: StringProperty()
    was_mute: BoolProperty()
    active: BoolProperty()
    slot_handle: IntProperty()
    active_blend: StringProperty(default='REPLACE')
    active_extrapolation: StringProperty(default='HOLD')
    active_influence: FloatProperty(default=1)
    frame_start: FloatProperty()
    frame_end: FloatProperty()


def update_playback(self, context):
    from ..utils.import_assets import resolve_playback, binding_target, resolve_override, covered_by_other, update_baselines
    failed = 0
    for entry in self.entries:
        track, strip = resolve_playback(entry)
        if strip:
            strip.mute = self.mute or covered_by_other(self.id_data, self, binding_target(entry), entry.action)
            strip.influence = self.influence
            strip.blend_type = self.blend
            strip.extrapolation = 'HOLD_FORWARD' if self.hold else 'NOTHING'
        else:
            failed += 1
    for saved in self.overrides:
        _, strip = resolve_override(saved)
        if strip:
            strip.mute = (saved.was_mute or (self.blend == 'REPLACE' and not self.mute)
                          or covered_by_other(self.id_data, self, binding_target(saved), saved.action))
        else:
            failed += 1
    self.issue = f"{failed} 个播放条目已删除或有歧义，请检查 NLA" if failed else ""
    update_baselines(self.id_data)


class KSPScheduledClip(bpy.types.PropertyGroup):
    uid: StringProperty()
    source_key: StringProperty()
    name: StringProperty()
    issue: StringProperty()
    source_start: FloatProperty()
    source_end: FloatProperty()
    start: FloatProperty()
    end: FloatProperty()
    entries: CollectionProperty(type=KSPPlaybackBinding)
    overrides: CollectionProperty(type=KSPOverrideState)
    mute: BoolProperty(name="静音", update=update_playback)
    hold: BoolProperty(name="结束后保持", default=True, update=update_playback)
    influence: FloatProperty(name="影响", default=1, min=0, max=1,
                             update=update_playback)
    blend: EnumProperty(name="混合", items=(('REPLACE', "替换", ""),
                                            ('COMBINE', "融合", "")),
                        default='REPLACE', update=update_playback)


_enum_cache = {}


def clip_items(self, context):
    from ..utils.import_assets import clip_entries
    items = [(str(i), f"{i + 1}. {clip.name} [{anchor.name}]", path + '\n' + clip.path + "\n" + (clip.issues or "游戏原始片段"))
             for i, (anchor, clip, path) in enumerate(clip_entries(self.id_data))]
    if not items:
        items = [('NONE', "无导入动画", "")]
    _enum_cache[self.id_data.as_pointer()] = items
    return items


def select_clip(self, context):
    from ..utils.import_assets import collect_clips
    clips = collect_clips(self.id_data)
    try:
        _, clip = clips[int(self.clip_choice)]
    except (ValueError, IndexError):
        return
    self.source_start, self.source_end = clip.start, clip.end
    if context:
        self.insert_frame = context.scene.frame_current_final


class KSPImportedAssets(bpy.types.PropertyGroup):
    uid: StringProperty()
    source: StringProperty()
    clips: CollectionProperty(type=KSPSourceClip)
    scheduled: CollectionProperty(type=KSPScheduledClip)
    baselines: CollectionProperty(type=KSPPlaybackBinding)
    clip_choice: EnumProperty(name="游戏动画", items=clip_items, update=select_clip)
    source_start: FloatProperty(name="源开始帧", default=1)
    source_end: FloatProperty(name="源结束帧", default=2)
    insert_frame: FloatProperty(name="插入帧", default=1)
    hold: BoolProperty(name="结束后保持最后状态", default=True)
    show_issues: BoolProperty(name="展开未支持 / 未绑定通道")


classes_to_register = (KSPSourceBinding, KSPSourceClip, KSPPlaybackBinding,
                       KSPOverrideState, KSPScheduledClip, KSPImportedAssets)
custom_properties_to_register = ((bpy.types.Object, "ksp_assets", KSPImportedAssets),)
