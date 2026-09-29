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

from struct import unpack
import os.path
from pathlib import Path

import bpy
from mathutils import Vector

def load_mbm(mbmpath):
    with open(mbmpath, 'rb') as mbmfile:
        header = mbmfile.read(20)
        if len(header) != 20:
            raise ValueError('Truncated MBM header')
        magic, width, height, bump, bpp = unpack('<5i', header)
        if magic != 0x50534b03 or width <= 0 or height <= 0 or bpp not in (24, 32):
            raise ValueError('Invalid MBM header')
        raw = mbmfile.read(width * height * (bpp // 8))
        if len(raw) != width * height * (bpp // 8):
            raise ValueError('Truncated MBM pixels')
        if bpp == 32:
            pixels = raw
        else:
            pixels = [0, 0, 0, 255] * width * height
            for i in range(width * height):
                pixels[i * 4:i * 4 + 3] = raw[i * 3:i * 3 + 3]
    return width, height, pixels

def load_image(base, ext, path, type):
    name = base + ext
    if ext.lower() in [".dds", ".png", ".tga"]:
        img = bpy.data.images.load(os.path.abspath(os.path.join(path, name)))
        img.name = base
        img.muimageprop.invertY = False
        if ext.lower() == ".dds":
            img.muimageprop.invertY = True
        pixels = img.pixels[:1024]#256 pixels
        if base[-2:].lower() == "_n" or base[-3:].lower() == "nrm":
            type = 1
    elif ext.lower() == ".mbm":
        w,h, pixels = load_mbm(os.path.join(path, name))
        img = bpy.data.images.new(base, w, h)
        img.pixels[:] = map(lambda x: x / 255.0, pixels)
        img.pack()
        pixels = [p / 255.0 for p in pixels[:1024]]
    img.alpha_mode = 'STRAIGHT'
    img.muimageprop.invertY = (ext.lower() == ".dds")
    img.muimageprop.convertNorm = False
    img.colorspace_settings.is_data = False
    if type == 1:
        img.colorspace_settings.is_data = True
        for i in range(min(int(len(pixels)/4), 256)):
            c = 2*Vector(pixels[i*4:i*4+4])-Vector((1, 1, 1, 1))
            if abs(c.x*c.x + c.y*c.y + c.z*c.z - 1) > 0.05:
                img.muimageprop.convertNorm = True
    return img

EXTENSIONS = ('.dds', '.mbm', '.tga', '.png', '.jpg', '.jpeg')
_shared_index = {}


def texture_root(path):
    for parent in (Path(path), *Path(path).parents):
        if parent.name.casefold() == 'gamedata':
            return str(parent)
    return None


def _case_file(path):
    """Literal, case-insensitive component matching; never substring guessing."""
    if os.path.isfile(path):
        return os.path.abspath(path)
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        if not current.is_dir():
            return None
        matches = [p for p in current.iterdir() if p.name.casefold() == part.casefold()]
        if len(matches) != 1:
            return None
        current = matches[0]
    return str(current) if current.is_file() else None


def resolve_texture(name, directory, root=None, allow_shared=True):
    name = name.strip().strip('"\'').replace('\\', '/')
    root = root or texture_root(directory)
    if name.casefold().startswith('gamedata/'):
        name = name[len('gamedata/'):]
    stem, ext = os.path.splitext(name)
    if ext.lower() not in EXTENSIONS:
        stem = name
    extensions = ([ext.lower()] if ext.lower() in EXTENSIONS else [])
    extensions += [e for e in EXTENSIONS if e not in extensions]
    bases = [os.path.join(directory, stem)]
    if root:
        bases.append(os.path.join(root, stem))
    for base in dict.fromkeys(bases):
        for extension in extensions:
            found = _case_file(base + extension)
            if found:
                return found, ''
    # Older stock .mu files reference textures relocated into shared Assets
    # folders. Only a unique exact basename across GameData is recoverable.
    if root and allow_shared and '/' not in stem:
        if root not in _shared_index:
            index = {}
            for parent, _, files in os.walk(root):
                for file in files:
                    base, suffix = os.path.splitext(file)
                    if suffix.lower() in EXTENSIONS:
                        index.setdefault(base.casefold(), []).append(os.path.join(parent, file))
            _shared_index[root] = index
        choices = _shared_index[root].get(stem.casefold(), [])
        locations = {os.path.splitext(p)[0].casefold() for p in choices}
        if len(locations) > 1:
            return None, 'ambiguous texture: ' + '; '.join(choices)
        for extension in extensions:
            matches = [p for p in choices if os.path.splitext(p)[1].lower() == extension]
            if len(matches) == 1:
                return matches[0], 'unique shared texture'
            if len(matches) > 1:
                return None, 'ambiguous texture: ' + '; '.join(matches)
    return None, f'not found; directory={directory}; GameData={root or "<none>"}'


def load_texture_file(filepath, normal=False):
    """Reuse only the exact source AND role, and pack bytes for portable .blend."""
    source = os.path.abspath(filepath).replace('\\', '/')
    for image in bpy.data.images:
        if (image.get('ksp_texture_source', '').casefold() == source.casefold()
                and image.get('ksp_texture_normal', False) == bool(normal)
                and image.size[0] and image.size[1]):
            return image
    base, ext = os.path.splitext(os.path.basename(filepath))
    if ext.lower() in ('.jpg', '.jpeg'):
        image = bpy.data.images.load(source)
        image.muimageprop.invertY = False
        image.muimageprop.convertNorm = False
    else:
        image = load_image(base, ext, os.path.dirname(source), int(normal))
    image.colorspace_settings.is_data = bool(normal)
    image['ksp_texture_source'] = source
    image['ksp_texture_normal'] = bool(normal)
    if not image.size[0] or not image.size[1]:
        raise RuntimeError('image decoded with zero dimensions: ' + source)
    image.pack()
    return image


def create_textures(mu, path):
    normals = {prop.index for mat in mu.materials for name, prop in mat.textureProperties.items()
               if name.casefold() in ('_bumpmap', '_normalmap')}
    for index, tex in enumerate(mu.textures):
        tex.blender_image_name = ''  # Missing source must not bind a namesake image.
        filepath, detail = resolve_texture(tex.name, path)
        if not filepath:
            users = [f'{mat.name}/{name}' for mat in mu.materials for name, prop in mat.textureProperties.items()
                     if prop.index == index]
            mu.data_issues.append(f'Missing texture #{index}: {tex.name}; material channels={", ".join(users)}: {detail}')
            continue
        try:
            img = load_texture_file(filepath, tex.type == 1 or index in normals)
            tex.blender_image_name = img.name
            tex.source_filepath = filepath
            if detail:
                mu.data_issues.append(f'Recovered texture: {tex.name} -> {filepath} ({detail})')
        except (OSError, RuntimeError, ValueError) as exc:
            mu.data_issues.append(f'Texture decode failed: {tex.name}: {filepath}: {exc}')
