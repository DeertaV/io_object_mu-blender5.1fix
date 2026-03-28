# io_object_mu for Blender 5.1

This branch is a compatibility-maintenance port of the legacy `io_object_mu` Blender addon, updated to work with **Blender 5.1**.

The original project was no longer directly usable on recent Blender versions due to multiple API changes introduced across newer Blender releases. This branch focuses on restoring usability while keeping the original addon structure and workflow as intact as possible.

## What has been updated
- Fixed addon module loading and registration issues in Blender 5.1
- Updated deprecated Blender Python API usage
- Added compatibility handling for newer node-tree and shader APIs
- Improved tolerance for legacy shader/node properties that no longer exist in recent Blender versions
- Restored `.mu` import functionality for Blender 5.1
