"""Import source resources and remap them when a part instance is realized."""
import json
import ast
from uuid import uuid4
import bpy


def uid():
    return uuid4().hex


def binding_target(binding):
    return binding.material or binding.light or binding.camera or binding.object


def resolve_playback(entry):
    target = binding_target(entry)
    ad = getattr(target, 'animation_data', None)
    if not ad:
        return None, None
    track = ad.nla_tracks.get(entry.track)
    strip = track.strips.get(entry.strip) if track else None
    if strip and strip.action == entry.action:
        return track, strip
    matches = [(t, s) for t in ad.nla_tracks for s in t.strips if s.action == entry.action and entry.action]
    if len(matches) == 1:
        track, strip = matches[0]
        entry.track, entry.strip = track.name, strip.name
        return track, strip
    return None, None


def remove_playback(entry):
    target = binding_target(entry)
    ad = getattr(target, 'animation_data', None)
    track, strip = resolve_playback(entry)
    if strip:
        track.strips.remove(strip)
        if not track.strips:
            ad.nla_tracks.remove(track)
        return True
    # During a failed add, a track may have been created before its strip.
    track = ad.nla_tracks.get(entry.track) if ad else None
    if track and not track.strips:
        ad.nla_tracks.remove(track)
        return True
    return False


def resolve_override(saved):
    target = binding_target(saved)
    ad = getattr(target, 'animation_data', None)
    matches = [(t, s) for t in ad.nla_tracks for s in t.strips if s.action == saved.action] if ad else []
    exact = [(t, s) for t, s in matches if t.name == saved.track and s.name == saved.strip
             and abs(s.frame_start - saved.frame_start) < 0.001 and abs(s.frame_end - saved.frame_end) < 0.001]
    if len(exact) != 1:
        exact = [(t, s) for t, s in matches if abs(s.frame_start - saved.frame_start) < 0.001
                 and abs(s.frame_end - saved.frame_end) < 0.001]
    if len(exact) != 1 and len(matches) == 1:
        exact = matches
    return exact[0] if len(exact) == 1 else (None, None)


def covered_by_other(root, group, target, action):
    return any(other.uid != group.uid and other.blend == 'REPLACE' and not other.mute
               and any(binding_target(saved) == target and saved.action == action for saved in other.overrides)
               for other in root.ksp_assets.scheduled)


def update_baselines(root):
    from .blender_compat import iter_action_fcurves
    for baseline in root.ksp_assets.baselines:
        target = binding_target(baseline)
        ad = getattr(target, 'animation_data', None)
        if not ad or not baseline.action:
            continue
        channels = set()
        sources = [(ad.action, ad)] if ad.action else []
        sources += [(strip.action, strip) for track in ad.nla_tracks if not track.mute
                    for strip in track.strips if strip.action and not strip.mute]
        for action, slot in sources:
            if action.get('ksp_playback_uid') or action.get('ksp_baseline'):
                continue
            channels.update((fc.data_path, fc.array_index) for fc in iter_action_fcurves(action, slot) if not fc.mute)
        for fc in iter_action_fcurves(baseline.action):
            fc.mute = (fc.data_path, fc.array_index) in channels


def set_binding(binding, target, action=None, path="", rest=""):
    if isinstance(target, bpy.types.Material):
        binding.material = target
    elif isinstance(target, bpy.types.Light):
        binding.light = target
    elif isinstance(target, bpy.types.Camera):
        binding.camera = target
    elif isinstance(target, bpy.types.Object):
        binding.object = target
    else:
        raise ValueError(f"Unsupported animation ID: {target}")
    binding.action = action
    binding.path = path
    binding.rest = rest


def capture_rest(target, action):
    from .blender_compat import iter_action_fcurves
    values = []
    for fc in iter_action_fcurves(action):
        try:
            value = target.path_resolve(fc.data_path)
            if hasattr(value, "__len__"):
                value = value[fc.array_index]
            values.append([fc.data_path, fc.array_index, value])
        except (ValueError, TypeError, IndexError):
            continue
    return json.dumps(values)


def restore_values(target, values, blocked=()):
    for path, channel, value in values:
        if (path, channel) in blocked:
            continue
        prefix, _, attr = path.rpartition('.')
        try:
            owner = target.path_resolve(prefix) if prefix else target
            if attr.startswith('[') and attr.endswith(']'):
                owner[ast.literal_eval(attr[1:-1])] = value
            else:
                current = getattr(owner, attr)
                if hasattr(current, '__len__'):
                    current[channel] = value
                else:
                    setattr(owner, attr, value)
        except (AttributeError, ValueError, TypeError, IndexError):
            continue


def finalize_assets(mu, root, filepath):
    props = root.ksp_assets
    props.uid = uid()
    props.source = filepath
    root["ksp_model_root"] = True
    for source in mu.source_clips:
        clip = props.clips.add()
        clip.uid = source["uid"]
        clip.name = source["name"]
        clip.path = source["path"]
        clip.start, clip.end, clip.fps = source["start"], source["end"], source["fps"]
        clip.issues = "\n".join(source["issues"])
        for action, target, path in source["bindings"]:
            set_binding(clip.bindings.add(), target, action, path, capture_rest(target, action))
    if props.clips:
        props.clip_choice = '0'
    report = bpy.data.texts.new("KSP Model Import Data")
    report.write(f"Source: {filepath}\nClips: {len(props.clips)}\n"
                 + "\n".join(mu.data_issues) + "\n"
                 + "\n".join(f"{clip.name}: {clip.issues}" for clip in props.clips if clip.issues) + "\n")
    root["ksp_import_report"] = report.name


def instance_root(obj):
    """A part or placement anchor owns animation independently of its parent."""
    return bool(obj and (obj.get("ksp_part_root") or obj.get("ksp_instance_root")
                        or obj.get("ksp_original_name") == "ksp_import_anchor"))


def model_root(obj):
    candidate = None
    while obj:
        if instance_root(obj):
            return obj
        if obj.get("ksp_model_root") or (hasattr(obj, "ksp_assets") and obj.ksp_assets.uid):
            # Keep the nearest raw model when no part/placement anchor exists.
            # The highest ancestor may be a separately imported, animated model.
            if candidate is None:
                candidate = obj
        obj = obj.parent
    return candidate


def walk_objects(root):
    yield root
    for child in root.children:
        yield from walk_objects(child)


def asset_anchors(root, stack=()):
    if not root:
        return
    if root.ksp_assets.clips:
        yield root
    if root.instance_type == 'COLLECTION' and root.instance_collection:
        collection = root.instance_collection
        if collection.as_pointer() not in stack:
            objects = set(collection.all_objects)
            for obj in collection.all_objects:
                if obj.parent not in objects:
                    yield from asset_anchors(obj, stack + (collection.as_pointer(),))
    for child in root.children:
        yield from asset_anchors(child, stack)


def collect_clips(root):
    return [(anchor, clip) for anchor, clip, _ in clip_entries(root)]


def clip_entries(root, stack=(), trail="", owner=None):
    if not root:
        return
    if owner is None:
        owner = root
    elif instance_root(root):
        # Parenting independent parts/models together does not merge resources.
        return
    elif owner.ksp_assets.clips and root.get("ksp_model_root") and root.ksp_assets.clips:
        return
    path = trail + '/' + root.get('ksp_original_name', root.name)
    for clip in root.ksp_assets.clips:
        yield root, clip, path
    if root.instance_type == 'COLLECTION' and root.instance_collection:
        collection = root.instance_collection
        if collection.as_pointer() not in stack:
            objects = set(collection.all_objects)
            for obj in collection.all_objects:
                if obj.parent not in objects:
                    yield from clip_entries(obj, stack + (collection.as_pointer(),), path, owner)
    for child in root.children:
        yield from clip_entries(child, stack, path, owner)


def remap_assets(state):
    for source, dest in state["object_map"].items():
        if not source.ksp_assets.uid:
            continue
        props = dest.ksp_assets
        props.clips.clear()
        props.scheduled.clear()
        props.baselines.clear()
        props.uid = uid()
        props.source = source.ksp_assets.source
        for src in source.ksp_assets.clips:
            clip = props.clips.add()
            for field in ("uid", "name", "path", "start", "end", "fps", "issues"):
                setattr(clip, field, getattr(src, field))
            for binding in src.bindings:
                target = binding_target(binding)
                if isinstance(target, bpy.types.Object):
                    target = state["object_map"].get(target)
                elif isinstance(target, bpy.types.Material):
                    target = state["material_map"].get(target)
                else:
                    target = state["data_map"].get(target)
                if not target:
                    clip.issues += f"\nUnbound target: {binding.path}"
                    continue
                action = binding.action
                if action not in state["action_map"]:
                    state["action_map"][action] = action.copy()
                    state["action_map"][action].use_fake_user = True
                set_binding(clip.bindings.add(), target,
                            state["action_map"][action], binding.path, binding.rest)


def auxiliary(obj, kind):
    if not obj.get("ksp_data_token"):
        obj["ksp_data_token"] = uid()
    obj["ksp_auxiliary"] = kind
    obj["ksp_aux_visible"] = False
    if obj.type == 'EMPTY':
        obj["ksp_empty_size"] = obj.empty_display_size
        obj.empty_display_size = 0
    elif obj.type == 'ARMATURE':
        # Hide display, not depsgraph evaluation or child meshes.
        set_local_hidden(obj, True)
    else:
        set_local_hidden(obj, True)
        obj.hide_render = True
        if obj.type == 'MESH':
            # ViewLayer hide_set is not inherited by collection instances, and
            # cached objects may not have a Base in the current scene at all.
            # Only rendererless helper meshes use persistent viewport hiding;
            # armatures/transform parents must continue to evaluate normally.
            obj.hide_viewport = True


def set_auxiliary_visibility(obj, visible):
    obj["ksp_aux_visible"] = visible
    if obj.type == 'EMPTY':
        obj.empty_display_size = obj.get("ksp_empty_size", 1.0) if visible else 0
    else:
        set_local_hidden(obj, not visible)
        if obj.type != 'ARMATURE':
            obj.hide_render = not visible
        if obj.type == 'MESH':
            obj.hide_viewport = not visible


def set_local_hidden(obj, hidden):
    # Cached craft models live in a utility scene, not the active ViewLayer.
    if obj.name in bpy.context.view_layer.objects:
        try:
            obj.hide_set(hidden)
        except RuntimeError:
            # A freshly linked/unlinked object may still have a stale Base.
            bpy.context.view_layer.update()
            if obj.name in bpy.context.view_layer.objects:
                obj.hide_set(hidden)


def preserve_metadata(obj, component):
    def encode(value):
        if isinstance(value, (str, float, int, bool, type(None))):
            return value
        if isinstance(value, (tuple, list)):
            return [encode(v) for v in value]
        if hasattr(value, "__dict__"):
            return {k: encode(v) for k, v in vars(value).items()}
        return str(value)
    obj["ksp_raw_" + type(component).__name__] = json.dumps(encode(component))


_DATA_TYPES = ('meshes', 'armatures', 'lights', 'cameras', 'materials', 'actions')


def data_snapshot():
    return {kind: {item.as_pointer() for item in getattr(bpy.data, kind)} for kind in _DATA_TYPES}


def cleanup_new_data(snapshot):
    # Only discard new unreferenced datablocks; never purge pre-existing data.
    for kind in _DATA_TYPES:
        collection = getattr(bpy.data, kind)
        for item in list(collection):
            if item.as_pointer() in snapshot[kind]:
                continue
            if kind == 'actions' or item.users == int(item.use_fake_user):
                item.use_fake_user = False
            if item.users == 0:
                collection.remove(item)
