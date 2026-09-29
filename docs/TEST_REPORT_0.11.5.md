# 0.11.5 validation report

Date: 2026-09-29. Runtime: Windows, Blender 5.1.0. This report distinguishes successful regression coverage from untested combinations.

## Scope

The repository was previously at 0.9.4. The published snapshot contains the accumulated 0.10.5–0.11.5 implementation: missing-model recovery/reporting, mod-aware lookup, full readable source data and hierarchy retention, detached animation assets and per-instance scheduling, collision-only mesh omission, improved texture/material preview, and compact shader graphs. See [CHANGELOG](../CHANGELOG.md) and feature guides in the repository root.

## Verified before publication

12 regression suites passed in the implementation workspace and were rerun successfully from the publication checkout using tests/run_blender_test.py:

1. test_missing_models_blender
2. test_imported_animation_blender
3. test_craft_assets_blender
4. test_operator_lifecycle_blender
5. test_empty_retention_blender
6. test_model_lookup_blender
7. test_mod_lookup_blender
8. test_data_roundtrip_blender
9. test_appearance_blender
10. test_shader_evaluation_blender
11. test_preview_compact_blender
12. test_preview_undo_blender

- Default imports preserve scene frame/range/FPS and keep source animation assets detached.
- Existing coverage includes persistent bindings, isolated object/bone/material/light animation, source trimming, NLA conflicts, remove/mute, collection realization, save/reopen, undo and round-trip data.
- Stock craft: 33 instances, zero skipped, both instance modes.
- Six actual ReStock/KRE models, including 20-bone and 49-bone meshes: import, deformation evaluation and multi-material/source-animation export round trips passed.
- Minimal texture shader: 3 outer nodes. Actual MK1-3 primary material: 11 → 7; secondary: 13 → 4. See [reference counts](validation-0.11.5/compact-preview-reference-counts.json) and [new counts](validation-0.11.5/compact-preview-counts.json).
- Same-settings 512×512 Cycles CPU renders of the nose cone, solid booster and Mk16 parachute: every RGBA pixel exactly matches the 0.11.4 reference. See [comparison metrics](validation-0.11.5/compact-render-comparison.json).
- Simplification preserves Material IDs and source Action bindings, retains handmade nodes in a fake-user backup, survives save/reopen, and supports undo/redo. Injected construction failure leaves the original graph and material count unchanged.
- Shared groups have no Material-specific drivers inside; drivers remain on each Material instance. UV sharing splits when one texture mapping changes; later non-identity mappings retain a valid UV input.
- Independent MK1-3 example save/reopen smoke check passed: 7-node active material, packed textures, per-material parameter bindings and no active playback Action. The example contains game assets and is not included in the public repository.

## Not completed / not claimed

- `test_mod_assets_blender.py`: the real mod-library fixture directory was unavailable (the original K: drive was not mounted). Actual kOS/ALCOR/FASA/ASET assets were **not retested for 0.11.5**. Synthetic mod lookup tests passed, but do not replace real-asset coverage.
- Running native GUI button-by-button visual acceptance, every third-party mod combination, and game-engine export execution were not performed.
- Unity scripts, particle runtime and missing source data are not simulated. Unsupported readable non-collision components remain metadata and are reported.

The [manual checklist](TEST_CHECKLIST.md) lists further coverage and does not assert that every item has passed.

## Publication and package checks

- Source/test Python compilation passed.
- Blender official extension build and validate passed; tests/docs/cache/ZIP files are excluded from extension packaging.
- ZIP CRC and all 176 package-file comparisons against the final core add-on source passed.
- Download: [0.11.5 installation ZIP](../io_object_mu_blender51-0.11.5.zip).
- SHA256: `7F8DE58A286FB3B6E21F70EA189C3D120C8FE2DA51993160E059E65D45408D84`; [checksum file](../io_object_mu_blender51-0.11.5.zip.sha256).
- Original repository history, upstream attribution and GPL-2.0-or-later licensing retained.
- No credentials, local preference files, backups, user scenes, game `.mu`/texture assets, generated images or raw local logs are published.

For reproduction, see [tests/README](../tests/README.md). Each test runs in a new factory-startup process; assertions use Blender's `--python-exit-code 1`.
