# Publishing

## Release package

Run `python tools/check.py --blender PATH`, then `python tools/build.py --blender
PATH`. Publish the generated extension ZIP and checksum from `dist/` with a source
tag matching `hand_posing/blender_manifest.toml` (the initial Hand Posing
release uses `hand-posing-v0.1.0`). Review the validation report
in `docs/validation.md` and update it for the selected source revision.

The release includes Python source, the extension manifest, and the GPL license.
The source checkout also includes documentation and generated fixture tests.
The public source repository is https://github.com/SanjoSolutions/hand-posing.
Use https://github.com/SanjoSolutions/hand-posing/issues as the support URL.
The complete description for the official Extensions listing is in
[`extension-listing.md`](extension-listing.md).

The public [0.1.0 release](https://github.com/SanjoSolutions/hand-posing/releases/tag/hand-posing-v0.1.0)
includes the tested ZIP and SHA-256 checksum. Its tag points to tested source
`9d87a6c2db65bba176faecc2d672051529c49fdf`.

## Listing draft

**Name:** Hand Posing

**Summary:** Fit Rigify palms and fingers to nearby mesh surfaces.

**Category:** Rigging / Animation

**Blender:** 5.2 or later

**License:** GNU GPL version 3 or later

**Description:** Select a Rigify hand, calibrate it from the character's skin,
choose a surface, and snap. Hand Posing places the palm and fingers while
keeping the rig controls editable. Auto Keying records the resulting pose.
Existing Snap Hand calibrations work directly.

**Supported scope:** Standard Rigify hand controls, human-scale geometry, and
nearby locally convex targets. The addon uses Blender's evaluated skin and native
rig constraints. Rig and skin setup plus visual pose review belong to the workflow.

**Installation:** Preferences > Get Extensions > Install from Disk. Select the
release ZIP and enable Hand Posing.

## Blender Extensions

Submit the ZIP at the official Blender Extensions platform and provide the public
source link, installation steps, and `docs/preview.png`. The previews use an adult
female MPFB core model with a generated Rigify rig. Reproduce them in an isolated
background Blender profile with `tools/create_preview.py -- --mpfb-dir PATH`,
where PATH points to an installed MPFB extension. Reuse the generated model with
`--source-blend .cache/mpfb-preview-source.blend`. The model stays in `.cache/`;
only the hand renders are published. MPFB is a preview-authoring dependency.
Use `--constraints docs/preview-constraints.json` for the anatomical limit policy
exported from the woman's rig in `man_and_woman3.blend`. The preview installs 30
finger limits and two wrist limits in native custom spaces, preserving anatomical
extension/flexion when fitting the frames to the new model. Wrist properties drive
all 12 wrist bounds. The preview verifies evaluated joint rotations against the
limits after snapping. Add `--skip-render` to repeat that verification quickly.
Review the current [addon guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/)
and [terms](https://extensions.blender.org/terms-of-service/) for the submission.
The manifest declares GPL-3.0-or-later and requires Blender 5.2.

Sign in with Blender ID at https://extensions.blender.org/submit/. Upload the
release ZIP, add the listing description and preview, set the source and support
links, and submit for moderation. Publication requires the platform's approval.

## Other addon marketplaces

Use the same source license, tested Blender version, ZIP, installation steps, and
scope description. Supply listing images and seller metadata in that marketplace's
current submission form. Each platform owns its listing review and approval.

The local release preparation creates the package and listing draft. Repository
publication, marketplace submission, and platform approval have
their own delivery state.
