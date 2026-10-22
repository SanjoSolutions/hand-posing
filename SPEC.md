# Hand Posing

Hand Posing is an open source Blender addon for fitting editable Rigify
hands to nearby convex mesh surfaces. Palm placement favors the authored hand
position and rotation. Finger pads follow the surface within calibrated ranges.
Existing native rig constraints guide the result. Auto Keying records the pose.

Users can calibrate either hand from a skinned mesh, select a target surface,
and snap the hand through the sidebar or operator search. Existing Snap Hand
calibrations continue to work. Saved calibrations belong to the Blender file.

Users can create, edit, and remove any number of finger groups for each hand,
including no groups. Each finger, including the thumb, belongs to at most one
group. Changing group members immediately brings those fingers close together,
without pressing Snap Hand or requiring a surface or skin calibration. The wrist
and unrelated fingers keep their pose. Grouping respects joint constraints and
any selected surface, and Auto Keying records the changed controls. Groups also
apply when snapping and belong to the Blender file. Ungrouped fingers keep their
independent fitting behavior.
Adding or removing group members keeps Blender responsive, including in scenes
with complete characters and skinned meshes.

Users can create, edit, and remove follow relationships between bones, including
bones on different armatures. In each relationship, bone A keeps pointing at
bone B as the pose changes. An offset from 0 to 1 selects the point along B:
0 is its base, 0.5 is halfway, and 1 is its tip. Each bone can follow one target.
Self-following and circular relationships are rejected. Relationships belong to
the Blender file and work without hand calibration or a surface.

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
The gallery preview shows the fingers pointing left. The icon and featured image
keep their upright orientation.
