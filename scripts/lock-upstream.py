#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain a clean local candidate as a verified bundle, readable patch and source lock."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".upstream/hyphae")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)

    def git(*arguments, **kwargs):
        return subprocess.check_output(["git", *arguments], cwd=source, **kwargs)

    if git("status", "--porcelain").strip():
        raise SystemExit("Commit the candidate changes before updating the source lock.")
    lock_path = ROOT / "source.lock.json"
    lock = json.loads(lock_path.read_text())
    revision = git("rev-parse", "HEAD", text=True).strip()
    base = lock["hyphae"]["base_commit"]
    paths = {name: (ROOT / lock["hyphae"][name]).resolve() for name in ("bundle", "patch")}
    if any(not path.is_relative_to(ROOT / "upstream") for path in paths.values()):
        raise SystemExit("Candidate artifacts must stay under upstream/.")
    bundle = paths["bundle"].with_suffix(".pending")
    git("bundle", "create", str(bundle), "HEAD", "^" + base)
    git("bundle", "verify", str(bundle), stderr=subprocess.PIPE)
    patch = paths["patch"].with_suffix(".pending")
    patch.write_bytes(git("diff", "--binary", "--full-index", base, revision))
    bundle.replace(paths["bundle"])
    patch.replace(paths["patch"])
    for name, path in paths.items():
        with path.open("rb") as stream:
            lock["hyphae"][name + "_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    lock["hyphae"]["candidate_commit"] = revision
    temporary = lock_path.with_suffix(".pending")
    temporary.write_text(json.dumps(lock, indent=2) + "\n")
    temporary.replace(lock_path)
    print(json.dumps({"source_commit": revision, "bundle_verified": True}))


if __name__ == "__main__":
    main()
