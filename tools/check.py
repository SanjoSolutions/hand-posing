# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate, install, reopen, exercise, and disable the packaged extension."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


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


def check(blender):
    from build import build
    project = Path(__file__).resolve().parents[1]
    before = retrieve_regular_preferences()
    try:
        with tempfile.TemporaryDirectory(prefix="hand-posing-check-") as directory:
            session = BlenderSession(blender, Path(directory))
            version = session.execute("--version").splitlines()[0]
            archive = build(session, project / "dist")
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
assert addon.__version__ == '0.1.0'
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
                      "checks": ["manifest", "archive", "install", "calibrate", "snap", "auto_key",
                                 "saved_calibration", "registration", "disable_enable", "fresh_process"],
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
