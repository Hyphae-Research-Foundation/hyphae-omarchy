#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a development runtime and plugin in the VM's read-only project share."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SHARE=ROOT/"target/vm/share"


def digest(path):
    with path.open("rb") as source:return hashlib.file_digest(source,"sha256").hexdigest()


def main():
    subprocess.run(["python3",str(ROOT/"scripts/stage-plugin.py")],check=True)
    SHARE.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/"target/plugin-stage",SHARE/"plugin",dirs_exist_ok=True)
    runtime=SHARE/"runtime"
    runtime.mkdir(exist_ok=True)
    files={}
    for source,name in ((ROOT/"target/native/debug/hyphae","hyphae"),(ROOT/"target/embed/debug/hyphae-embed","hyphae-embed")):
        files[name]=digest(source)
        shutil.copy2(source,runtime/name)
    metadata={"schema":"hyphae-omarchy-development-runtime-v1","files":files,
        "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT/".upstream/hyphae",text=True).strip()}
    metadata["id"]=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    (runtime/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    shutil.copytree(ROOT/"target/models/bge-small-en-v1.5",SHARE/"model",dirs_exist_ok=True)
    print(SHARE)


if __name__=="__main__":main()
