#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the desktop client source with a complete member inventory."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(['python3',str(ROOT/'scripts/stage-plugin.py')],cwd=ROOT,check=True)
    stage=ROOT/'target/plugin-stage'
    manifest=json.loads((stage/'manifest.json').read_text())
    dist=ROOT/'dist'
    dist.mkdir(exist_ok=True)
    destination=dist/f"hyphae-memory-{manifest['version']}.tar.gz"
    clean=not bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip())
    epoch=int(subprocess.check_output(['git','show','-s','--format=%ct','HEAD'],cwd=ROOT,text=True)) if clean else max(int(path.stat().st_mtime) for path in stage.rglob('*') if path.is_file())
    files={}
    with destination.open('wb') as output, gzip.GzipFile(filename='',fileobj=output,mode='wb',mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for path in sorted(stage.rglob('*')):
            if path.is_dir():
                continue
            if path.is_symlink() or not path.is_file():
                raise SystemExit('Only regular source files may enter a plugin package.')
            name=str(path.relative_to(stage))
            payload=path.read_bytes()
            files[name]={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
            info=tarfile.TarInfo(f"{manifest['id']}/{name}")
            info.size=len(payload)
            info.mode=0o644
            info.mtime=epoch
            with path.open('rb') as stream:
                archive.addfile(info,stream)
    receipt={'schema':'hyphae-memory-panel-package-v1','plugin_id':manifest['id'],'version':manifest['version'],
             'interface':'hyphae-memory-panel-v1','archive':destination.name,'bytes':destination.stat().st_size,
             'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
             'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'source_clean':clean,'source_date_epoch':epoch,'files':files}
    (dist/'package.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({key:value for key,value in receipt.items() if key!='files'}))


if __name__=='__main__':
    main()
