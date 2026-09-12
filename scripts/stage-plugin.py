#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage the git-visible plugin source, excluding local build/runtime artifacts."""
import argparse
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, default=root / "target/plugin-stage")
args = parser.parse_args()
destination = args.out.resolve()
if not destination.is_relative_to(root / "target"):
    raise SystemExit("staging must stay under the project's target directory")
if destination.exists():
    shutil.rmtree(destination)
destination.mkdir(parents=True)
listed = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
for item in sorted(set(listed.split(b"\0"))):
    if not item:
        continue
    relative = Path(item.decode())
    source = root / relative
    if source.is_symlink() or not source.is_file():
        raise SystemExit("only regular source files may enter a plugin archive")
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
print(destination)
