# Validation

## Main merge verification

The merge of `blender-org-extension` into main passed the isolated package
check on October 24, 2026 with Blender 5.2.1 LTS. All 25 workflow tests passed
before and after two reload cycles, including finger groups and follow
relationships. Reload checks cover all nine runtime submodules, refreshed
dependent references, and registration of the finger-group data and both panels.
Installation, disable/enable, fresh-process startup, and preference preservation
also passed. [`validation.json`](validation.json) records this main integration
run; its package is kept separately under `dist/main/`.

The Blender Extensions submission remains the ten-file ZIP from the
`hand-posing-v0.1.1` tag on `blender-org-extension`, described below.

## Blender Extensions review revision

Verified on Windows with Blender 5.2.1 LTS on October 24, 2026, using
`python tools/check.py --blender PATH` in an isolated profile.
The base is the submitted 0.1.0 ZIP, verified byte for byte against
`hand-posing-v0.1.0`; see [publishing provenance](publishing.md).

All six public workflow tests pass before and after two consecutive reloads.
The reload check calls `bpy.utils.load_scripts(reload_scripts=True)`, the routine
Blender's Reload Scripts operator schedules on a UI timer. This lets background
Blender complete each reload before checking class and function identities,
dependency references, operators, properties, and the absence of add-on load
handlers. No browser interface or Playwright tests apply to this native addon.

| Requirement | Evidence |
| --- | --- |
| Submitted version as base | Download checksum and all ten package files match the release tag |
| Module reloading | All seven runtime submodules and the registered panel refresh twice; public and dependent references use the new definitions |
| Saved-file usability | Calibration, the skin pointer, the panel, and the Snap Hand operator survive reopening a generated file |
| Extension lifecycle | Unregister removes the panel and both properties; enable, disable, and fresh-process startup pass |
| Calibration, snapping, and Auto Keying | Six public workflow tests pass twice, including generated Rigify hands and failed-reach restoration |
| Runtime-only package | Manifest and ZIP validation pass; the ZIP contains exactly eight Python files, the manifest, and license |
| User preferences | Regular preferences retain their original hashes |

The revised `hand_posing-0.1.1.zip` has SHA-256
`5108cecf10c295688c3ce9728063d37c78e749bf51b1e49e0b971916fd8c27c6`.
The submission copy is kept in `dist/blender-org-extension/` and comes only
from the tagged `blender-org-extension` branch.
[`validation-blender-org-extension.json`](validation-blender-org-extension.json) records this run's source hashes and checks.
This verification covers the standalone addon; it does not rerun the game's
dependency checks or a hosted Linux CI job. The package has not been resubmitted.

## Earlier main validation

Finger group responsiveness was verified on October 22, 2026 with Blender 5.2.1
LTS. The isolated package check passed all 25 workflow tests, installation,
disable/enable, and fresh-process checks, preserving regular preferences.
The added regression exercises adding a second, third, and fourth member,
including the thumb, with and without calibration. It bounds native scene
updates and checks closer spacing and unchanged unrelated controls.

A separate background process loaded the existing character scene and added
the pinky to a right-hand ring-finger group. Profiling measured 68.65 seconds
and 1,644 native scene updates before the fix, versus 0.82 seconds and six
updates afterward. Tip spacing decreased from 45.1 mm to 22.0 mm and unrelated
controls remained unchanged. Timing depends on the scene and machine. Trial
poses now use a local hand snapshot; the accepted pose is checked against
evaluated rig constraints and skin clearance. The original scene was not saved.

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
| Finger groups | Add, edit, remove, and transfer exclusive membership; independent groups for both hands |
| Immediate grouping | Membership edits move fingers without Snap Hand, calibration, or a surface; wrist and unrelated controls stay fixed; Auto Keying records only affected fingers |
| Grouped contact | Measured closer spacing on flat and curved targets, including thumbs and generated Rigify hands; surface clearance and joint bounds |
| Saved groups | Save/reopen and disable/enable preserve group names and members |
| Follow relationships | Create, edit, remove, and chain bone pairs; evaluated base, midpoint, tip, and intermediate offsets; live offset changes and animated targets |
| Follow safety and persistence | Self-following, duplicate sources, and cycles are rejected; cross-armature transforms, bone renaming, deleted-target repair, save/reopen, disable/enable, and Undo/Redo |
| Rig state preservation | Calibration preserves control transforms and pose mode; failed reach restores controls and IK blend |
| Blender addon lifecycle | Repeated registration, disable, enable, and fresh-process checks |
| Public distribution | Blender manifest and archive validation, GPL license, and release checksum |
| Game dependency | Shared class identity, pinned source checksums, game setup, and contact regression checks |

The public workflow tests live in
[`test_hand_posing.py`](../hand_posing/test_hand_posing.py).

Follow relationships passed the full isolated package check on October 21, 2026,
with Blender 5.2.1 LTS: 24 workflow tests plus ZIP validation, installation, and
fresh-process checks. These include ten follow tests covering Undo/Redo.
Existing hand calibration, snapping, and grouping tests passed.
`tools/create_follow_preview.py` captures the native sidebar and edit dialog in
a separate Blender process and saves an editable example scene under
`.cache/follow-relationships/`. Its base, midpoint, and tip guides are checked
against evaluated bone directions before capture. The current local package
and installation report are in `dist/`.

[`validation.json`](validation.json) records the tested package source hashes
and release ZIP checksum. The [preview](preview.png) shows an adult female MPFB
core model's hand posed by the extension. The model was generated with MPFB
2.0.17 and Rigify in Blender 5.2.1 LTS; Hand Posing captured its skin calibration
and snapped the right hand to the preview surface. The thumb was then refined
with the editable control from approximately 94 degrees to a relaxed 35-degree
spread. The camera frames the genuine
MPFB thumb and fingers. See [provenance](preview-provenance.json).
The gallery preview points left; the icon and featured image retain their upright
orientation.
The model retains its UV coordinates and uses MPFB's MakeSkin material with the
MakeHuman female diffuse texture and MPFB's fingernail roughness mask.
The preview also applies the woman's joint-limit policy from
`man_and_woman3.blend`: 30 finger constraints, two wrist constraints, and 12
adjustable wrist-bound drivers. Evaluated pose verification passed after snapping
and thumb refinement;
the maximum angular limit error was below 0.000001 radians. The reference Blender
file retained its original SHA-256 checksum. These constraints belong to the
demonstration rig; the extension continues to honor the user's existing rig setup.

`tools/create_group_preview.py` renders an immediate-grouping/independent comparison without snapping again and saves
its editable Blender scene in `.cache/finger-groups/`.

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
