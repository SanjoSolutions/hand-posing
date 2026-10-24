# Validation

## Blender Extensions review

Verified on Windows with Blender 5.2.1 LTS on October 24, 2026:

```sh
python tools/check.py --blender /path/to/blender
```

All four points in the [review](https://extensions.blender.org/approval-queue/hand-posing/#activity-23878)
are addressed. The check installs the built ZIP into a temporary extension
repository and verifies the installed code, rather than importing the checkout.

| Review point | Result | Evidence |
| --- | --- | --- |
| 1. Reload modules correctly | Passed | The package uses Blender's documented reload pattern. Two reload cycles replace definitions in all seven submodules, refresh public and dependent references, and retain the registered panel, operators, and properties. All six workflow tests pass before and after reload. |
| 2. Exclude development code and tests | Passed | The ZIP contains exactly eight runtime Python files, the manifest, and license. Its Python syntax trees contain none of `retrieve_source_revision`, `reload_for_development`, or `restore_interface`. Tests, build tools, previews, and documentation are outside the package. |
| 3. Remove `restore_interface` and repeated registration | Passed | No shipped source installs a `load_post` handler or uses `persistent`. Reopening a saved Blender file does not call `register()`, while calibration, the skin pointer, panel, and Snap Hand operator remain available. |
| 4. Remove registration from `snap_hand.py` | Passed | An audit of every shipped Python file finds only `__init__.py:register` and `__init__.py:unregister`, with no calls to these entry points inside the package. Disable/enable and fresh-process startup pass. |

The background reload check calls `bpy.utils.load_scripts(reload_scripts=True)`,
the same routine the Reload Scripts operator schedules on a UI timer. It checks
the reload behavior directly; it does not drive the menu through the UI.
The six workflows cover both hands, a generated Rigify rig, surface fitting,
Auto Keying, saved calibration, registration cleanup, and failed-reach rollback.
Regular Blender preferences retain their original hashes.

The revision is based on `3b77e11`, whose add-on files match the submitted
0.1.0 sources. Runtime sources are unchanged by the squash and this verification.
The rebuilt `hand_posing-0.1.1.zip` has SHA-256
`7d97fa34df99a65b94bfb08bbcbddc8d921a3f7c5403b1376783269c03b909ce`.
The current copy, checksum, and check results are in `dist/`; a submission copy
is kept in `dist/blender-org-extension/`. The submission source is identified by
the `hand-posing-v0.1.1` tag on `blender-org-extension`.
The package has not been resubmitted.

[`validation.json`](validation.json) records each review point's result, the ZIP
file list, the registration entry points, the archive checksum, and source hashes.
Its `source_files` includes the repository test file for reproducibility;
`package_review.files` lists only the files distributed in the ZIP.
This run covers Windows; it does not rerun the game's dependency checks or Linux CI.

## Earlier release validation

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
The [preview](preview.png) shows an adult female MPFB
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
