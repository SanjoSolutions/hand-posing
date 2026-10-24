Created by Codex.

Hand Posing 0.1.1 addresses the Blender Extensions review of the initial release.

- Support Blender's Reload Scripts command by refreshing all runtime modules
  and their imported references.
- Remove development helpers from the add-on. Tests and development tools remain
  in the source repository and are excluded from the extension ZIP.
- Remove the file-load registration handler. Saved calibration and the interface
  remain available when opening Blender files.
- Keep add-on registration in `__init__.py` and remove the forwarding entry point
  from `snap_hand.py`.

Validated on Windows with Blender 5.2.1 LTS. All six workflow tests passed before
and after two reload cycles. Package validation, installation, saved-file
reopening, disable/enable, and fresh-process startup passed. The built ZIP
contains only runtime sources, the manifest, and license.
