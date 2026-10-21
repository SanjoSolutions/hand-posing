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
| Finger groups | Add, edit, remove, and transfer exclusive membership; independent groups for both hands |
| Grouped contact | Measured closer spacing on flat and curved targets, including thumbs and generated Rigify hands; surface clearance and joint bounds |
| Saved groups | Save/reopen and disable/enable preserve group names and members |
| Rig state preservation | Calibration preserves control transforms and pose mode; failed reach restores controls and IK blend |
| Blender addon lifecycle | Repeated registration, disable, enable, and fresh-process checks |
| Public distribution | Blender manifest and archive validation, GPL license, and release checksum |
| Game dependency | Shared class identity, pinned source checksums, game setup, and contact regression checks |

The eleven public workflow tests live in
[`test_hand_posing.py`](../hand_posing/test_hand_posing.py).
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
`tools/create_group_preview.py` renders a grouped/independent comparison and saves
its editable Blender scene in `.cache/finger-groups/`.
