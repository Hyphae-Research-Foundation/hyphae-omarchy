#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pin clean Hyphae source only after fetching the same public commit and tree."""
import argparse
import json
from pathlib import Path
import tempfile
from source_lock import ROOT, fetch_source, git, load_lock, verify_checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".upstream/hyphae")
    arguments = parser.parse_args()
    source = arguments.source.resolve(strict=True)
    lock = load_lock()
    identity = {"repository": lock["hyphae"]["repository"],
                "commit": git(source, "rev-parse", "HEAD"),
                "tree": git(source, "rev-parse", "HEAD^{tree}")}
    verify_checkout(source, identity)
    with tempfile.TemporaryDirectory(prefix="hyphae-public-source-") as temporary:
        fetch_source(Path(temporary) / "checkout", identity)
    lock["hyphae"] = identity
    pending = ROOT / "source.lock.pending"
    pending.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    pending.replace(ROOT / "source.lock.json")
    print(json.dumps({"source_commit": identity["commit"], "tree": identity["tree"], "public_fetch_verified": True}))


if __name__ == "__main__":
    main()
