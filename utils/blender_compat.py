# vim:ts=4:et

import bpy


def clear_to_mesh(obj_eval, obj_original=None):
    """Clear temporary meshes created via Object.to_mesh() across API variants."""
    target = obj_eval if obj_eval is not None else obj_original
    if target is None:
        return
    try:
        target.to_mesh_clear()
    except RuntimeError:
        if obj_original is not None and obj_original is not target:
            try:
                obj_original.to_mesh_clear()
            except RuntimeError:
                pass


def update_view_layer(context=None):
    """Force dependency graph/view layer evaluation after modifier visibility changes."""
    if context is None:
        context = bpy.context
    try:
        context.view_layer.update()
    except AttributeError:
        pass


def enable_custom_normals(mesh):
    """Compatibility shim for split/custom normals across Blender versions.

    Blender 4.1+ removed Mesh.use_auto_smooth. Custom loop normals still work,
    so only touch the property when it exists.
    """
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True


def ensure_mesh_normals(mesh):
    """Refresh mesh normals without relying on removed Blender APIs."""
    if hasattr(mesh, "calc_normals"):
        mesh.calc_normals()
        return
    try:
        mesh.update(calc_edges=False)
    except TypeError:
        mesh.update()
    if hasattr(mesh, "calc_loop_triangles"):
        mesh.calc_loop_triangles()


def set_edit_bone_inherit_scale(edit_bone, enabled=True):
    """Set EditBone scale inheritance across Blender API variants."""
    if hasattr(edit_bone, "use_inherit_scale"):
        edit_bone.use_inherit_scale = enabled
    elif hasattr(edit_bone, "inherit_scale"):
        edit_bone.inherit_scale = 'FULL' if enabled else 'NONE'


def ensure_action_fcurve(action, datablock, data_path, index=0):
    """Create an F-Curve on legacy and layered Blender action APIs."""
    if hasattr(action, "fcurves"):
        if index is None:
            return action.fcurves.new(data_path=data_path)
        return action.fcurves.new(data_path=data_path, index=index)

    if not datablock.animation_data:
        datablock.animation_data_create()
    datablock.animation_data.action = action
    if index is None:
        return action.fcurve_ensure_for_datablock(datablock, data_path)
    return action.fcurve_ensure_for_datablock(datablock, data_path,
                                              index=index)


def iter_action_fcurves(action, slot_source=None):
    """Yield F-Curves on legacy and Blender 5.1 layered action APIs."""
    if not action:
        return
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return

    slot_handle = getattr(slot_source, "action_slot_handle", None)
    fallback = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                curves = list(getattr(bag, "fcurves", []))
                if slot_handle is None:
                    yield from curves
                    continue
                if getattr(bag, "slot_handle", None) == slot_handle:
                    yield from curves
                    return
                fallback.extend(curves)

    if slot_handle is not None:
        yield from fallback
