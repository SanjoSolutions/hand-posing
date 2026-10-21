Created by Codex.

Hand Posing 0.1.0 fits editable Rigify palms and fingers to nearby mesh surfaces.
Calibrate each hand from the character's skin, select a target mesh, and snap
through the sidebar or F3 search. Auto Keying records the resulting controls.

Requires Blender 5.2 or newer, standard Rigify hand controls, and human-scale
geometry. Targets should be locally convex and within arm reach. Review and
refine the resulting pose as part of animation authoring.

## Install

Download `hand_posing-0.1.0.zip`. In Blender, open **Edit > Preferences > Get
Extensions**, use the menu's **Install from Disk**, select the ZIP, and enable
**Hand Posing**.

## Validation

The extension validation workflow passed on Linux with Blender 5.2.1 LTS.
The Windows workflow also passed package validation, installation, hand calibration
and snapping, Auto Keying, saved calibration, and disabling and enabling the
installed extension. See `docs/validation.md` for evidence and supported scope.

The attached SHA-256 file identifies the release archive. Source code is
licensed under GPL-3.0-or-later.
