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

import sys, traceback

import bpy
from bpy.types import bpy_prop_array
from mathutils import Vector

from .shader_config import shader_configs

typemap = {
    'VALUE': "NodeSocketFloat",
    'RGBA': "NodeSocketColor",
    'SHADER': "NodeSocketShader",
}

use_index = { None, "Vector", "Value", "Shader" }

node_type_aliases = {
    "ShaderNodeSeparateRGB": "ShaderNodeSeparateColor",
    "ShaderNodeCombineRGB": "ShaderNodeCombineColor",
}

socket_aliases = {
    "Image": "Color",
    "RGB": "Color",
    "R": "Red",
    "G": "Green",
    "B": "Blue",
}

shader_aliases = {
    "Standard": "KSP/Bumped Specular",
    "KSP/Particles/Additive": "KSP/Alpha/Translucent Additive",
    "KSP/Particles/Alpha Blended": "KSP/Alpha/Translucent Additive",
}

KSP_PREVIEW_PRINCIPLED = "Principled BSDF"


def node_tree_add_input(node_tree, socket_type, name):
    if hasattr(node_tree, "interface") and node_tree.interface is not None:
        return node_tree.interface.new_socket(
            name=name,
            in_out='INPUT',
            socket_type=socket_type,
        )
    return node_tree.inputs.new(socket_type, name)


def node_tree_add_output(node_tree, socket_type, name):
    if hasattr(node_tree, "interface") and node_tree.interface is not None:
        return node_tree.interface.new_socket(
            name=name,
            in_out='OUTPUT',
            socket_type=socket_type,
        )
    return node_tree.outputs.new(socket_type, name)

def parse_value(valstr):
    valstr = valstr.strip()
    if valstr in {"False", "false"}:
        return False
    if valstr in {"True", "true"}:
        return True
    if not valstr or valstr[0].isalpha() or valstr[0] in ["_"]:
        return valstr
    return eval(valstr)

def set_property(obj, prop, valstr):
    try:
        attr = getattr(obj, prop)
    except Exception:
        return
    try:
        if type(attr) == bool:
            if valstr in {"False", "false"}:
                value = False
            elif valstr in {"True", "true"}:
                value = True
            else:
                value = bool(parse_value(valstr))
        elif type(attr) == str:
            if valstr and valstr[0] in ['"', "'"]:
                value = eval(valstr)
            else:
                value = valstr
        else:
            value = eval(valstr)
        if type(attr) == bpy_prop_array:
            if type(value) not in [list, tuple]:
                # Older shader configs may use scalars for array defaults.
                value = (value,) * len(attr)
        setattr(obj, prop, value)
    except Exception:
        # Blender 5.x removed a number of UI/node properties that older
        # configs still try to restore. Ignore those and keep importing.
        return

def find_socket(sockets, sock):
    if "," in sock:
        index, name = sock.split(",")
        name = name.strip()
    else:
        index = sock
        name = None
    if name in use_index:
        index = int(index.strip())
        return sockets[index]
    elif name in sockets:
        return sockets[name]
    alias = socket_aliases.get(name)
    if alias and alias in sockets:
        return sockets[alias]
    return None

def build_nodes(matname, node_tree, ntcfg):
    for value in ntcfg.values:
        attr, val = value.name, value.value
        if attr == "name":
            continue
        set_property(node_tree, attr, val)
    if ntcfg.HasNode("inputs"):
        inputs = ntcfg.GetNode("inputs")
        for ip in inputs.GetNodes("input"):
            type = typemap[ip.GetValue("type")]
            name = ip.GetValue("name")
            input = node_tree_add_input(node_tree, type, name)
            if ip.HasValue("min_value"):
                value = ip.GetValue("min_value")
                set_property(input, "min_value", value)
            if ip.HasValue("max_value"):
                value = ip.GetValue("max_value")
                set_property(input, "max_value", value)
    if ntcfg.HasNode("outputs"):
        outputs = ntcfg.GetNode("outputs")
        for op in outputs.GetNodes("output"):
            type = typemap[op.GetValue("type")]
            name = op.GetValue("name")
            node_tree_add_output(node_tree, type, name)
    if not ntcfg.HasNode("nodes"):
        return
    refs = []
    nodes = node_tree.nodes
    for n in ntcfg.GetNode("nodes").nodes:
        sntype, sndata, line = n.name, n, n.line
        sntype = node_type_aliases.get(sntype, sntype)
        sn = nodes.new(sntype)
        for snvalue in sndata.values:
            a, v = snvalue.name, snvalue.value
            v = v.strip()
            if a == "parent":
                refs.append((sn, a, v))
                continue
            elif a == "node_tree":
                sn.node_tree = bpy.data.node_groups[v]
            else:
                set_property(sn, a, v)
        if sndata.HasNode("inputs"):
            input_nodes = sndata.GetNode("inputs").GetNodes("input")
            if sntype == "ShaderNodeVectorMath":
                # blender 2.82 has only 2 vector and 1 float input nodes
                # but blender 2.90 (2.83?) has 3 vector inputs
                # fortunately, the affects only the wrap operation which
                # none of the shaders use
                if len(sn.inputs) < 4:
                    del input_nodes[2]
            for i,ip in enumerate(input_nodes):
                if ip.HasValue("default_value"):
                    value = ip.GetValue("default_value")
                    name = ip.GetValue("name")
                    if name in use_index:
                        input = sn.inputs[i]
                    elif name in sn.inputs:
                        input = sn.inputs[name]
                    set_property (input, "default_value", value)
        if sndata.HasNode("outputs"):
            for i,op in enumerate(sndata.GetNode("outputs").GetNodes("output")):
                if op.HasValue("default_value"):
                    value = op.GetValue("default_value")
                    set_property(sn.outputs[i], "default_value", value)
    for r in refs:
        if r[1] == "parent" and r[2] in nodes:
            setattr(r[0], r[1], nodes[r[2]])
    if not ntcfg.HasNode("links"):
        return
    links = node_tree.links
    linknodes = ntcfg.GetNode("links")
    for ln in linknodes.GetNodes("link"):
        from_node = nodes[ln.GetValue("from_node")]
        to_node = nodes[ln.GetValue("to_node")]
        from_socket = find_socket(from_node.outputs, ln.GetValue("from_socket"))
        to_socket = find_socket(to_node.inputs, ln.GetValue("to_socket"))
        if from_socket and to_socket:
            links.new(from_socket, to_socket)

def call_update(item, prop, context):
    annotations = item.__annotations__[prop]
    if hasattr(annotations, "keywords"):
        keywords = annotations.keywords
    else:
        keywords = annotations[1]
    keywords["update"](item, context)

def set_tex(mu, dst, src, context):
    try:
        if src.index < 0:
            raise IndexError    # ick, but it works
        tex = mu.textures[src.index]
        if tex.name[-4:] in [".dds", ".png", ".tga", ".mbm"]:
            dst.tex = tex.name[:-4]
        else:
            dst.tex = tex.name
        dst.type = tex.type
        if hasattr(tex, "blender_image_name"):
            dst["blender_image_name"] = tex.blender_image_name
            dst['ksp_image_binding'] = True
        if hasattr(tex, 'source_filepath'):
            dst['ksp_texture_source'] = tex.source_filepath
    except IndexError:
        pass
    image = bpy.data.images.get(dst.get('blender_image_name', dst.tex))
    if image:
        dst.rgbNorm = not image.muimageprop.convertNorm
    dst.scale = src.scale
    dst.offset = src.offset
    if context.material.node_tree:
        call_update(dst, "tex", context)
        #other properties are all updated in the one updater
        call_update(dst, "rgbNorm", context)

def make_shader_prop(muprop, blendprop, context):
    for k in muprop:
        item = blendprop.add()
        item.name = k
        item.value = muprop[k]
        if context.material.node_tree:
            call_update(item, "value", context)

def make_shader_tex_prop(mu, muprop, blendprop, context):
    for k in muprop:
        item = blendprop.add()
        item.name = k
        set_tex(mu, item, muprop[k], context)

def create_nodes(mat):
    shaderName = mat.mumatprop.shaderName
    shaderConfigName = shader_aliases.get(shaderName, shaderName)
    if shaderConfigName in shader_configs:
        cfg = shader_configs[shaderConfigName]
        for extra in cfg.GetNodes("node_tree"):
            ntname = extra.GetValue("name")
            if not ntname in bpy.data.node_groups:
                node_tree = bpy.data.node_groups.new(ntname, "ShaderNodeTree")
                build_nodes(mat.name, node_tree, extra)
        matcfg = cfg.GetNode("Material")
        for value in matcfg.values:
            name, val = value.name, value.value
            set_property(mat, name, val)
        if mat.use_nodes:
            links = mat.node_tree.links
            nodes = mat.node_tree.nodes
            while len(links):
                links.remove(links[0])
            while len(nodes):
                nodes.remove(nodes[0])
        if mat.use_nodes and matcfg.HasNode("node_tree"):
            build_nodes(mat.name, mat.node_tree, matcfg.GetNode("node_tree"))
    else:
        print(f"WARNING: unknown shader: {shaderName}")

def _norm_name(name):
    return (name or "").replace(" ", "").replace("-", "").replace("_", "").lower()

def _find_socket(sockets, *names):
    for name in names:
        if name in sockets:
            return sockets[name]
    wanted = {_norm_name(name) for name in names}
    for socket in sockets:
        if _norm_name(socket.name) in wanted:
            return socket
    return None

def _find_named_node(nodes, node_type, names):
    wanted = {_norm_name(name) for name in names}
    candidates = []
    for node in nodes:
        if node_type and getattr(node, "type", None) != node_type:
            continue
        keys = {_norm_name(getattr(node, "name", "")),
                _norm_name(getattr(node, "label", ""))}
        if keys & wanted:
            return node
        if any(want and any(want in key for key in keys) for want in wanted):
            candidates.append(node)
    return candidates[0] if candidates else None

def _find_prop_value(prop_set, names):
    item = _find_prop_item(prop_set, names)
    return getattr(item, "value", None) if item else None

def _find_prop_item(prop_set, names):
    wanted = {_norm_name(name) for name in names}
    for item in getattr(prop_set, "properties", []):
        if _norm_name(getattr(item, "name", "")) in wanted:
            return item
    return None

def _resolve_image(texname):
    if not texname:
        return None
    if texname in bpy.data.images:
        return bpy.data.images[texname]
    return None

def _clear_links_to(node_tree, to_socket):
    if not to_socket:
        return
    for link in list(to_socket.links):
        node_tree.links.remove(link)

def _link(node_tree, from_socket, to_socket, clear=True):
    if not from_socket or not to_socket:
        return False
    if clear:
        _clear_links_to(node_tree, to_socket)
    node_tree.links.new(from_socket, to_socket)
    return True

def _set_default_color(socket, value):
    if not socket or value is None:
        return
    try:
        vals = list(value)
    except TypeError:
        return
    if len(vals) >= 3:
        if len(vals) < 4:
            vals.append(1.0)
        socket.default_value = vals[:4]

def _set_default_float(socket, value):
    if not socket or value is None:
        return
    try:
        socket.default_value = float(value)
    except (TypeError, ValueError):
        pass

def _create_texture_node(node_tree, texprop, location):
    if not texprop:
        return None
    node = node_tree.nodes.new("ShaderNodeTexImage")
    node.name = texprop.name
    node.label = texprop.name
    node.location = location
    image = _resolve_image(texprop.get("blender_image_name", ""))
    if image is None and not texprop.get('ksp_image_binding'):
        image = _resolve_image(texprop.tex)
    if image:
        normal_role = texprop.type or texprop.name.casefold() in ('_bumpmap', '_normalmap')
        if image.colorspace_settings.is_data != bool(normal_role):
            # One source can be referenced as both albedo and data. Never
            # change the color interpretation of another material's image.
            image = image.copy()
            image.colorspace_settings.is_data = bool(normal_role)
            image['ksp_texture_normal'] = bool(normal_role)
            texprop['blender_image_name'] = image.name
        node.image = image
    return node

def _texture_uv(tree, uv, tex, prop):
    if not tex:
        return
    # Image.texture_mapping is not a substitute for shader input coordinates.
    # Keep the original game scale/offset in RNA, apply it explicitly in nodes.
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.name = prop.name + ' UV Transform'
    mapping.vector_type = 'POINT'
    sx, sy = prop.scale
    ox, oy = prop.offset
    if tex.image and tex.image.muimageprop.invertY:
        sy, oy = -sy, 1 - oy
    mapping.inputs['Scale'].default_value = (sx, sy, 1)
    mapping.inputs['Location'].default_value = (ox, oy, 0)
    _link(tree, uv.outputs['UV'], mapping.inputs['Vector'])
    _link(tree, mapping.outputs['Vector'], tex.inputs['Vector'])


def _math(tree, operation, a, b):
    node = tree.nodes.new('ShaderNodeMath')
    node.operation = operation
    for socket, value in zip(node.inputs, (a, b)):
        if isinstance(value, (int, float)):
            socket.default_value = value
        else:
            _link(tree, value, socket)
    return node.outputs[0]


def _prop_output(mat, kind, names, fallback, label, value_channel=None):
    tree = mat.node_tree
    item = _find_prop_item(getattr(mat.mumatprop, kind), names)
    color = kind == 'color' and value_channel is None
    node = tree.nodes.new('ShaderNodeRGB' if color else 'ShaderNodeValue')
    node.name = label
    value = item.value if item else fallback
    node.outputs[0].default_value = value[value_channel] if item and value_channel is not None else value
    if item:
        index = next(i for i, p in enumerate(getattr(mat.mumatprop, kind).properties) if p == item)
        path = f'mumatprop.{kind}.properties[{index}].value'
        for channel in range(4) if color else (None,):
            fc = node.outputs[0].driver_add('default_value', channel) if color else node.outputs[0].driver_add('default_value')
            variable = fc.driver.variables.new()
            variable.name, variable.type = 'value', 'SINGLE_PROP'
            variable.targets[0].id_type = 'MATERIAL'
            variable.targets[0].id = mat
            component = value_channel if value_channel is not None else channel
            variable.targets[0].data_path = path + (f'[{component}]' if component is not None else '')
            fc.driver.expression = 'value'
    return node.outputs[0]


def _multiply_color(tree, a, b, name):
    node = tree.nodes.new('ShaderNodeMixRGB')
    node.name = name
    node.blend_type = 'MULTIPLY'
    node.inputs[0].default_value = 1
    _link(tree, a, node.inputs[1])
    _link(tree, b, node.inputs[2])
    return node.outputs[0]


def _normal_color(tree, tex, prop):
    if prop.rgbNorm:
        return tex.outputs['Color']
    # Unity DXT5nm stores X in alpha and Y in green. Reconstruct Z without
    # modifying the source image, so exporting retains the original resource.
    separate = tree.nodes.new('ShaderNodeSeparateColor')
    _link(tree, tex.outputs['Color'], separate.inputs['Color'])
    x = _math(tree, 'MULTIPLY_ADD', tex.outputs['Alpha'], 2)
    # MULTIPLY_ADD's third input defaults to zero, set it explicitly to -1.
    x.node.inputs[2].default_value = -1
    y = _math(tree, 'MULTIPLY_ADD', separate.outputs['Green'], 2)
    y.node.inputs[2].default_value = -1
    xy = _math(tree, 'ADD', _math(tree, 'MULTIPLY', x, x), _math(tree, 'MULTIPLY', y, y))
    z = _math(tree, 'SQRT', _math(tree, 'MAXIMUM', _math(tree, 'SUBTRACT', 1, xy), 0), 0)
    z = _math(tree, 'MULTIPLY_ADD', z, .5)
    z.node.inputs[2].default_value = .5
    combine = tree.nodes.new('ShaderNodeCombineColor')
    _link(tree, tex.outputs['Alpha'], combine.inputs['Red'])
    _link(tree, separate.outputs['Green'], combine.inputs['Green'])
    _link(tree, z, combine.inputs['Blue'])
    return combine.outputs[0]

def ensure_principled_preview(mat):
    """Build a clean Blender-friendly material graph for imported KSP mats.

    KSP export data is stored in mat.mumatprop, so imported materials do not
    need to keep the large compatibility node groups visible.  The clean graph
    intentionally matches a normal Blender workflow:

        UV Map -> _MainTex -> Principled BSDF Base Color -> Material Output
        UV Map -> _Emissive -> Principled BSDF Emission Color
    """
    if not mat:
        return

    mat.use_nodes = True
    node_tree = mat.node_tree
    if not node_tree:
        return

    nodes = node_tree.nodes
    links = node_tree.links
    # Only the generated node preview is rebuilt. Material Actions and KSP
    # source properties/clip bindings are separate IDs and remain untouched.
    node_tree.animation_data_clear()
    while len(links):
        links.remove(links[0])
    while len(nodes):
        nodes.remove(nodes[0])

    uv = nodes.new("ShaderNodeUVMap")
    uv.name = "UV Map"
    uv.location = (-850, 0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = KSP_PREVIEW_PRINCIPLED
    principled.location = (-150, 0)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "Material Output"
    output.location = (250, 0)

    main_prop = _find_prop_item(mat.mumatprop.texture,
                                ("_MainTex", "MainTex", "_BaseMap", "BaseMap"))
    emissive_prop = _find_prop_item(mat.mumatprop.texture,
                                    ("_Emissive", "_EmissiveMap",
                                     "_Emission", "_EmissionMap"))
    main_tex = _create_texture_node(node_tree, main_prop, (-550, 110))
    emissive_tex = _create_texture_node(node_tree, emissive_prop, (-550, -140))

    base_color = _find_socket(principled.inputs, "Base Color", "BaseColor")
    emission_color = _find_socket(principled.inputs, "Emission Color",
                                  "Emission", "EmissionColor")
    emission_strength = _find_socket(principled.inputs, "Emission Strength",
                                     "EmissionStrength")
    surface = _find_socket(output.inputs, "Surface")
    bsdf = _find_socket(principled.outputs, "BSDF")
    uv_out = _find_socket(uv.outputs, "UV")

    if main_tex:
        _texture_uv(node_tree, uv, main_tex, main_prop)
        tint = _prop_output(mat, 'color', ('_Color', '_BaseColor'), (1, 1, 1, 1), 'KSP Tint')
        _link(node_tree, _multiply_color(node_tree, main_tex.outputs['Color'], tint, 'KSP Albedo'), base_color)
    else:
        value = _find_prop_value(mat.mumatprop.color, ("_Color", "_BaseColor"))
        _link(node_tree, _prop_output(mat, 'color', ('_Color', '_BaseColor'), value or (1, 1, 1, 1), 'KSP Tint'), base_color)

    if emissive_tex:
        _texture_uv(node_tree, uv, emissive_tex, emissive_prop)
        tint = _prop_output(mat, 'color', ('_EmissiveColor', '_EmissionColor'), (1, 1, 1, 1), 'KSP Emission Tint')
        _link(node_tree, _multiply_color(node_tree, emissive_tex.outputs['Color'], tint, 'KSP Emission'), emission_color)
        _set_default_float(emission_strength, 1.0)
    else:
        value = _find_prop_value(mat.mumatprop.color,
                                 ("_EmissiveColor", "_EmissionColor"))
        if value is not None:
            _link(node_tree, _prop_output(mat, 'color', ('_EmissiveColor', '_EmissionColor'), value, 'KSP Emission Tint'), emission_color)
            _set_default_float(emission_strength, 1.0)

    shader = mat.mumatprop.shaderName.casefold()
    # Specular texture alpha is a specular mask, NOT transparency.
    if 'specular' in shader and main_tex:
        _link(node_tree, main_tex.outputs['Alpha'], principled.inputs['Specular IOR Level'])
    shininess = _find_prop_value(mat.mumatprop.float3, ('_Shininess',))
    if shininess is not None:
        principled.inputs['Roughness'].default_value = (2 / (2 + max(0, shininess) * 128)) ** .5
    normal_prop = _find_prop_item(mat.mumatprop.texture, ('_BumpMap', '_NormalMap'))
    normal_tex = _create_texture_node(node_tree, normal_prop, (-550, -400))
    if normal_tex and normal_tex.image:
        _texture_uv(node_tree, uv, normal_tex, normal_prop)
        normal = nodes.new('ShaderNodeNormalMap')
        normal.name = 'KSP Normal Map'
        _link(node_tree, _normal_color(node_tree, normal_tex, normal_prop), normal.inputs['Color'])
        _link(node_tree, normal.outputs['Normal'], principled.inputs['Normal'])
    if 'cutoff' in shader or 'translucent' in shader or 'transparent' in shader:
        alpha = main_tex.outputs['Alpha'] if main_tex else 1
        tint_alpha = _prop_output(mat, 'color', ('_Color', '_BaseColor'), 1, 'KSP Tint Alpha', value_channel=3)
        alpha = _math(node_tree, 'MULTIPLY', alpha, tint_alpha)
        opacity = _prop_output(mat, 'float3', ('_Opacity',), 1, 'KSP Opacity')
        alpha = _math(node_tree, 'MULTIPLY', alpha, opacity)
        if 'cutoff' in shader:
            cutoff = _prop_output(mat, 'float3', ('_Cutoff',), .5, 'KSP Alpha Cutoff')
            alpha = _math(node_tree, 'GREATER_THAN', alpha, cutoff)
        _link(node_tree, alpha, principled.inputs['Alpha'])
        mat.surface_render_method = 'DITHERED'
    mat.diffuse_color = _find_prop_value(mat.mumatprop.color, ('_Color', '_BaseColor')) or (1, 1, 1, 1)
    _link(node_tree, bsdf, surface)
    from .preview_layout import compact_preview
    compact_preview(mat)

def make_shader4(mumat, mu):
    mat = bpy.data.materials.new(mumat.name)
    matprops = mat.mumatprop
    matprops.shaderName = mumat.shaderName
    mat['ksp_imported_material'] = True
    mu.data_issues.append(f'Blender Principled preview: {mumat.name}: {mumat.shaderName}; Unity lighting/runtime effects not simulated')
    if mumat.shaderName not in shader_configs and not mumat.shaderName.startswith('KSP/'):
        mu.data_issues.append(f'Approximate Blender shader conversion: {mumat.name}: {mumat.shaderName}')
    # Imported materials use the explicit Blender preview below. Building an
    # obsolete compatibility graph first can mutate shared image color spaces
    # through legacy callbacks and report supported Cutoff shaders as unknown.
    class Context:
        pass
    ctx = Context()
    ctx.material = mat
    make_shader_prop(mumat.colorProperties, matprops.color.properties, ctx)
    make_shader_prop(mumat.vectorProperties, matprops.vector.properties, ctx)
    make_shader_prop(mumat.floatProperties2, matprops.float2.properties, ctx)
    make_shader_prop(mumat.floatProperties3, matprops.float3.properties, ctx)
    make_shader_tex_prop(mu, mumat.textureProperties, matprops.texture.properties, ctx)
    ensure_principled_preview(mat)
    return mat

def make_shader(mumat, mu):
    return make_shader4(mumat, mu)
