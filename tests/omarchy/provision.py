#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install this development candidate in the disposable VM user's profile."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

share=Path("/mnt/hyphae")
home=Path.home()
plugin=home/".config/omarchy/plugins/org.hyphaeresearch.memory"
metadata=json.loads((share/"runtime/metadata.json").read_text())
runtime=home/".local/share/hyphae-omarchy/development"/metadata["id"]
runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
for name,expected in metadata["files"].items():
    source=share/"runtime"/name
    with source.open("rb") as input_file:assert hashlib.file_digest(input_file,"sha256").hexdigest()==expected
    destination=runtime/name
    shutil.copy2(source,destination)
    destination.chmod(0o700)
receipt=runtime.parents[1]/"runtime.json"
receipt.write_text(json.dumps({"schema":"hyphae-omarchy-runtime-v1","binary":str(runtime/"hyphae"),"embed_binary":str(runtime/"hyphae-embed"),"sha256":metadata["files"]["hyphae"],"embed_sha256":metadata["files"]["hyphae-embed"],"source_commit":metadata["source_commit"],"activation_pending":False,"development":True}))
receipt.chmod(0o600)
shutil.copytree(share/"plugin",plugin,dirs_exist_ok=True)
lock=json.loads((plugin/"models.lock.json").read_text())
cache=home/".local/share/hyphae-omarchy/downloads"
cache.mkdir(parents=True,exist_ok=True,mode=0o700)
for entry in lock["files"]:
    source=share/"model"/entry["path"]
    with source.open("rb") as input_file:assert hashlib.file_digest(input_file,"sha256").hexdigest()==entry["sha256"]
    shutil.copy2(source,cache/entry["sha256"])
environment=os.environ.copy()
environment["OMARCHY_PATH"]="/usr/share/omarchy"
environment["PATH"]="/usr/share/omarchy/bin:"+environment["PATH"]
subprocess.run(["/usr/share/omarchy/bin/omarchy-plugin-validate",str(plugin)],env=environment,check=True)
subprocess.run(["/usr/share/omarchy/bin/omarchy-plugin-enable","org.hyphaeresearch.memory"],env=environment,check=True)
print(json.dumps({"status":"development-candidate-installed","source_commit":metadata["source_commit"],"runtime":str(runtime),"plugin":str(plugin)}))
