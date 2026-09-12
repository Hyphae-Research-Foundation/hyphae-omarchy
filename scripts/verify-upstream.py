#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the candidate's required native/SDK checks and retain complete logs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from source_lock import load_lock, verify_checkout

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=ROOT/".upstream/hyphae")
    parser.add_argument("--only",nargs="*")
    args=parser.parse_args()
    source=args.source.resolve(strict=True)
    verify_checkout(source, load_lock()["hyphae"])
    output=ROOT/"target/validation/upstream"
    output.mkdir(parents=True,exist_ok=True)
    environment=os.environ.copy()
    environment["PYTHONPATH"]=str(source/"sdks/python/src")
    environment["HYPHAE_TARGET_DIR"]=str(ROOT/"target/native")
    environment["RUSTDOCFLAGS"]="-D warnings"
    cargo=["--workspace","--all-features","--locked","--target-dir",str(ROOT/"target/native"),"--jobs","4"]
    checks=[
        ("fmt",source,["cargo","fmt","--all","--check"]),
        ("clippy",source,["cargo","clippy",*cargo,"--all-targets","--config","profile.dev.debug=0","--","-D","warnings"]),
        ("rust",source,["cargo","test",*cargo,"--no-fail-fast","--config","profile.test.debug=0"]),
        ("rustdoc",source,["cargo","doc",*cargo,"--no-deps","--config","profile.dev.debug=0"]),
        ("embed-fmt",source,["cargo","fmt","--manifest-path","embed/Cargo.toml","--check"]),
        ("embed",source,["cargo","test","--manifest-path","embed/Cargo.toml","--locked","--target-dir",str(ROOT/"target/embed"),"--config","profile.test.debug=0","--jobs","4"]),
        ("sdk-models",source,["python3","tools/generate_sdk_models.py","--check"]),
        ("python",source,["python3","-m","unittest","discover","-s","sdks/python/tests"]),
        ("typescript-install",source/"sdks/typescript",["npm","ci","--ignore-scripts","--no-audit","--no-fund","--cache",str(ROOT/"target/npm-cache")]),
        ("typescript-build",source/"sdks/typescript",["npm","run","build"]),
        ("typescript",source/"sdks/typescript",["node","--test","test/client.test.mjs","test/providers.test.mjs","test/v2.test.mjs","test/memory.test.mjs"]),
        ("cross-sdk",source,["cargo","test",*cargo,"--config","profile.test.debug=0","--test","sdk_v2_real","--","--ignored"]),
        ("conformance-build",source,["cargo","build","--locked","-p","hyphae-conformance-rust","--target-dir",str(ROOT/"target/native"),"--jobs","4","--config","profile.dev.debug=0"]),
        ("client-conformance",source,["python3","tools/run_conformance.py"]),
        ("integration-install",source/"integrations/javascript",["npm","ci","--ignore-scripts","--no-audit","--no-fund","--cache",str(ROOT/"target/npm-cache")]),
        ("integration-build",source/"integrations/javascript",["npm","run","build"]),
        ("integration-conformance",source,["python3","tools/run_integration_conformance.py"]),
        ("boundaries",source,["python3","tools/check_integration_boundaries.py"]),
        ("documentation",source,["python3","tools/check_documentation.py","--binary",str(ROOT/"target/native/debug/hyphae")]),
        ("documentation-examples",source,["python3","tools/run_documentation_examples.py","--binary",str(ROOT/"target/native/debug/hyphae")]),
        ("packaging",source,["python3","packaging/test_package.py"]),
    ]
    names=[name for name,_,_ in checks]
    if args.only and set(args.only)-set(names):
        parser.error("Unknown check selection")
    receipt={"schema":"hyphae-omarchy-upstream-checks-v1","started":datetime.now(timezone.utc).isoformat(),"source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=source,text=True).strip(),"source_clean":not bool(subprocess.check_output(["git","status","--porcelain"],cwd=source).strip()),"scope":"selected checks" if args.only else "full local suite","selection":args.only or names,"checks":[]}
    failures=[]
    for name,cwd,command in checks:
        if args.only and name not in args.only:continue
        print(json.dumps({"check":name,"status":"running"}),flush=True)
        begin=time.monotonic()
        with (output/f"{name}.log").open("w") as log:
            result=subprocess.run(command,cwd=cwd,env=environment,stdout=log,stderr=subprocess.STDOUT)
        entry={"check":name,"status":"passed" if result.returncode==0 else "failed","exit_code":result.returncode,"seconds":round(time.monotonic()-begin,3)}
        receipt["checks"].append(entry)
        (output/"checks.json").write_text(json.dumps(receipt,indent=2)+"\n")
        print(json.dumps(entry),flush=True)
        if result.returncode:
            failures.append(name)
            print((output/f"{name}.log").read_text()[-2500:],flush=True)
    receipt["status"]="failed" if failures else "passed"
    (output/"checks.json").write_text(json.dumps(receipt,indent=2)+"\n")
    raise SystemExit(bool(failures))


if __name__=="__main__": main()
