# Changelog

## 0.11.6 — 2026-09-29
- Resolve animation ownership to the nearest independent part/import placement anchor, with a nearest-raw-model fallback; do not redirect child model operations to an animated parent model.
- Stop source-clip discovery at independent instance boundaries, including parented models/parts and compatibility with existing 0.11.x anchors.
- Reject exact same-instance duplicate requests before displaying overlap choices; retain real target-channel conflict handling.
- Add invoke/execute regressions for simultaneous object/bone/material/light playback, rename/save/reopen, and real same-model/different-model Craft instances in both modes.

## 0.11.5 — 2026-09-29
- Reduce generated shader node clutter: remove identity operations, share UV mappings, group color/alpha and packed-normal calculations, and arrange nodes without overlaps.
- Add opt-in arrange and simplify tools for existing imported materials. Simplification preserves the original Material ID, creates a fake-user backup, and supports undo/redo.
- Preserve material-specific parameter drivers, original animation bindings and export metadata.
- Verified: generic texture shader 3 outer nodes; MK1-3 primary material 11 → 7; secondary 13 → 4. Three same-settings render comparisons match pixel-for-pixel.

## 0.11.4
- Omit collision-only MeshFilters while retaining their transform hierarchy; preserve non-collision rendererless meshes as hidden auxiliary data.
- Improve texture binding, packed images, explicit UV/DDS orientation, alpha cutout, normal maps, tint and emission preview.
- Support common craft appearance variants and MODEL texture overrides, with a material-preview button.

## 0.11.3
- Add mod-aware scoped lookup, ModuleManager cache, PROP/INTERNAL definitions and ambiguity diagnostics.
- Add index refresh and explicit user-confirmed replacement rules persisted per game library/configuration and in saved Blender files.

## 0.11.2
- Normalize model paths, resolve unique case-insensitive matches, and accept a game root as well as GameData.
- Recover broken legacy mesh references only from a unique candidate in the same CFG directory; never guess among multiple candidates. Report recovery separately.

## 0.11.1
- Retain all source Empty/Transform nodes, including unnamed leaves and transforms that originally hosted collision components. Auxiliary display is hidden by default without deleting hierarchy.

## 0.11.0
- Preserve readable source animation, mesh, skinning, bones, hierarchy and metadata. Imported animations remain detached by default and do not change scene timing.
- Add per-part clip selection, source trimming and synchronized NLA insertion, duplicate detection, explicit conflict handling, mute/remove, hold/restore and persistent bindings.
- Isolate playback across object, armature, material and light instances; realize only the selected collection instance when animation is added.
- Preserve source assets through save/reopen and export round trips; do not simulate Unity runtime scripts or create legacy collision bodies by default.

## 0.10.5 and compatibility maintenance
- Skip missing MODEL subcomponents/parts and provide precise missing-reference reports instead of aborting an entire craft.
- Blender 5.1 mesh/bone/action compatibility fixes and existing KSP animation authoring/validation tools retained.
