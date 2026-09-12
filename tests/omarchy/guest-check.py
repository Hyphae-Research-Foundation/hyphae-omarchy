#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the installed plugin bridge and real user services inside the QA VM."""
import argparse
import json
from pathlib import Path
import subprocess
import time

plugin=Path.home()/".config/omarchy/plugins/org.hyphaeresearch.memory"
parser=argparse.ArgumentParser()
parser.add_argument("phase",choices=["setup","status","seed","semantic","backup","awake"])
args=parser.parse_args()


def control(operation,arguments=None):
    output=subprocess.check_output(["python3",str(plugin/"scripts/bridge.py")],input=json.dumps({"schema":"hyphae-omarchy-control-v1","operation":operation,"arguments":arguments or {},"id":1}).encode(),timeout=300)
    value=json.loads(output)
    print(json.dumps({"operation":operation,**value}),flush=True)
    if not value["ok"]:raise SystemExit(1)
    return value["result"]


if args.phase=="awake":
    path=Path.home()/".config/omarchy/shell.json"
    value=json.loads(path.read_text())
    value["idle"]={**value.get("idle",{}),"screensaver":86400,"lock":86400}
    path.write_text(json.dumps(value,indent=2)+"\n")
    print("QA idle timeouts extended for visual verification.")
elif args.phase=="setup":
    control("setup",{"enable_service":True})
    for _ in range(30):
        if control("status")["service_active"]:break
        time.sleep(.5)
    else:raise SystemExit("User memory service did not become ready")
elif args.phase=="status":control("status")
elif args.phase=="seed":
    records=[]
    for kind,text in [("decision","Use Hyphae's own embeddings and keep all agent memory on this computer."),("constraint","Las pruebas completas se generan cuando el usuario solicita verificar una consulta."),("fact","Removing the integration preserves memories and verified backups.")]:
        records.append(control("store",{"project":"qa/desktop","kind":kind,"text":text,"harness":"omarchy-vm","model":"user"}))
    (Path.home()/"hyphae-qa-records.json").write_text(json.dumps(records))
    control("recall",{"project":"qa/desktop","query":"Hyphae embeddings","mode":"lexical"})
elif args.phase=="semantic":
    model=control("install_model")
    control("semantic",{"enabled":True,"model_dir":model["model_dir"]})
    for _ in range(60):
        state=control("status")
        if state.get("semantic_ready") and state.get("pending_embeddings")==0:break
        time.sleep(1)
    else:raise SystemExit("Semantic worker did not become ready")
elif args.phase=="backup":control("backup")
