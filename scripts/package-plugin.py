#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package tracked plugin source and its reviewed runtime as one offline archive."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    lock=json.loads((ROOT/"runtime.lock.json").read_text())
    bundle=ROOT/"dist"/lock["bundle"]["name"]
    with bundle.open("rb") as source:
        if hashlib.file_digest(source,"sha256").hexdigest()!=lock["bundle"]["sha256"]:
            raise SystemExit("Rebuild the reviewed runtime before packaging.")
    subprocess.run(["python3",str(ROOT/"scripts/stage-plugin.py")],cwd=ROOT,check=True)
    stage=ROOT/"target/plugin-stage"
    manifest=json.loads((stage/"manifest.json").read_text())
    destination=ROOT/"dist"/f"hyphae-memory-{manifest['version']}.tar.gz"
    files=[(path.relative_to(stage),path) for path in stage.rglob("*") if path.is_file()]
    files.append((Path("dist")/bundle.name,bundle))
    with destination.open("wb") as output, gzip.GzipFile(filename="",fileobj=output,mode="wb",mtime=0) as compressed, tarfile.open(fileobj=compressed,mode="w",format=tarfile.USTAR_FORMAT) as archive:
        for name,path in sorted(files):
            if path.is_symlink(): raise SystemExit("Plugin archives contain only regular files.")
            info=tarfile.TarInfo(f"{manifest['id']}/{name}"); info.size=path.stat().st_size; info.mode=0o644
            with path.open("rb") as source: archive.addfile(info,source)
    with destination.open("rb") as source: digest=hashlib.file_digest(source,"sha256").hexdigest()
    receipt={"schema":"hyphae-omarchy-plugin-package-v1","plugin_id":manifest["id"],"version":manifest["version"],"archive":destination.name,"bytes":destination.stat().st_size,"sha256":digest,"runtime_sha256":lock["bundle"]["sha256"],"source_commit":lock["source_commit"]}
    (ROOT/"dist/package.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt),flush=True)


if __name__=="__main__": main()
