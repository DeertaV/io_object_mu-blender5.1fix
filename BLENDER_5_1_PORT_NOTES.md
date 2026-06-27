# Blender 5.1 port notes

This package is a Blender 5.1 compatibility refresh of the legacy
`io_object_mu` add-on.

## Target

- Latest stable target checked from Blender's official download page:
  Blender 5.1.2.
- Package compatibility floor: Blender 5.1.0.
- Local runtime used for regression in this workspace:
  `D:\Blender\blender.exe`, Blender 5.1.0.

Blender 5.1.2 is a corrective release in the same 5.1 API line, so the add-on
keeps a 5.1.0 minimum instead of needlessly rejecting 5.1.0 and 5.1.1 users.

## Compatibility fixes

- Added `utils/blender_compat.py` with shims for Blender API variants.
- Replaced removed or changed mesh/bone/action APIs:
  - custom normal setup no longer relies on `Mesh.use_auto_smooth`;
  - export normal refresh no longer directly requires `Mesh.calc_normals`;
  - edit bone scale inheritance handles Blender 5.1 `inherit_scale`;
  - action f-curve creation handles Blender 5.1 layered actions.
- Updated shader node compatibility:
  - `ShaderNodeSeparateRGB` to `ShaderNodeSeparateColor`;
  - `ShaderNodeCombineRGB` to `ShaderNodeCombineColor`;
  - old RGB socket names to Blender 5.1 color socket names.
- Added shader fallbacks for common imported shaders:
  - `Standard`;
  - `KSP/Particles/Additive`;
  - `KSP/Particles/Alpha Blended`.
- Fixed cfg/GameData import paths:
  - ModuleManager cache parsing uses `ConfigNode` objects;
  - malformed empty assignment lines like ` = =` are skipped;
  - legacy `mesh = model.mu` cfg parts choose the cfg-declared mesh.
- Updated craft import:
  - default craft import realizes part collections into editable object trees;
  - mesh, light, camera, armature, material, action, and NLA data are copied;
  - armature modifier and constraint targets are remapped to the copied objects;
  - the old lightweight collection-instance mode remains available through
    `Use Collection Instances`.
- Reduced normal import console noise while keeping true unknown path/property
  diagnostics visible.

## Tested scenarios

- Blender add-on register/unregister.
- Blender extension source and zip validation.
- Direct `.mu` import for Squad static, skinned, animated, light, and engine
  samples.
- `.craft` import with ModuleManager-backed GameData.
- Realized craft import with editable animated solar-panel objects.
- MiniDrill armature/action/NLA import.
- light_12 light object and light data animation import.
- `liquidEngine24-77/model.mu` import/export size regression.
- Default cube `.mu` export.
- QuickHull operator smoke test.
