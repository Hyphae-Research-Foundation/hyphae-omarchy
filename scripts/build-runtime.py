#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and inventory the exact reviewed Hyphae source revision for Linux x86_64."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tomllib
from dependencies import inventories

ROOT=Path(__file__).resolve().parents[1]


def run(arguments, source, environment=None):
    return subprocess.check_output(arguments,cwd=source,env=environment,text=True).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--jobs",type=int,default=4)
    parser.add_argument("--skip-build",action="store_true",help="Repackage the same clean source and binary inventory already recorded in runtime.lock.json")
    args=parser.parse_args()
    source=args.source.resolve(strict=True)
    if platform.system()!="Linux" or platform.machine()!="x86_64":
        raise SystemExit("Build the Omarchy candidate on Linux x86_64.")
    lock=json.loads((ROOT/"source.lock.json").read_text())
    revision=run(["git","rev-parse","HEAD"],source)
    if revision!=lock["hyphae"]["candidate_commit"] or run(["git","status","--porcelain"],source):
        raise SystemExit("The source must be clean and match source.lock.json.")
    if not 1<=args.jobs<=16: raise SystemExit("Use 1 through 16 build jobs.")
    toolchain=tomllib.loads((source/"rust-toolchain.toml").read_text())["toolchain"]["channel"]
    if toolchain != lock["rust"]:
        raise SystemExit("The source toolchain differs from source.lock.json.")
    environment=os.environ.copy()
    for key in ("RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","RUSTUP_TOOLCHAIN"):
        environment.pop(key,None)
    environment["SOURCE_DATE_EPOCH"]=run(["git","show","-s","--format=%ct","HEAD"],source)
    environment["CARGO_ENCODED_RUSTFLAGS"]="\x1f".join([f"--remap-path-prefix={source}=/usr/src/hyphae","-C","debuginfo=0"])
    binaries={}
    previous=json.loads((ROOT/"runtime.lock.json").read_text()) if args.skip_build else None
    if previous and previous["source_commit"] != revision:
        raise SystemExit("Compile this revision before using --skip-build.")
    for package,manifest,target in (("hyphae-cli",source/"Cargo.toml",ROOT/"target/native"),("hyphae-embed",source/"embed/Cargo.toml",ROOT/"target/embed")):
        if not args.skip_build:
            subprocess.run(["cargo",f"+{toolchain}","build","--manifest-path",str(manifest),"-p",package,"--release","--locked","--target","x86_64-unknown-linux-gnu","--target-dir",str(target),"--jobs",str(args.jobs)],cwd=source,env=environment,check=True)
        name="hyphae" if package=="hyphae-cli" else "hyphae-embed"
        binaries[f"bin/{name}"]=target/"x86_64-unknown-linux-gnu/release"/name
        if previous:
            with binaries[f"bin/{name}"].open("rb") as binary:
                if hashlib.file_digest(binary,"sha256").hexdigest() != previous["files"][f"bin/{name}"]["sha256"]:
                    raise SystemExit("The existing binary differs from its build receipt; rebuild it.")
    metadata={"schema":"hyphae-omarchy-runtime-source-v1","source_commit":revision,
        "upstream_base":lock["hyphae"]["base_commit"],"rust":run(["rustc",f"+{toolchain}","--version"],source),
        "target":"x86_64-unknown-linux-gnu","profile":"release","protocol_minor":7,
        "control_schema":"hyphae-omarchy-control-v1","source_date_epoch":int(environment["SOURCE_DATE_EPOCH"])}
    payloads={name:path.read_bytes() for name,path in binaries.items()}
    payloads["share/LICENSE"]= (source/"LICENSE").read_bytes()
    payloads["share/THIRD_PARTY_NOTICES.md"]= (source/"THIRD_PARTY_NOTICES.md").read_bytes()
    payloads["share/LICENSE-DOCUMENTATION"]= (source/"LICENSE-DOCUMENTATION").read_bytes()
    payloads["share/SOURCE.json"]=(json.dumps(metadata,indent=2,sort_keys=True)+"\n").encode()
    payloads["share/SBOM.cdx.json"],payloads["share/DEPENDENCY_LICENSES.txt"]=inventories(source,toolchain,revision,int(environment["SOURCE_DATE_EPOCH"]),environment)
    if run(["git","rev-parse","HEAD"],source) != revision or run(["git","status","--porcelain"],source):
        raise SystemExit("The source changed during the build; no runtime lock was updated.")
    inventory={name:{"sha256":hashlib.sha256(value).hexdigest(),"bytes":len(value)} for name,value in payloads.items()}
    dist=ROOT/"dist"
    dist.mkdir(exist_ok=True)
    name=f"hyphae-memory-0.1.0-linux-x86_64-{revision[:12]}.tar.gz"
    destination=dist/name
    temporary=destination.with_suffix(".pending")
    with temporary.open("wb") as output, gzip.GzipFile(filename="",fileobj=output,mode="wb",mtime=0) as compressed, tarfile.open(fileobj=compressed,mode="w",format=tarfile.USTAR_FORMAT) as archive:
        for member,value in sorted(payloads.items()):
            info=tarfile.TarInfo(member); info.size=len(value); info.mode=0o555 if member.startswith("bin/") else 0o444
            archive.addfile(info,io.BytesIO(value))
    temporary.replace(destination)
    with destination.open("rb") as bundle: checksum=hashlib.file_digest(bundle,"sha256").hexdigest()
    reviewed={"schema":"hyphae-omarchy-runtime-lock-v1","source_commit":revision,
        "bundle":{"name":name,"url":None,"bytes":destination.stat().st_size,"sha256":checksum},"files":inventory,"build":metadata}
    (ROOT/"runtime.lock.json").write_text(json.dumps(reviewed,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"bundle":str(destination),"sha256":checksum,"source_commit":revision}),flush=True)


if __name__=="__main__": main()
