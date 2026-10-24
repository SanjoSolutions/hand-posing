# Publishing

## Publication status

As of October 21, 2026, the GitHub 0.1.0 release is public. The official Blender
Extensions listing exists as a draft at
https://extensions.blender.org/add-ons/hand-posing/draft/ and has not been
submitted for moderation. The textured adult female MPFB previews have been
uploaded and saved in the draft. The gallery preview points left; the icon and
featured image remain upright. Submission waits for the user's review.

## Blender Extensions review

The `blender-org-extension` branch starts from `hand-posing-v0.1.0`
(`9d87a6c2db65bba176faecc2d672051529c49fdf`). Every file in the submitted ZIP
matches that tag byte for byte. The downloaded ZIP's SHA-256 is
`9fd15d4c2ef6e52d0ffc0a947e80cfe7ad8aa82a95a2c1af85a6d860ff0ad323`.

The [October 24, 2026 review](https://extensions.blender.org/approval-queue/hand-posing/#activity-23878)
requests standard script reloading, removal of development helpers, removal of
the file-load registration handler, and a single registration entry point.
The revised package addresses these requests. Tests remain in the repository;
the submitted ZIP already excluded them, and the build now verifies the exact
runtime file list. The version remains 0.1.0. This local revision has not been
uploaded to the review queue.
