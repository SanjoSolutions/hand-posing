# Hand Posing

Fit Rigify palms and fingers to nearby mesh surfaces.

Hand Posing fits an existing Rigify hand to a selected mesh surface. Calibrate
each hand from the character's skinned mesh, position the hand near its target,
and choose **Snap Hand**. The resulting hand and finger controls remain editable.
With Blender's Auto Keying enabled, snapping records the resulting pose.

## Features

- Calibrate the left and right hand independently from weighted skin geometry.
- Fit the palm and fingers to nearby, locally convex mesh surfaces.
- Keep the rig's native constraints and editable controls.
- Save calibration data inside the Blender file.
- Use the sidebar panel or find **Snap Hand** with F3.
- Work offline without external Python packages or services.

## Requirements

Blender 5.2 or newer and a skinned character with standard Rigify hand controls
using `.L` and `.R` names. The extension works with existing generated rigs;
it does not enable or operate the Rigify add-on. Custom rig layouts are not
supported by the included adapter.

## Quick start

1. Select a hand IK or finger control in Pose Mode.
2. Open the 3D Viewport sidebar with **N**, then **Item > Hand Posing**.
3. Choose the character's skinned mesh in **Hand skin**.
4. Click **Calibrate Hand** and confirm. Repeat for the other hand if needed.
5. Place and rotate the hand IK control near the intended contact.
6. Choose the target mesh in **Surface**, then click **Snap Hand**.
7. Review and refine the pose with the rig controls. Enable Auto Keying before
   snapping to record the result, or insert keys manually afterward.

Save the Blender file to keep calibration data. Recalibrate after changing hand
proportions or skin geometry. Calibration measures rest geometry and restores
the current pose. Existing Snap Hand calibration data is supported.

## Supported scope

Use human-scale geometry, treating Blender units as meters. Target surfaces
should be locally convex and within the arm's reach. Native joint limits can
leave visible gaps at finger joints; visual review remains part of the workflow.
Move the arm or target closer if contact is beyond the rig's reach. Dense skin
and target geometry increase solve time. Blender's Undo restores a prior pose.

The previews show an adult female MPFB model's hand after snapping to a surface.
The character is generated from MPFB's CC0 core assets. MPFB is used to create
the demonstration model; it is not required to use Hand Posing on existing rigs.

## Documentation and support

- [Installation and full documentation](https://github.com/SanjoSolutions/hand-posing#readme)
- [Source code](https://github.com/SanjoSolutions/hand-posing)
- [Report a bug](https://github.com/SanjoSolutions/hand-posing/issues)

Licensed under GNU GPL version 3 or later.
