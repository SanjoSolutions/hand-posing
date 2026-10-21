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
and release ZIP checksum. The [preview](preview.png) shows an adult female MPFB
core model's hand posed by the extension. The model was generated with MPFB
2.0.17 and Rigify in Blender 5.2.1 LTS; Hand Posing captured its skin calibration
and snapped the right hand to the preview surface. The thumb was then refined
with the editable control from approximately 94 degrees to a relaxed 35-degree
spread. The camera frames the genuine
MPFB thumb and fingers. See [provenance](preview-provenance.json).
The preview also applies the woman's joint-limit policy from
`man_and_woman3.blend`: 30 finger constraints, two wrist constraints, and 12
adjustable wrist-bound drivers. Evaluated pose verification passed after snapping
and thumb refinement;
the maximum angular limit error was below 0.000001 radians. The reference Blender
file retained its original SHA-256 checksum. These constraints belong to the
demonstration rig; the extension continues to honor the user's existing rig setup.

The Hand Posing rename passed all 11 game fast checks, the game setup check,
and the public dependency workflow check, including the saved helper adapter.
The extraction's six focused contact checks passed:
17 base snapping tests, 12 convex snapping tests, five rectangle tests, one
refinement workflow test, 12 cache tests, and two model placement tests. The game
setup and public dependency workflow checks also passed.

Runtime verification covers Windows and Linux with Blender 5.2.1 LTS. The
[Linux CI run](https://github.com/SanjoSolutions/hand-posing/actions/runs/39630909318)
passed for release source `9d87a6c2db65bba176faecc2d672051529c49fdf`.
The Windows installation and six public workflow tests were rerun successfully
during submission preparation on October 21, 2026. Locally
convex targets, standard Rigify controls, and human-scale geometry define the
supported scope. Visual pose review remains part of animation authoring.
