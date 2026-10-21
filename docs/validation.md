# Validation

Verified on Windows with Blender 5.2.1 LTS on October 21, 2026.

`python tools/check.py --blender PATH` passed from the standalone checkout. It
validated the manifest and ZIP, installed the ZIP into a temporary extension
repository, opened fresh Blender processes, exercised the public workflows,
disabled and enabled the addon, and verified persisted installation. The regular
Blender preferences retained their original hashes.

| Requirement | Evidence |
| --- | --- |
| Calibration for both hands | Generated skin fixtures and a freshly generated Rigify human rig |
| Editable surface placement | Snap operator checks and evaluated palm and finger skin clearance |
| Auto Keying | Authored hand and finger animation channels |
| Saved calibration | Save and reopen a generated Blender file |
| Rig state preservation | Calibration preserves control transforms and pose mode; failed reach restores controls and IK blend |
| Blender addon lifecycle | Repeated registration, disable, enable, and fresh-process checks |
| Public distribution | Blender manifest and archive validation, GPL license, and release checksum |
| Game dependency | Shared class identity, pinned source checksums, game setup, and contact regression checks |

The six public workflow tests live in
[`test_hand_posing.py`](../hand_posing/test_hand_posing.py).
[`validation.json`](validation.json) records the tested package source hashes
and release ZIP checksum. The [preview](preview.png) uses generated test geometry.

The Hand Posing rename passed all 11 game fast checks, the game setup check,
and the public dependency workflow check, including the saved helper adapter.
The extraction's six focused contact checks passed:
17 base snapping tests, 12 convex snapping tests, five rectangle tests, one
refinement workflow test, 12 cache tests, and two model placement tests. The game
setup and public dependency workflow checks also passed.

Runtime verification covers Windows. The source includes a Linux CI workflow;
its hosted execution belongs to the public repository's first CI run. Locally
convex targets, standard Rigify controls, and human-scale geometry define the
supported scope. Visual pose review remains part of animation authoring.
