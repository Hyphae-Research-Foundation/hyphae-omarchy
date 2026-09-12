#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the exact public Hyphae commit and verify its tree before use."""
import argparse
from pathlib import Path
from source_lock import ROOT, fetch_source, load_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".upstream/hyphae")
    arguments = parser.parse_args()
    destination = arguments.out.resolve()
    fetch_source(destination, load_lock()["hyphae"])
    print(destination)


if __name__ == "__main__":
    main()
