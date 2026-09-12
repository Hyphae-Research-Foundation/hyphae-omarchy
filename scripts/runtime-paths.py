#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Print a built release binary path only when it matches the runtime lock."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", choices=["hyphae", "hyphae-embed"])
    arguments = parser.parse_args()
    lock = json.loads((ROOT / "runtime.lock.json").read_text())
    expected = lock["files"]["bin/" + arguments.binary]
    path = (ROOT / "target/runtime-cli" / expected["sha256"] / "hyphae"
            if arguments.binary == "hyphae"
            else ROOT / "target/embed/x86_64-unknown-linux-gnu/release/hyphae-embed")
    if not path.is_file() or path.is_symlink():
        raise SystemExit("Build the pinned runtime before running release checks.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if path.stat().st_size != expected["bytes"] or digest != expected["sha256"]:
        raise SystemExit("The release binary differs from runtime.lock.json.")
    print(path)


if __name__ == "__main__":
    main()
