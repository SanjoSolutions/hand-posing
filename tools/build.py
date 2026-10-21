# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and validate a Blender extension ZIP in an isolated profile."""

import argparse
import hashlib
from pathlib import Path
import tempfile

from check import BlenderSession


def build(session, output):
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "hand_posing"
    session.execute("--command", "extension", "validate", str(source))
    session.execute("--command", "extension", "build", "--source-dir", str(source), "--output-dir", str(output))
    import tomllib
    manifest = tomllib.loads((source / "blender_manifest.toml").read_text())
    archive = output / f"{manifest['id']}-{manifest['version']}.zip"
    session.execute("--command", "extension", "validate", str(archive))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hand-posing-build-") as directory:
        session = BlenderSession(arguments.blender, Path(directory))
        archive = build(session, arguments.output.resolve())
    print(archive)
