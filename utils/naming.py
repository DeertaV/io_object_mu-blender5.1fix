# vim:ts=4:et

import os
import re

import bpy

from .utils import strip_nnn


BLENDER_SUFFIX_RE = re.compile(r"(\.\d{3}| \(\d+\))$")
MESSY_PREFIXES = ("Object", "object", "model", "Model")
MOJIBAKE_MARKERS = ("å", "æ", "ç", "è", "é", "ä", "Ã", "Â", "¤", "�")


def clean_base_name(name, fallback="未命名"):
    raw = name or ""
    name = os.path.basename(raw).strip()
    if "." in name:
        root, ext = os.path.splitext(name)
        if ext.lower() in {".mu", ".craft", ".cfg"}:
            name = root
    if name.lower() in {"model", "model000"}:
        parent = os.path.basename(os.path.dirname(raw))
        if parent:
            name = parent
    name = BLENDER_SUFFIX_RE.sub("", name).strip()
    name = name.replace(":", "_").replace("/", "_").replace("\\", "_")
    return name or fallback


def looks_mojibake(name):
    if not name:
        return True
    return any(marker in name for marker in MOJIBAKE_MARKERS)


def safe_display_base(name, fallback_source=None, fallback="未命名"):
    if looks_mojibake(name):
        return clean_base_name(fallback_source, fallback)
    return clean_base_name(name, fallback)


def original_ksp_name(obj):
    try:
        stored = obj.get("ksp_original_name", "")
    except AttributeError:
        stored = ""
    return strip_nnn(stored or obj.name)


def display_prefix(obj, is_root=False):
    if is_root:
        return "部件"
    if getattr(obj, "muproperties", None) and obj.muproperties.modelType == 'VOLUME':
        return "体积"
    if obj.type == 'MESH':
        if obj.name.lower().startswith(("col", "collider")):
            return "碰撞"
        return "网格"
    if obj.type == 'ARMATURE':
        return "骨架"
    if obj.type == 'LIGHT':
        return "灯光"
    if obj.type == 'CAMERA':
        return "相机"
    if obj.type == 'EMPTY':
        return "空物体"
    return "对象"


def readable_object_name(obj, root_name=None, is_root=False):
    base = clean_base_name(root_name if is_root and root_name else obj.name)
    if any(base.startswith(prefix) for prefix in MESSY_PREFIXES) and obj.data:
        base = clean_base_name(obj.data.name, base)
    return f"{display_prefix(obj, is_root)}_{base}"


def preserve_original_name(obj):
    if "ksp_original_name" not in obj:
        obj["ksp_original_name"] = strip_nnn(obj.name)
    if obj.data and "ksp_original_name" not in obj.data:
        obj.data["ksp_original_name"] = strip_nnn(obj.data.name)


def rename_import_hierarchy(root, root_name=None):
    if not root:
        return
    objects = [root]
    objects.extend(root.children_recursive)
    for obj in objects:
        preserve_original_name(obj)
    for obj in objects:
        is_root = obj == root
        obj.name = readable_object_name(obj, root_name, is_root)
        if obj.data:
            prefix = display_prefix(obj, is_root=False)
            obj.data.name = f"{prefix}数据_{clean_base_name(obj.data.name)}"


def rename_single_import_object(obj, display_name=None, is_root=False):
    if not obj:
        return
    preserve_original_name(obj)
    obj.name = readable_object_name(obj, display_name, is_root)
    if obj.data:
        prefix = display_prefix(obj, is_root=False)
        obj.data.name = f"{prefix}数据_{clean_base_name(obj.data.name)}"


def rename_import_collection(collection, source_name=None, prefix="集合"):
    if not collection:
        return
    if "ksp_original_name" not in collection:
        collection["ksp_original_name"] = strip_nnn(collection.name)
    base = safe_display_base(source_name or collection.name, collection.name)
    collection.name = f"{prefix}_{base}"
