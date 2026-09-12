#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a pinned package and run its lifecycle check in the disposable Omarchy VM."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Preserve the guest's existing synthetic profile before the lifecycle run")
    args = parser.parse_args()
    package_path = ROOT / "dist/package.json"
    receipt = json.loads(package_path.read_text())
    archive = ROOT / "dist" / receipt["archive"]
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != receipt["sha256"]:
            raise SystemExit("The package differs from its release receipt.")
    stage = ROOT / "target/vm/share/release" / receipt["sha256"]
    stage.mkdir(parents=True, exist_ok=True)
    for source in (package_path, archive, ROOT / "tests/omarchy/check-lifecycle.py"):
        shutil.copy2(source, stage / source.name)
    vm = [sys.executable, str(ROOT / "scripts/vm.py")]
    subprocess.run([*vm, "mount-share"], check=True)
    phase = "install" if args.install_only else "lifecycle"
    guest = "/mnt/hyphae/release/" + receipt["sha256"]
    output = ROOT / "target/validation/vm"
    output.mkdir(parents=True, exist_ok=True)
    command = "python3 " + shlex.quote(guest + "/check-lifecycle.py") + " --package-dir " + shlex.quote(guest)
    command += " --output " + shlex.quote("/home/memory/hyphae-qa-" + phase + ".json")
    if args.install_only:
        command += " --install-only"
    if args.fresh:
        command += " --fresh"
    with (output / f"{phase}.log").open("w") as log:
        result = subprocess.run([*vm, "ssh", command], stdout=log, stderr=subprocess.STDOUT)
    fetched = subprocess.run([*vm, "ssh", "cat " + shlex.quote("/home/memory/hyphae-qa-" + phase + ".json")], capture_output=True, text=True)
    if fetched.returncode == 0:
        report = json.loads(fetched.stdout)
        if report["package_sha256"] != receipt["sha256"]:
            raise SystemExit("The guest report belongs to another package.")
        (output / f"{phase}.json").write_text(json.dumps(report, indent=2) + "\n")
    print((output / f"{phase}.log").read_text()[-6000:])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
