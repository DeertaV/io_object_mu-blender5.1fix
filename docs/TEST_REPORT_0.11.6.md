# 0.11.6 — simultaneous animation ownership regression report

Date: 2026-09-29. Runtime: Windows / Blender 5.1.0.

## Confirmed failure and fix

A new regression failed against 0.11.5: selecting an independently imported model B, parented beneath imported model A, resolved animation ownership to A rather than B (`Selecting B must not resolve to A`). The old search kept overwriting the candidate while walking upwards. Clip discovery also traversed separately owned child parts/models.

The fix uses the nearest independent part/placement anchor (recognizing existing 0.11.x anchor metadata) and a nearest-raw-model fallback. Source-clip enumeration stops at independent instance boundaries. Same-instance duplicate detection now runs before the overlap dialog and names the owning part; actual same-target Action/NLA conflicts remain protected.

This demonstrates one concrete cause of cross-part false duplicate/conflict messages. It is not a claim that every possible manual hierarchy or shared-ID configuration has been visually reproduced in the user's running GUI.

## Verification

**13 public regression suites passed from the publication checkout**, using one factory-startup Blender process per suite and `--python-exit-code 1`:

- test_missing_models_blender
- test_imported_animation_blender
- test_craft_assets_blender
- test_operator_lifecycle_blender
- test_empty_retention_blender
- test_model_lookup_blender
- test_mod_lookup_blender
- test_data_roundtrip_blender
- test_appearance_blender
- test_shader_evaluation_blender
- test_preview_compact_blender
- test_preview_undo_blender
- test_simultaneous_instances_blender (new)

The new asset-independent regression covers the actual panel invoke/execute methods, existing placement-anchor metadata, nested raw models and Craft roots, selecting a child/rig/helper/light, identical clip UIDs and frame intervals, simultaneous object/bone/material/light evaluation, independent mute/remove, duplicate rejection without a dialog, real overlap rejection, Chinese renaming and save/reopen. Scene frame/range/FPS are preserved by animation addition.

The existing actual ReStock Craft test now schedules two instances of the same drill clip and a different solar part at frame 200, in both expanded and collection-instance modes. Targets are distinct, no unrelated overrides are created, and removing the first part leaves the other two scheduled.

An additional private saved-scene regression was performed without saving or modifying the user's original file: retain one already scheduled ladder, then add six other part instances (parachute, three landing legs, antenna, engine) at frame 200. All six add successfully with disjoint targets, no override records, and the original playback remains present and unmuted. User scenes and their raw logs are not uploaded.

## Remaining validation boundaries

- The unavailable real mod-library fixture from 0.11.5 is still unavailable; actual kOS/ALCOR/FASA/ASET coverage is not claimed. Synthetic mod lookup and available Stock/ReStock/KRE regressions passed.
- Native running-GUI click acceptance and every manually shared data-ID/hierarchy combination have not been tested. Genuine shared targets still require conflict handling.
- Unity runtime scripts/particles and unsupported source channels remain outside the conversion scope, as documented in the existing guides.

## Package

Official Blender extension build/validate and Python source compilation passed. ZIP CRC and all 177 packaged files match the final core source byte-for-byte. No game assets, user settings/backups/scenes or raw local logs are included.

- [Install 0.11.6 ZIP](../io_object_mu_blender51-0.11.6.zip)
- SHA256: `B69DF5DBCF5F7AFEF9DA2C63E38C386B998E8027B372746650AC85E4A601CF96`
- [Checksum file](../io_object_mu_blender51-0.11.6.zip.sha256)
- [Feature explanation](../ANIMATION_ISOLATION_0.11.6.md)
- [Test runner instructions](../tests/README.md)

The running installed plug-in is not hot-replaced; save/exit before installing the new ZIP. Existing source assets and scheduled animation records are not automatically deleted or re-imported.
