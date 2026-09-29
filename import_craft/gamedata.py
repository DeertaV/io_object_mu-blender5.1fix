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
import os
import posixpath
import difflib
import json

from ..cfgnode import ConfigNode, ConfigNodeError
from ..model import Model
from .part import Part
from ..prop import Prop
from ..import_mu import MuImportError

def game_data_root(path):
    """Accept GameData itself or a game folder containing GameData."""
    if not path or not path.strip():
        raise MuImportError('GameData', 'Please select a KSP game directory or its GameData directory')
    path = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
    if not os.path.isdir(path):
        raise MuImportError("GameData", f"GameData directory does not exist: {path}")
    children = [entry.path for entry in os.scandir(path)
                if entry.is_dir() and entry.name.casefold() == 'gamedata']
    if len(children) == 1:
        path = children[0]
    return path.replace('\\', '/').rstrip('/')

def recurse_tree(path, func):
    files = os.listdir(path)
    files.sort()
    for f in files:
        if f.startswith('.'):
            continue
        p = "/".join((path, f))
        if os.path.isdir(p):
            recurse_tree(p, func)
        else:
            func(p)

class Internal(Part):
    def __init__(self, path, cfg):
        super().__init__(path, cfg)
        self.name = cfg.GetValue('name') or ''

class GameData:
    ModuleManager = "ModuleManager.ConfigCache"

    def get_gdpath(self, path):
        return path[len(self.root)+1:]

    def process_mu(self, path):
        gdpath = self.get_gdpath(path)
        directory, model = os.path.split(gdpath)
        if directory not in self.model_by_path:
            self.model_by_path[directory] = []
        if model[:-3] not in self.model_by_path[directory]:
            self.model_by_path[directory].append(model[:-3])
        url = gdpath[:-3]
        if url not in self.models:
            self.models[url] = path
        self._model_keys.setdefault(url.casefold(), set()).add(url)
        self._directory_keys.setdefault(directory.casefold(), set()).add(directory)
        self._basename_keys.setdefault(posixpath.basename(url).casefold(), set()).add(url)

    def process_cfgnode(self, path, node):
        if node.name in {'PART', 'PROP', 'INTERNAL'}:
            path = path.replace('\\', '/').lstrip('/')
            if path.lower().startswith('gamedata/'):
                path = path[len('GameData/'):]
            node.source_url = path
            cls, table = {'PART': (Part, self.parts), 'PROP': (Prop, self.props),
                          'INTERNAL': (Internal, self.internals)}[node.name]
            definition = cls(path, node)
            if not definition.name:
                self.database_issues.append(f'{path}: {node.name} missing name; not indexed')
                return
            definition.db = self
            records = self._definition_records[node.name].setdefault(definition.name, [])
            signature = node.ToString(-1)
            if not any(old.cfg.source_url == path and old.cfg.ToString(-1) == signature for old in records):
                records.append(definition)
            table.setdefault(definition.name, definition)
            active = [record for record in records if 'zdeprecated' not in record.cfg.source_url.casefold().split('/')]
            if len(active) == 1:
                table[definition.name] = active[0]
            self._definition_keys[node.name].setdefault(definition.name.casefold(), set()).add(definition.name)
        elif node.name == "RESOURCE_DEFINITION":
            res = node
            resname = res.GetValue("name")
            self.resources[resname] = res
        elif node.name == "Localization":
            if not node.nodes:
                return
            locs = next((lang for lang in node.nodes if lang.name.lower() == 'en-us'), node.nodes[0])
            for loc in locs.values:
                self.localizations[loc.name] = loc.value

    def process_cfg(self, path):
        if self.use_module_manager:
            return
        try:
            cfg = ConfigNode.loadfile(path, allow_unnamed=True)
        except ConfigNodeError as e:
            print(path+e.message)
            self.database_issues.append(e.message)
            return
        if not cfg:
            return
        self.database_issues.extend(getattr(cfg, 'parse_issues', ()))
        for node in cfg.nodes:
            gdpath = self.get_gdpath(path)
            self.process_cfgnode(gdpath, node)

    def build_db(self, path):
        path = path.replace("\\", "/")
        if path[-4:].lower() == ".cfg":
            self.process_cfg(path)
            return
        if path[-3:].lower() == ".mu":
            self.process_mu(path)
            return

    def parse_module_manager(self, mmcache):
        try:
            cfg = ConfigNode.loadfile(mmcache, allow_unnamed=True)
        except ConfigNodeError as e:
            print(mmcache+e.message)
            self.database_issues.append(f'ModuleManager cache rejected: {e.message}; raw CFG fallback is not patched game data')
            return False
        top_nodes = cfg.nodes if isinstance(cfg, ConfigNode) else cfg
        self.database_issues.extend(getattr(cfg, 'parse_issues', ()))
        accepted = 0
        for urlconfig in top_nodes:
            if urlconfig.name != "UrlConfig":
                continue
            path = urlconfig.GetValue("parentUrl")
            if not path:
                continue
            for node in urlconfig.nodes:
                if node.name in {"PART", "PROP", "INTERNAL",
                                 "RESOURCE_DEFINITION", "Localization"}:
                    self.process_cfgnode(path, node)
                    if node.name in {'PART', 'PROP', 'INTERNAL'}:
                        accepted += 1
        if not accepted:
            self.database_issues.append('ModuleManager cache has no usable asset definitions; raw CFG fallback')
        return bool(accepted)

    def create_db(self):
        mmcache = "/".join((self.root, self.ModuleManager))
        if os.access(mmcache, os.F_OK):
            if self.parse_module_manager(mmcache):
                self.use_module_manager = True
        recurse_tree(self.root, self.build_db)
        for k in self.model_by_path:
            self.model_by_path[k].sort()

    def __init__(self, path):
        self.use_module_manager = False
        self.root = game_data_root(path)
        from ..import_mu.textures import _shared_index
        _shared_index.pop(self.root, None)
        self.cache_stamp = self.configuration_stamp()
        self.model_by_path = {}
        self.models = Model.Preloaded(root=self.root)
        self._model_keys = {}
        self._directory_keys = {}
        self._basename_keys = {}
        self.mod_names = {entry.name.casefold() for entry in os.scandir(self.root) if entry.is_dir()}
        for url in self.models:
            self._model_keys.setdefault(url.casefold(), set()).add(url)
            self._basename_keys.setdefault(posixpath.basename(url).casefold(), set()).add(url)
        self.lookup_messages = []
        self.database_issues = []
        self.model_aliases = self.scene_aliases().get(self.root.casefold(), {})
        if not isinstance(self.model_aliases, dict):
            self.model_aliases = {}
        self.import_generation = 0
        # Scene caches must never replace fresh ModuleManager/source definitions.
        self.parts = {}
        self.props = {}
        self._definition_records = {kind: {} for kind in ('PART', 'PROP', 'INTERNAL')}
        self._definition_keys = {kind: {} for kind in self._definition_records}
        self.internals = {}
        self.localizations = {}
        self.resources = {}
        self.create_db()

    def configuration_stamp(self):
        from ..model.model import model_stamp
        return model_stamp(os.path.join(self.root, self.ModuleManager))

    @staticmethod
    def scene_aliases():
        import bpy
        try:
            data = json.loads(bpy.context.scene.get('ksp_model_aliases', '{}'))
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def alias_key(self, url, directory):
        return json.dumps([(self._normalize_url(directory) or '').casefold(),
                           (self._normalize_url(url) or '').casefold()], ensure_ascii=False)

    def sync_aliases(self):
        current = self.scene_aliases().get(self.root.casefold(), {})
        current = current if isinstance(current, dict) else {}
        if current != self.model_aliases:
            self.model_aliases = current
            self.invalidate_definitions()

    def invalidate_definitions(self):
        for table in (self.parts, self.props, self.internals):
            for definition in table.values():
                definition.model = None
                if hasattr(definition, 'model_unavailable'):
                    definition.model_unavailable = False
                    definition.missing_model_messages = []
                if hasattr(definition, 'variant_models'):
                    definition.variant_models.clear()

    def set_alias(self, url, directory, target=None):
        import bpy
        key = self.alias_key(url, directory)
        if target is None:
            self.model_aliases.pop(key, None)
        else:
            self.model_aliases[key] = target
        saved = self.scene_aliases()
        saved[self.root.casefold()] = self.model_aliases
        bpy.context.scene['ksp_model_aliases'] = json.dumps(saved, ensure_ascii=False)
        # Only future imports are invalidated. Existing scene objects/collections
        # remain intact, including partially imported models the user edited.
        self.invalidate_definitions()

    def find_definition(self, name, kind='PART', diagnostics=None):
        notes = diagnostics if diagnostics is not None else []
        table = {'PART': self.parts, 'PROP': self.props, 'INTERNAL': self.internals}[kind]
        requested = str(name or '').strip()
        canonical = requested.replace('_', '.') if kind == 'PART' else requested
        key = requested if requested in table else canonical
        if key not in table:
            matches = self._definition_keys[kind].get(canonical.casefold(), ())
            if len(matches) == 1:
                key = next(iter(matches))
                notes.append(f'[resolved] {kind} identifier spelling: {requested!r} -> {key!r}')
            elif len(matches) > 1:
                notes.append(f'[ambiguous] {kind} identifiers: ' + ', '.join(sorted(matches)))
                return None
        if key in table:
            records = self._definition_records[kind].get(key, [table[key]])
            if len(records) == 1:
                return records[0]
            active = [record for record in records if 'zdeprecated' not in record.cfg.source_url.casefold().split('/')]
            if len(active) == 1:
                notes.append(f'[resolved] Active {kind} definition preferred over zDeprecated archives: {key!r} -> {active[0].cfg.source_url}')
                return active[0]
            notes.append(f'[ambiguous] Duplicate {kind} {key!r}; sources: ' + ', '.join(r.cfg.source_url for r in records))
            return None
        similar = difflib.get_close_matches(canonical.casefold(), sorted(self._definition_keys[kind]), n=5, cutoff=0.55)
        names = sorted({candidate for similar_key in similar for candidate in self._definition_keys[kind][similar_key]})
        if names:
            notes.append(f'[suggestions only] Nearby {kind} identifiers (not auto-bound): ' + ', '.join(names))
        if not self.use_module_manager:
            notes.append('[configuration] No usable ModuleManager cache; patch-generated definitions may be unavailable')
        return None

    def _exact_model_url(self, normalized, notes):
        if not normalized:
            return None
        if normalized in self.models:
            return normalized
        matches = self._model_keys.get(normalized.casefold(), ())
        if not matches:
            self._scan_model_directory(posixpath.dirname(normalized))
            matches = self._model_keys.get(normalized.casefold(), ())
        if len(matches) == 1:
            resolved = next(iter(matches))
            notes.append(f'[resolved] Path spelling/index recovery: {normalized!r} -> {resolved}.mu')
            return resolved
        if len(matches) > 1:
            notes.append(f'[ambiguous] Case-insensitive path {normalized!r}: ' + ', '.join(sorted(matches)))
        return None

    def model_candidates(self, url, directory, limit=5):
        """Rank diagnostic candidates inside one mod; never auto-bind similarity."""
        normalized = self._normalize_url(url)
        local = self._normalize_url(directory) if directory else ''
        if not normalized:
            return []
        prefix = normalized.split('/')[0].casefold()
        scope = prefix if prefix in self.mod_names else (local or '').split('/')[0].casefold()
        name = posixpath.basename(normalized).casefold()
        candidates = []
        for candidate in self.models:
            if candidate.split('/')[0].casefold() != scope:
                continue
            basename = posixpath.basename(candidate).casefold()
            exact = basename == name
            nearby = posixpath.dirname(candidate).casefold() == (local or '').casefold()
            similarity = difflib.SequenceMatcher(None, name, basename).ratio()
            if exact or nearby or similarity >= 0.55:
                candidates.append(((nearby, exact, similarity), candidate))
        candidates.sort(key=lambda item: (tuple(-int(v) if isinstance(v, bool) else -v for v in item[0]), item[1]))
        return [candidate for _, candidate in candidates[:limit]]

    def _normalize_url(self, url):
        if not url:
            return None
        url = str(url).strip().strip('"\'').replace('\\', '/')
        if os.path.isabs(url) or os.path.splitdrive(url)[0]:
            absolute = os.path.abspath(url).replace('\\', '/')
            if not absolute.casefold().startswith(self.root.casefold() + '/'):
                return None
            url = absolute[len(self.root) + 1:]
        if url.split('/')[0].casefold() == 'gamedata':
            url = url.split('/', 1)[1] if '/' in url else ''
        if url.lower().endswith('.mu'):
            url = url[:-3]
        url = posixpath.normpath(url)
        if url in {'', '.', '..'} or url.startswith('../'):
            return None
        return url

    def _scan_model_directory(self, directory):
        normalized = self._normalize_url(directory) if directory else ''
        if normalized is None:
            return []
        matches = self._directory_keys.get(normalized.casefold(), ())
        if len(matches) == 1:
            normalized = next(iter(matches))
        path = os.path.join(self.root, normalized)
        if os.path.isdir(path):
            # On a miss, check just this directory, not all of GameData. This
            # picks up newly copied models while keeping normal lookups O(1).
            for entry in sorted(os.scandir(path), key=lambda e: e.name.casefold()):
                if entry.is_file() and entry.name.lower().endswith('.mu'):
                    self.process_mu(entry.path.replace('\\', '/'))
        directories = self._directory_keys.get(normalized.casefold(), ())
        return sorted({posixpath.join(d, name) for d in directories
                       for name in self.model_by_path.get(d, ())})

    def find_model_url(self, url, directory=None, allow_fallback=False, diagnostics=None):
        notes = diagnostics if diagnostics is not None else []
        normalized = self._normalize_url(url)
        local = self._normalize_url(directory) if directory else ''
        raw = str(url or '').strip().strip('"\'').replace('\\', '/')
        if normalized is None and raw.startswith(('./', '../')) and local:
            normalized = self._normalize_url(posixpath.join(local, raw))
        if url and normalized is None:
            notes.append(f"[invalid] Model path is empty or outside GameData: {url!r}")
            return None
        if normalized:
            resolved = self._exact_model_url(normalized, notes)
            if resolved:
                return resolved
            mapped = self.model_aliases.get(self.alias_key(normalized, directory))
            if isinstance(mapped, str):
                target = self._normalize_url(mapped)
                resolved = self._exact_model_url(target, [])
                source = self.models.get(resolved) if resolved else None
                if hasattr(source, 'model'):
                    from ..model.model import model_source
                    source = model_source(source.model)
                if isinstance(source, str) and os.path.isfile(source):
                    notes.append(f'[resolved] User-confirmed mapping (scoped to GameData and CFG directory): {url!r} -> {resolved}.mu')
                    return resolved
                notes.append(f'[invalid mapping] Confirmed target missing or invalid: {mapped!r}')
            if any(note.startswith('[ambiguous]') for note in notes):
                return None
            prefix = normalized.split('/')[0].casefold()
            local_mod = (local or '').split('/')[0].casefold()
            # Relative model paths and subfolders used by mods are tried
            # literally, never by fuzzy filename substitution.
            if local and prefix not in self.mod_names:
                relative = self._normalize_url(posixpath.join(local, raw))
                resolved = self._exact_model_url(relative, notes)
                if resolved:
                    notes.append(f'[resolved] Exact CFG-relative path: {url!r} -> {resolved}.mu')
                    return resolved
            relative_hint = ('/' not in raw or raw.startswith(('./', '../'))
                             or raw.split('/')[0].casefold() in {'model', 'models', 'assets', 'meshes'})
            can_use_local = local and (prefix == local_mod or (prefix not in self.mod_names and relative_hint))
            if can_use_local:
                filename = posixpath.basename(normalized)
                # Direct same-file-name relocation is allowed only within the
                # owning mod. A missing cross-mod dependency is not substituted.
                local_file = self._normalize_url(posixpath.join(local, filename))
                trailing = '/'.join(normalized.casefold().split('/')[-2:])
                same_suffix = local_file and local_file.casefold().endswith('/' + trailing)
                distinctive = filename.casefold() not in {'model', 'mesh', 'default'}
                resolved = self._exact_model_url(local_file, notes) if (allow_fallback or '/' not in raw or same_suffix or distinctive) else None
                if resolved:
                    notes.append(f'[resolved] Exact filename in owning CFG directory: {url!r} -> {resolved}.mu')
                    return resolved
                if prefix == local_mod:
                    same_names = [candidate for candidate in self._basename_keys.get(filename.casefold(), ())
                                  if candidate.split('/')[0].casefold() == local_mod
                                  and candidate.casefold().endswith('/' + '/'.join(normalized.casefold().split('/')[-2:]))]
                    if len(same_names) == 1:
                        resolved = same_names[0]
                        notes.append(f'[resolved] Same-mod exact filename/path-suffix relocation: {url!r} -> {resolved}.mu')
                        return resolved
                    if len(same_names) > 1:
                        notes.append('[ambiguous] Same-mod suffix matches: ' + ', '.join(sorted(same_names)))
                        return None
        if allow_fallback and directory is not None:
            candidates = self._scan_model_directory(directory)
            # A legacy explicit mesh can fall back only in its own CFG folder.
            requested_dir = posixpath.dirname(normalized) if normalized else directory
            if requested_dir.casefold() != (local or '').casefold():
                candidates = []
            if len(candidates) == 1:
                resolved = candidates[0]
                notes.append(f"[resolved] Unique legacy mesh in CFG directory: {url or '<default mesh>'!r} -> {resolved}.mu")
                return resolved
            if len(candidates) > 1:
                notes.append(f"[ambiguous] {directory}: multiple local models; not guessed: " + ', '.join(c + '.mu' for c in candidates))
        if normalized and not any(note.startswith('[ambiguous]') for note in notes):
            suggestions = self.model_candidates(normalized, directory)
            if suggestions:
                notes.append('[suggestions only] Same-mod candidate models, not auto-bound: ' + ', '.join(c + '.mu' for c in suggestions))
            else:
                notes.append(f'[missing] No indexed/static model for {url!r}; CFG directory: {directory}; check mod dependencies or runtime-generated geometry')
        return None

    def resolve_model(self, url, directory=None, allow_fallback=False, diagnostics=None):
        resolved = self.find_model_url(url, directory, allow_fallback, diagnostics)
        if resolved is None:
            return None
        if isinstance(self.models[resolved], str):
            self.models[resolved] = Model(self.models[resolved], resolved)
        elif hasattr(self.models[resolved], 'model'):
            from ..model.model import model_source, model_stamp
            cached = self.models[resolved].model
            source = model_source(cached)
            if cached.get('ksp_model_stamp') and cached['ksp_model_stamp'] != model_stamp(source):
                self.models[resolved] = Model(source, resolved)
        return self.models[resolved]

    def model(self, url):
        return self.resolve_model(url)

gamedata = None


def database_report(db):
    import bpy
    report = bpy.data.texts.new('KSP GameData Diagnostics')
    report.write('\n'.join([f'GameData: {db.root}',
                            f'Configuration: {"ModuleManager.ConfigCache" if db.use_module_manager else "raw CFG (patches not executed)"}',
                            f'PART: {len(db.parts)}; PROP: {len(db.props)}; INTERNAL: {len(db.internals)}; models: {len(db.models)}',
                            ''] + db.database_issues) + '\n')
    return report.name
