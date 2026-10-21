# Contributing

Use Blender 5.2 and Python 3.11 or later. Keep geometry fitting in the solver
modules, calibration in `calibration.py`, and Blender registration and UI in
`__init__.py`. Keep imports relative to the extension package.

Add tests beside the behavior they exercise. Exercise public APIs with generated
fixtures and measure evaluated geometry. Run `python tools/check.py --blender
PATH` before submitting a change. Include the Blender version and a reproducible
scene or fixture for geometry reports. Share assets with redistribution rights.

Contributions use the project's GPL-3.0-or-later license.
