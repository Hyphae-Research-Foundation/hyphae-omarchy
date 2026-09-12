#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct the exact unpublished candidate from its public base and local bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=ROOT/".upstream/hyphae")
    args=parser.parse_args()
    destination=args.out.resolve()
    lock=json.loads((ROOT/"source.lock.json").read_text())["hyphae"]
    bundle=ROOT/lock["bundle"]
    with bundle.open("rb") as source:
        if hashlib.file_digest(source,"sha256").hexdigest()!=lock["bundle_sha256"]:
            raise SystemExit("The candidate bundle differs from its source lock.")
    if destination.exists():
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=destination,text=True).strip()
        dirty=subprocess.check_output(["git","status","--porcelain"],cwd=destination,text=True)
        if head!=lock["candidate_commit"] or dirty:raise SystemExit("The existing checkout differs; it has been preserved.")
        print(destination);return
    destination.mkdir(parents=True)
    def git(*arguments):subprocess.run(["git",*arguments],cwd=destination,check=True)
    git("init","--quiet")
    git("remote","add","origin",lock["repository"])
    git("fetch","--depth=1","origin",lock["base_commit"])
    git("bundle","verify",str(bundle))
    git("fetch",str(bundle),"HEAD")
    git("checkout","--detach",lock["candidate_commit"])
    print(destination)


if __name__=="__main__":main()
