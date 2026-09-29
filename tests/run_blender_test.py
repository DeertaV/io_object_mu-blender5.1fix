"""Run a regression from this repository without installing the add-on.

blender --background --factory-startup --python-exit-code 1 \
    --python tests/run_blender_test.py -- test_preview_undo_blender.py
"""
import importlib.util
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if not args:
    raise ValueError('Supply a regression script name after --')
test = (root / 'tests' / args[0]).resolve()
if test.parent != (root / 'tests').resolve() or not test.is_file():
    raise ValueError('Regression script must be a file in tests/')
(root / 'tests' / 'artifacts').mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location(
    'io_object_mu_blender51', root / '__init__.py',
    submodule_search_locations=[str(root)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
sys.argv = [str(test)] + (['--'] + args[1:] if len(args) > 1 else [])
runpy.run_path(str(test), run_name='__main__')
