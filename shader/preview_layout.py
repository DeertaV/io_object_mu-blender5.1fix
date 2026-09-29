"""Compact generated preview graphs without changing KSP data or shader math."""
import hashlib
import json
import bpy


def _value(value):
    return list(value) if hasattr(value, '__len__') and not isinstance(value, str) else value


def _socket_type(socket):
    return {'RGBA': 'NodeSocketColor', 'VECTOR': 'NodeSocketVector',
            'VALUE': 'NodeSocketFloat'}[socket.type]


def _driver(tree, socket):
    path = socket.path_from_id('default_value')
    drivers = tree.animation_data.drivers if tree.animation_data else []
    result = []
    for fc in drivers:
        if fc.data_path == path:
            result.append((fc.array_index, fc.driver.expression,
                           [(v.name, v.type, v.targets[0].id_type, v.targets[0].id,
                             v.targets[0].data_path) for v in fc.driver.variables]))
    return result


def _restore_driver(socket, records):
    for index, expression, variables in records:
        fc = socket.driver_add('default_value', index) if socket.type == 'RGBA' else socket.driver_add('default_value')
        fc.driver.expression = expression
        for name, kind, id_type, target, path in variables:
            variable = fc.driver.variables.new()
            variable.name, variable.type = name, kind
            variable.targets[0].id_type, variable.targets[0].id = id_type, target
            variable.targets[0].data_path = path


def _label(socket, output=False):
    names = {'KSP Tint': '颜色', 'KSP Emission Tint': '发光颜色',
             'KSP Tint Alpha': '颜色透明度', 'KSP Opacity': '不透明度',
             'KSP Alpha Cutoff': '裁切阈值', '_MainTex': '基础贴图',
             '_Emissive': '发光贴图', '_BumpMap': '法线贴图'}
    if output:
        return {'Base Color': '基础色', 'Emission Color': '发光',
                'Alpha': '透明度', 'Normal': '法线'}.get(socket.name, socket.name)
    name = names.get(socket.node.name, socket.node.name)
    return name + (' Alpha' if socket.name == 'Alpha' else '')


def _pack(tree, selected, title):
    """Parameters/drivers stay on the MATERIAL's group instance, not inside
    the shared functional group. This keeps per-part animation independent.
    Called only for freshly generated plugin nodes, never arbitrary user graphs.
    """
    ordered = [n for n in tree.nodes if n in selected]
    constants = [n for n in ordered if n.type in {'RGB', 'VALUE'}]
    internal = [n for n in ordered if n not in constants]
    boundary_inputs = []
    for node in constants:
        boundary_inputs.append((node.outputs[0], _label(node.outputs[0]),
                                _value(node.outputs[0].default_value), _driver(tree, node.outputs[0])))
    for link in tree.links:
        if link.to_node in selected and link.from_node not in selected:
            if not any(source == link.from_socket for source, *_ in boundary_inputs):
                boundary_inputs.append((link.from_socket, _label(link.from_socket), None, []))
    boundary_outputs = []
    for link in tree.links:
        if link.from_node in selected and link.to_node not in selected:
            if not any(source == link.from_socket for source, _ in boundary_outputs):
                boundary_outputs.append((link.from_socket, _label(link.to_socket, True)))
    if not boundary_outputs:
        return None
    # A group with just an unmodified constant adds no useful complexity.
    if len(ordered) == 1 and ordered[0].type not in {'RGB', 'VALUE'}:
        return None
    links = list(tree.links)
    external = [(link.from_socket, link.to_socket) for link in links
                if link.from_node in selected and link.to_node not in selected]
    input_map = {source: index for index, (source, *_) in enumerate(boundary_inputs)}
    node_map = {node: index for index, node in enumerate(internal)}
    signature = []
    for node in internal:
        signature.append([node.bl_idname, getattr(node, 'operation', None), getattr(node, 'blend_type', None),
                          getattr(node, 'mode', None), getattr(node, 'space', None),
                          [_value(s.default_value) if hasattr(s, 'default_value') else None for s in node.inputs]])
    connection = []
    for link in links:
        if link.to_node in internal:
            source = ('input', input_map[link.from_socket]) if link.from_socket in input_map else (
                'node', node_map[link.from_node], list(link.from_node.outputs).index(link.from_socket))
            connection.append([source, node_map[link.to_node], list(link.to_node.inputs).index(link.to_socket)])
    output_sources = [('input', input_map[s]) if s in input_map else
                      ('node', node_map[s.node], list(s.node.outputs).index(s)) for s, _ in boundary_outputs]
    digest = hashlib.sha256(json.dumps([signature, connection, output_sources,
        [(label, _socket_type(s)) for s, label, *_ in boundary_inputs],
        [(label, _socket_type(s)) for s, label in boundary_outputs]], sort_keys=True).encode()).hexdigest()
    group = next((g for g in bpy.data.node_groups if g.get('ksp_compact_signature') == digest), None)
    if group is None:
        group = bpy.data.node_groups.new(title, 'ShaderNodeTree')
        group['ksp_compact_signature'] = digest
        for source, label, *_ in boundary_inputs:
            group.interface.new_socket(name=label, in_out='INPUT', socket_type=_socket_type(source))
        for source, label in boundary_outputs:
            group.interface.new_socket(name=label, in_out='OUTPUT', socket_type=_socket_type(source))
        entry = group.nodes.new('NodeGroupInput')
        exit = group.nodes.new('NodeGroupOutput')
        copied = []
        for node in internal:
            clone = group.nodes.new(node.bl_idname)
            clone.name = node.name
            for attr in ('operation', 'blend_type', 'use_clamp', 'mode', 'space', 'uv_map'):
                if hasattr(node, attr):
                    setattr(clone, attr, getattr(node, attr))
            for source, dest in zip(node.inputs, clone.inputs):
                if hasattr(source, 'default_value'):
                    dest.default_value = _value(source.default_value)
            copied.append(clone)
        def from_source(source):
            return entry.outputs[source[1]] if source[0] == 'input' else copied[source[1]].outputs[source[2]]
        for source, node, socket in connection:
            group.links.new(from_source(source), copied[node].inputs[socket])
        for index, source in enumerate(output_sources):
            group.links.new(from_source(source), exit.inputs[index])
        arrange_nodes(group)
    instance = tree.nodes.new('ShaderNodeGroup')
    instance.node_tree, instance.name, instance.label = group, title, title
    for index, (source, _, default, drivers) in enumerate(boundary_inputs):
        if default is not None:
            instance.inputs[index].default_value = default
            _restore_driver(instance.inputs[index], drivers)
        else:
            tree.links.new(source, instance.inputs[index])
    for source, dest in external:
        index = next(i for i, (s, _) in enumerate(boundary_outputs) if s == source)
        tree.links.new(instance.outputs[index], dest)
    for node in ordered:
        for socket in node.outputs:
            if hasattr(socket, 'default_value') and _driver(tree, socket):
                if socket.type == 'RGBA':
                    for channel in range(4):
                        socket.driver_remove('default_value', channel)
                else:
                    socket.driver_remove('default_value')
        tree.nodes.remove(node)
    return instance


def arrange_nodes(tree):
    """Left-to-right topological columns with conservative non-overlap spacing."""
    nodes = list(tree.nodes)
    depth = {}
    def level(node, visiting=()):
        if node in depth:
            return depth[node]
        if node in visiting:
            return 0
        parents = [l.from_node for l in tree.links if l.to_node == node and l.from_node != node]
        depth[node] = max((level(p, visiting + (node,)) + 1 for p in parents), default=0)
        return depth[node]
    for node in nodes:
        level(node)
    columns = {}
    for node in nodes:
        columns.setdefault(depth[node], []).append(node)
    for column, items in columns.items():
        y = 0
        items.sort(key=lambda n: (2 if '法线' in n.name or n.type == 'NORMAL_MAP' or n.name == '_BumpMap' else
                                 1 if n.name == '_Emissive' else 0))
        for node in items:
            node.location = (column * 310, y)
            node.width = 240 if node.type in {'TEX_IMAGE', 'BSDF_PRINCIPLED'} else 210
            node.hide = node.type in {'MAPPING', 'UVMAP'}
            height = 460 if node.type == 'TEX_IMAGE' else (700 if node.type == 'BSDF_PRINCIPLED' else
                     100 if node.hide else max(210, 100 + len(node.inputs) * 24))
            y -= height + 100
    for node in nodes:
        node.select = False


def copy_preview_tree(source_mat, dest_mat):
    """Commit a validated generated graph while retaining the Material ID.
    Shader source Actions and all persistent clip pointers refer to that ID.
    """
    source, dest = source_mat.node_tree, dest_mat.node_tree
    dest.animation_data_clear()
    dest.nodes.clear()
    copies = {}
    for node in source.nodes:
        clone = dest.nodes.new(node.bl_idname)
        copies[node] = clone
        clone.name, clone.label = node.name, node.label
        for attr in ('node_tree', 'image', 'interpolation', 'extension', 'projection',
                     'vector_type', 'operation', 'blend_type', 'space', 'uv_map', 'target'):
            if hasattr(node, attr):
                setattr(clone, attr, getattr(node, attr))
        clone.location, clone.width, clone.hide = node.location, node.width, node.hide
        for a, b in zip(node.inputs, clone.inputs):
            if hasattr(a, 'default_value'):
                b.default_value = _value(a.default_value)
            records = _driver(source, a) if hasattr(a, 'default_value') else []
            records = [(i, expr, [(n, k, t, dest_mat if owner == source_mat else owner, p)
                                  for n, k, t, owner, p in variables]) for i, expr, variables in records]
            _restore_driver(b, records)
    for link in source.links:
        dest.links.new(copies[link.from_node].outputs[list(link.from_node.outputs).index(link.from_socket)],
                       copies[link.to_node].inputs[list(link.to_node.inputs).index(link.to_socket)])


def compact_preview(mat):
    tree = mat.node_tree
    # Undriven constants do not need their own visible nodes.
    for node in list(tree.nodes):
        if node.type in {'RGB', 'VALUE'} and not _driver(tree, node.outputs[0]):
            for link in list(node.outputs[0].links):
                link.to_socket.default_value = _value(node.outputs[0].default_value)
            tree.nodes.remove(node)
    # Remove identity UV transforms and redundant fallback multiply-by-one.
    for node in list(tree.nodes):
        if node.type == 'MAPPING' and tuple(node.inputs['Scale'].default_value) == (1, 1, 1) and tuple(
                node.inputs['Location'].default_value) == (0, 0, 0):
            source = node.inputs['Vector'].links[0].from_socket
            for link in list(node.outputs[0].links):
                tree.links.new(source, link.to_socket)
            tree.nodes.remove(node)
    for node in list(tree.nodes):
        if node.type == 'UVMAP' and all(l.to_node.type == 'TEX_IMAGE' for l in node.outputs[0].links):
            tree.nodes.remove(node)  # Image Texture defaults to active UV.
    mappings = {}
    for node in list(tree.nodes):
        if node.type == 'MAPPING':
            key = tuple(tuple(node.inputs[p].default_value) for p in ('Location', 'Rotation', 'Scale'))
            if key in mappings:
                for link in list(node.outputs[0].links):
                    tree.links.new(mappings[key].outputs[0], link.to_socket)
                tree.nodes.remove(node)
            else:
                mappings[key] = node
    for node in list(tree.nodes):
        if node.type == 'MIX_RGB' and node.blend_type == 'MULTIPLY':
            if not node.inputs[2].is_linked and tuple(node.inputs[2].default_value) == (1, 1, 1, 1):
                source = node.inputs[1].links[0].from_socket
                for link in list(node.outputs[0].links):
                    tree.links.new(source, link.to_socket)
                tree.nodes.remove(node)
    for node in list(tree.nodes):
        if node.type == 'MATH' and node.operation == 'MULTIPLY':
            for index in (0, 1):
                if not node.inputs[index].is_linked and node.inputs[index].default_value == 1 and node.inputs[1 - index].is_linked:
                    source = node.inputs[1 - index].links[0].from_socket
                    for link in list(node.outputs[0].links):
                        tree.links.new(source, link.to_socket)
                    tree.nodes.remove(node)
                    break
    # GA normal reconstruction is one expandable node, not a screenful of math.
    normal = tree.nodes.get('KSP Normal Map')
    normals = set()
    def visit(node):
        if node in normals or node.type in {'TEX_IMAGE', 'MAPPING', 'UVMAP'}:
            return
        normals.add(node)
        for socket in node.inputs:
            for link in socket.links:
                visit(link.from_node)
    if normal:
        visit(normal)
        if len(normals) > 1:
            _pack(tree, normals, 'KSP 法线转换')
    controls = {n for n in tree.nodes if n.type in {'RGB', 'VALUE', 'MIX_RGB', 'MATH'}}
    if controls:
        _pack(tree, controls, 'KSP 颜色与透明')
    arrange_nodes(tree)
    mat['ksp_preview_version'] = 2
