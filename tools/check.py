# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate, install, reopen, exercise, and disable the packaged extension."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


class BlenderSession:
    def __init__(self, blender, root):
        self.blender, self.root = blender, root
        self.environment = os.environ.copy()
        for variable, part in (("BLENDER_USER_RESOURCES", "resources"), ("BLENDER_USER_CONFIG", "config"),
                               ("BLENDER_USER_SCRIPTS", "scripts"), ("BLENDER_USER_EXTENSIONS", "extensions")):
            directory = root / part
            directory.mkdir(parents=True, exist_ok=True)
            self.environment[variable] = str(directory)
        self.environment["HAND_POSING_TEST_ROOT"] = str(root)

    def execute(self, *arguments):
        command = [self.blender, "--background", *arguments]
        process = subprocess.Popen(command, env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace",
                                   start_new_session=os.name != "nt")
        try:
            output, _ = process.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
            raise RuntimeError("Blender check exceeded its deadline:\n" + output)
        print(output, flush=True)
        if process.returncode:
            raise RuntimeError(f"Blender exited with {process.returncode}: {command}")
        return output

    def execute_script(self, source):
        script = self.root / "check_step.py"
        script.write_text(source, encoding="utf-8")
        return self.execute("--python-exit-code", "1", "--python", str(script))


def retrieve_regular_preferences():
    home = Path.home()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Blender Foundation/Blender"
    elif sys.platform == "darwin":
        root = home / "Library/Application Support/Blender"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "blender"
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob("*/config/userpref.blend")}


def inspect_review_package(archive):
    """Check the shipped sources for the registration and development-code review points."""
    with zipfile.ZipFile(archive) as package:
        files = sorted(package.namelist())
        trees = {name: ast.parse(package.read(name), filename=name)
                 for name in files if name.endswith(".py")}
    forbidden = {"retrieve_source_revision", "reload_for_development", "restore_interface", "persistent", "load_post"}
    entry_points = []
    for name, tree in trees.items():
        for node in ast.walk(tree):
            symbol = getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "name", None)
            if symbol in forbidden:
                raise RuntimeError(f"Review cleanup missing in {name}: {symbol}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"register", "unregister"}:
                entry_points.append(f"{name}:{node.name}")
            if isinstance(node, ast.Call):
                called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if called in {"register", "unregister"}:
                    raise RuntimeError(f"Unexpected add-on lifecycle call in {name}: {called}")
    if sorted(entry_points) != ["__init__.py:register", "__init__.py:unregister"]:
        raise RuntimeError(f"Unexpected add-on lifecycle entry points: {entry_points}")
    return {"files": files, "python_files": sorted(trees), "development_helpers_absent": True,
            "file_load_registration_absent": True, "lifecycle_entry_points": sorted(entry_points)}


def check(blender):
    from build import build
    project = Path(__file__).resolve().parents[1]
    before = retrieve_regular_preferences()
    try:
        with tempfile.TemporaryDirectory(prefix="hand-posing-check-") as directory:
            session = BlenderSession(blender, Path(directory))
            version = session.execute("--version").splitlines()[0]
            archive = build(session, project / "dist")
            package_review = inspect_review_package(archive)
            session.execute_script('''import os
from pathlib import Path
import bpy
root = Path(os.environ['HAND_POSING_TEST_ROOT'])
assert Path(bpy.utils.user_resource('CONFIG')).resolve() == (root / 'config').resolve()
repository = root / 'installed'
repository.mkdir()
bpy.ops.preferences.extension_repo_add(name='Hand Posing Test', type='LOCAL', use_custom_directory=True, custom_directory=str(repository))
repo = next(repo for repo in bpy.context.preferences.extensions.repos if Path(repo.directory).resolve() == repository.resolve())
(root / 'repository.txt').write_text(repo.module)
bpy.ops.wm.save_userpref()
''')
            repository = (session.root / "repository.txt").read_text()
            session.execute("--command", "extension", "install-file", "--repo", repository, "--enable", str(archive))
            session.execute_script(f'''import importlib, runpy
import bpy
name = 'bl_ext.{repository}.hand_posing'
assert name in bpy.context.preferences.addons
addon = importlib.import_module(name)
assert addon.__version__ == '0.1.1'
runpy.run_path({str(project / 'hand_posing/test_hand_posing.py')!r}, run_name='__main__')
''')
            session.execute_script(f'''import importlib
import bpy
name = 'bl_ext.{repository}.hand_posing'
addon = importlib.import_module(name)
for _cycle in range(2):
    previous = (addon.HAND_PT_snap, addon.HandCalibration, addon.HandSnap,
                addon.HandSurface, addon.retrieve_selected_rig,
                addon.rig_binding.uses_rig, addon.resting_hand_rectangle.RestingHandRectangle,
                addon.convex_hand_snap.ConvexHandSnap, addon.hand_surface_clearance.ContactSurface,
                addon.skin_finger_refinement.SkinFingerRefinement)
    # Reload Scripts schedules this routine on a UI timer, which background
    # Blender does not service while executing this test script.
    bpy.utils.load_scripts(reload_scripts=True)
    addon = importlib.import_module(name)
    current = (addon.HAND_PT_snap, addon.HandCalibration, addon.HandSnap,
               addon.HandSurface, addon.retrieve_selected_rig,
               addon.rig_binding.uses_rig, addon.resting_hand_rectangle.RestingHandRectangle,
               addon.convex_hand_snap.ConvexHandSnap, addon.hand_surface_clearance.ContactSurface,
               addon.skin_finger_refinement.SkinFingerRefinement)
    assert all(new is not old for new, old in zip(current, previous))
    assert bpy.types.Panel.bl_rna_get_subclass_py('HAND_PT_snap') is addon.HAND_PT_snap
    assert addon.HandCalibration is addon.calibration.HandCalibration
    assert addon.retrieve_selected_rig is addon.calibration.retrieve_selected_rig
    assert addon.HandSnap is addon.snap_hand.HandSnap
    assert addon.convex_hand_snap.HandSnap is addon.HandSnap
    assert addon.convex_hand_snap.RestingHandRectangle is addon.resting_hand_rectangle.RestingHandRectangle
    assert addon.skin_finger_refinement.FingerComfort is addon.snap_hand.FingerComfort
    assert addon.calibration.uses_rig is addon.rig_binding.uses_rig
    assert bpy.ops.hand.snap.get_rna_type()
    assert bpy.ops.hand.calibrate_surface.get_rna_type()
    assert hasattr(bpy.types.PoseBone, 'snap_hand_surface')
    assert hasattr(bpy.types.PoseBone, 'hand_on_surface_skin')
    assert not any(getattr(handler, '__module__', '').startswith(name)
                   for handler in bpy.app.handlers.load_post)
print('PASS: Blender Reload Scripts refreshes all modules and registrations twice')
runpy = importlib.import_module('runpy')
runpy.run_path({str(project / 'hand_posing/test_hand_posing.py')!r}, run_name='__main__')
''')
            session.execute_script(f'''import addon_utils
import bpy
name = 'bl_ext.{repository}.hand_posing'
addon_utils.disable(name, default_set=True)
assert bpy.types.Panel.bl_rna_get_subclass_py('HAND_PT_snap') is None
assert not hasattr(bpy.types.PoseBone, 'snap_hand_surface')
assert addon_utils.enable(name, default_set=True) is not None
bpy.ops.wm.save_userpref()
''')
            session.execute_script(f'''import bpy
assert 'bl_ext.{repository}.hand_posing' in bpy.context.preferences.addons
assert bpy.types.Panel.bl_rna_get_subclass_py('HAND_PT_snap')
print('PASS: installed extension persists across Blender processes')
''')
            report = {"blender": version, "archive": archive.name,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "checks": ["manifest", "archive", "runtime_files_only", "review_package_audit", "install", "calibrate", "snap", "auto_key",
                                 "saved_calibration", "registration", "reload_scripts", "workflows_after_reload",
                                 "disable_enable", "fresh_process"],
                      "review_points": {
                          "1": {"status": "passed", "evidence": "Two reload cycles refresh all seven submodules, public and dependent references; six workflows pass before and after reload"},
                          "2": {"status": "passed", "evidence": "Exact runtime-only ZIP file list; development helpers absent from all shipped Python sources"},
                          "3": {"status": "passed", "evidence": "No restore_interface or load_post registration; saved-file reopening does not call register and retains the panel, operator, calibration, and skin pointer"},
                          "4": {"status": "passed", "evidence": "Only __init__.py defines register/unregister; no runtime source calls these entry points"}},
                      "package_review": package_review,
                      "regular_preferences_preserved": True,
                      "regular_preference_versions": sorted(Path(path).parents[1].name for path in before),
                      "source_files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in sorted((project / "hand_posing").iterdir()) if path.is_file()}}
    finally:
        after = retrieve_regular_preferences()
        if after != before:
            raise RuntimeError("Regular Blender preferences changed during isolated verification")
    (project / "dist/check_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: package validation, installation, hand workflows, and regular preference preservation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default="blender")
    check(parser.parse_args().blender)
