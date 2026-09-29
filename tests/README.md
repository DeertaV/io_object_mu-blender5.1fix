# Blender 5.1 regression tests

These tests run in a separate factory-startup Blender process. They do not modify the running Blender session or installed add-on. Game assets and generated `.blend`, `.mu`, image or log files are not included in this repository.

The repository itself is the extension source root. Use the runner to load it under the stable `io_object_mu_blender51` package name without installation:

```powershell
& 'D:\Blender\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/run_blender_test.py -- test_preview_undo_blender.py
```

`--python-exit-code 1` is required so assertion failures give a non-zero process exit code. Run each script in a fresh process, not sequentially inside one Blender session.

## Asset-independent regressions

- `test_missing_models_blender.py`
- `test_empty_retention_blender.py`
- `test_mod_lookup_blender.py`
- `test_shader_evaluation_blender.py`
- `test_preview_undo_blender.py`
- `test_simultaneous_instances_blender.py`

## Real assets

Provide your own legally obtained KSP installation and required mods. Configure paths before starting Blender:

```powershell
$env:KSP_STOCK_GAMEDATA = 'E:\KSP\GameData'
$env:KSP_EXTRA_GAMEDATA = 'D:\KSP-with-ReStock-KRE\GameData'
$env:KSP_MOD_GAMEDATA = 'D:\KSP-with-kOS-ALCOR-FASA-ASET\GameData'
```

`KSP_STOCK_ROOT` optionally overrides the game root used by the model-lookup regression; otherwise it is the parent of `KSP_STOCK_GAMEDATA`. The historical local fixture paths remain defaults for reproducibility. Missing fixture directories are test prerequisites not satisfied, **not passing results**.

Stock assets: `test_model_lookup_blender.py`, `test_appearance_blender.py`, `test_preview_compact_blender.py`, `render_appearance_blender.py`.

ReStock / Kerbal Reusability Expansion assets: `test_imported_animation_blender.py`, `test_craft_assets_blender.py`, `test_operator_lifecycle_blender.py`, `test_data_roundtrip_blender.py`.

Additional real mod library: `test_mod_assets_blender.py` (not run successfully for 0.11.5 because its fixture library was unavailable).

Output is written to `tests/artifacts/` or test-local `.blend` files and is ignored by Git. The full manual checklist is [docs/TEST_CHECKLIST.md](../docs/TEST_CHECKLIST.md). Published validation results are [docs/TEST_REPORT_0.11.6.md](../docs/TEST_REPORT_0.11.6.md).
