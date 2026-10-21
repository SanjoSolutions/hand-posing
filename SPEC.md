# Hand Posing

Hand Posing is an open source Blender addon for fitting editable Rigify
hands to nearby convex mesh surfaces. Palm placement favors the authored hand
position and rotation. Finger pads follow the surface within calibrated ranges.
Existing native rig constraints guide the result. Auto Keying records the pose.

Users can calibrate either hand from a skinned mesh, select a target surface,
and snap the hand through the sidebar or operator search. Existing Snap Hand
calibrations continue to work. Saved calibrations belong to the Blender file.

The addon works independently of the game that originally supplied its solver.
The game uses the addon as its shared implementation.

The project includes a GPL-3.0-or-later license, installation and scripting
instructions, generated Blender test fixtures, automated installation checks,
and a validated extension ZIP for public addon listings.

The initial public release version is 0.1.0.

Publish Hand Posing on the official Blender Extensions directory. The public
listing includes usage instructions, supported scope, a preview, and links to
source code and support. The submitted package matches the tested release.
Record submission and review status separately from local release preparation.
Public previews use an adult female MPFB model with anatomically placed thumbs and
demonstrate the extension's supported Rigify workflow.
Preview posing uses the same native hand and finger joint constraints as the
woman's rig in `man_and_woman3.blend`.
The preview uses an MPFB skin texture and material so that fingernails and skin
detail are clearly visible.
