"""Static CFG texture remaps and stock ModulePartVariants (no Unity scripts)."""
import os
import bpy

from ..import_mu.textures import resolve_texture, load_texture_file, EXTENSIONS
from ..shader.shader import ensure_principled_preview


def _texture_name(url):
    base, ext = os.path.splitext(url)
    return base if ext.casefold() in EXTENSIONS else url


def _objects(collection):
    # Appearance collections are realized templates, so pointers and material
    # animation bindings stay independent without expanding every craft part.
    return list(collection.all_objects)


def _copy_template(base, name, owner):
    from .model import realize_model_instance
    result = bpy.data.collections.new(name)
    owner.children.link(result)
    instance = bpy.data.objects.new(name + ':source', None)
    instance.instance_type, instance.instance_collection = 'COLLECTION', base
    try:
        realize_model_instance(instance, result)
    except Exception:
        owner.children.unlink(result)
        bpy.data.collections.remove(result)
        raise
    finally:
        bpy.data.objects.remove(instance)
    return result


def _materials(objects, transform=None):
    selected = [o for o in objects if not transform or
                o.get('ksp_original_name', o.name) == transform or
                o.get('ksp_original_path', '').rsplit('/', 1)[-1] == transform]
    return {m for o in selected if o.type == 'MESH' for m in o.data.materials if m}


def _texture(prop, url, db, directory, notes):
    path, detail = resolve_texture(url, os.path.join(db.root, directory), db.root, allow_shared=False)
    if not path:
        notes.append(f'Missing CFG/variant texture: {url}: {detail}')
        return False
    try:
        image = load_texture_file(path, prop.name.casefold() in ('_bumpmap', '_normalmap'))
    except (OSError, RuntimeError, ValueError) as exc:
        notes.append(f'CFG/variant texture decode failed: {url}: {exc}')
        return False
    prop.tex = _texture_name(url)
    prop['blender_image_name'] = image.name
    prop['ksp_image_binding'] = True
    prop['ksp_texture_source'] = path
    prop.rgbNorm = not image.muimageprop.convertNorm
    notes.append(f'Applied texture: {prop.name}: {url} -> {path}')
    return True


def model_texture_remaps(base, node, db, directory, owner, notes):
    mappings = []
    for value in node.values:
        if value.name == 'texture':
            fields = [v.strip() for v in value.value.split(',', 1)]
            if len(fields) == 2:
                mappings.append(fields)
            else:
                notes.append(f'Invalid MODEL texture remap: {value.value}')
    if not mappings:
        return base
    result = _copy_template(base, base.name + ':textures', owner)
    for old, new in mappings:
        matched = False
        for mat in _materials(_objects(result)):
            for prop in mat.mumatprop.texture.properties:
                existing = _texture_name(prop.tex).casefold().replace('\\', '/')
                requested = _texture_name(old).casefold().replace('\\', '/')
                if existing == requested or ('/' not in requested and existing.rsplit('/', 1)[-1] == requested):
                    matched = _texture(prop, new, db, directory, notes) or matched
            ensure_principled_preview(mat)
        if not matched:
            notes.append(f'MODEL texture remap did not bind: {old} -> {new}')
    return result


def variant_name(cfg, craft_node):
    for module in craft_node.GetNodes('MODULE'):
        if module.GetValue('name') == 'ModulePartVariants' and module.HasValue('selectedVariant'):
            return module.GetValue('selectedVariant')
    for module in cfg.GetNodes('MODULE'):
        if module.GetValue('name') == 'ModulePartVariants':
            return module.GetValue('baseVariant') or ''
    return ''


def compile_variant(base, name, cfg, selected, db, directory, owner, notes):
    candidates = [v for module in cfg.GetNodes('MODULE')
                  if module.GetValue('name') == 'ModulePartVariants'
                  for v in module.GetNodes('VARIANT') if v.GetValue('name') == selected]
    if not candidates:
        # Some stock modules name their built-in base without a VARIANT node.
        bases = [m.GetValue('baseVariant') for m in cfg.GetNodes('MODULE')
                 if m.GetValue('name') == 'ModulePartVariants']
        if selected not in bases:
            notes.append(f'Variant not defined: {name}: {selected}; kept source appearance')
        return base
    if len(candidates) != 1:
        notes.append(f'Ambiguous variant: {name}: {selected}; kept source appearance')
        return base
    variant = candidates[0]
    result = _copy_template(base, name + ':variant:' + selected, owner)
    result['ksp_variant'] = selected
    result['ksp_variant_cfg'] = variant.ToString(-1)
    objects = _objects(result)
    for texture in variant.GetNodes('TEXTURE'):
        transform = texture.GetValue('transformName')
        materials = _materials(objects, transform)
        if not materials:
            notes.append(f'Variant texture target not found: {name}: {selected}: {transform}')
        for value in texture.values:
            key = '_MainTex' if value.name == 'mainTextureURL' else value.name
            if key == 'transformName':
                continue
            applied = False
            for mat in materials:
                props = mat.mumatprop.texture.properties
                prop = next((p for p in props if p.name == key), None)
                if prop:
                    applied = _texture(prop, value.value, db, directory, notes) or applied
            if not applied:
                notes.append(f'Variant setting not converted: {name}: {selected}: {value.name}={value.value}')
        for mat in materials:
            ensure_principled_preview(mat)
    active = {}
    for gameobjects in variant.GetNodes('GAMEOBJECTS'):
        for value in gameobjects.values:
            matching = [o for o in objects if o.get('ksp_original_path', '').rsplit('/', 1)[-1] == value.name]
            if not matching:
                notes.append(f'Variant GAMEOBJECTS target not found: {name}: {value.name}')
            for obj in matching:
                if value.value.casefold() in ('false', 'true'):
                    active[obj] = value.value.casefold() == 'true'
                else:
                    notes.append(f'Invalid GAMEOBJECTS boolean: {value.name}={value.value}')
    for obj in objects:
        parent, hidden = obj, False
        while parent:
            hidden = hidden or active.get(parent) is False
            parent = parent.parent
        if hidden or obj in active:
            obj.hide_viewport = hidden or (obj.type == 'MESH' and bool(obj.get('ksp_auxiliary')))
            obj.hide_render = hidden or (bool(obj.get('ksp_auxiliary')) and obj.type not in {'EMPTY', 'ARMATURE'})
            obj['ksp_variant_hidden'] = hidden
    for child in variant.nodes:
        if child.name not in ('TEXTURE', 'GAMEOBJECTS'):
            notes.append(f'Variant data retained as metadata only: {name}: {selected}: {child.name}')
    for obj in objects:
        if obj.get('ksp_part_root'):
            obj['ksp_variant'] = selected
    notes.append(f'Applied appearance variant: {name}: {selected}')
    return result


def appearance_report(name, directory, notes):
    if not notes:
        return
    text = bpy.data.texts.new('KSP Appearance Import Report')
    text.write(f'Part/model: {name}\nCFG directory: {directory}\n' + '\n'.join(dict.fromkeys(notes)) + '\n')
