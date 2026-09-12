#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run pinned, real host CLIs with a private profile in the QA container."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--image", default="localhost/hyphae-omarchy-qa:quattro-20260911")
    parser.add_argument("--node-dir", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    node = args.node_dir or Path(shutil.which("node") or "missing-node").resolve(strict=True).parent.parent
    output = ROOT / "target/validation/hosts"
    with binary.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    runtime = output / "runtime" / digest
    runtime.mkdir(parents=True, exist_ok=True)
    destination = runtime / "hyphae"
    if not destination.exists():
        shutil.copy2(binary, destination)
    with destination.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise SystemExit("The immutable QA runtime differs from the selected binary.")
    if not (ROOT / "tests/hosts/node_modules/.bin/codex").exists():
        raise SystemExit("Install the exact tests/hosts/package-lock.json dependencies first.")
    command = ["podman", "run", "--rm", "--network=none", "--security-opt", "label=disable", "--userns=keep-id",
        "-v", f"{node}:/node:ro", "-e", "PATH=/node/bin:/usr/local/sbin:/usr/local/bin:/usr/bin",
        "-v", f"{ROOT / 'tests/hosts'}:/hosts:ro", "-v", f"{runtime}:/runtime:ro",
        "-v", f"{output}:/artifacts", args.image, "python3", "/hosts/check-cli.py"]
    receipt = output / "hosts.json"
    if receipt.exists():
        receipt.unlink()
    with (output / "hosts.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    metadata = {"schema": "hyphae-host-run-v1", "status": "passed" if result.returncode == 0 else "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(), "binary_sha256": digest,
        "image": subprocess.check_output(["podman", "image", "inspect", "--format", "{{.Id}}", args.image], text=True).strip(),
        "network": "none", "exit_code": result.returncode}
    (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print((output / "hosts.log").read_text()[-6000:])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
