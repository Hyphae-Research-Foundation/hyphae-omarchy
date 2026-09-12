#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure the real memory profile on the committed bilingual integration fixture."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as source: return hashlib.file_digest(source,"sha256").hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--embed-binary",type=Path,required=True)
    parser.add_argument("--model-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    fixture=json.loads((ROOT/"tests/retrieval.json").read_text())
    root=Path(tempfile.mkdtemp(prefix="hyo-eval-")); (root/"bin").mkdir()
    binary=root/"bin/hyphae"; embed=root/"bin/hyphae-embed"
    shutil.copy2(args.binary,binary); shutil.copy2(args.embed_binary,embed)
    environment=os.environ.copy()
    for key in ("HYPHAE_NATIVE_API_KEY_FILE","HYPHAE_BASE_URL","HYPHAE_MEMORY_PROJECT"):
        environment.pop(key,None)
    (root/"r").mkdir(mode=0o700)
    environment.update(XDG_DATA_HOME=str(root/"d"),XDG_CONFIG_HOME=str(root/"c"),XDG_STATE_HOME=str(root/"s"),XDG_RUNTIME_DIR=str(root/"r"),HYPHAE_EMBED_BINARY=str(embed))
    daemon=worker=None
    rows=[]
    def ui(operation,arguments=None):
        result=subprocess.run([str(binary),"agent","ui"],input=json.dumps({"schema":"hyphae-omarchy-control-v1","operation":operation,"arguments":arguments or {}}),text=True,capture_output=True,timeout=180,env=environment,cwd=root,check=True)
        result=json.loads(result.stdout)
        if not result["ok"]: raise AssertionError(result)
        return result["result"]
    def start():
        endpoint=ui("status")["endpoint"]
        process=subprocess.Popen([str(binary),"serve","--data-dir",str(root/"d/hyphae/agent-memory"),"--endpoint",endpoint,"--native-api-key-auth"],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(1200):
            if Path(endpoint).exists() and ui("status")["service_active"]: return process
            if process.poll() is not None: raise AssertionError("memory daemon exited")
            time.sleep(.025)
        process.terminate(); process.wait(timeout=10)
        raise AssertionError("memory daemon startup timed out")
    try:
        ui("setup",{"enable_service":False}); daemon=start()
        identities={}
        for record in fixture["records"]:
            identities[record["key"]]=ui("store",{"project":"eval/plugin","text":record["text"],"kind":"decision","harness":"curated-fixture","model":"human-annotated"})["id"]
        for n in range(36):
            ui("store",{"project":"eval/plugin","text":f"Build experiment {n} tracks temporary rendering option {n+100} for a separate UI prototype.","kind":"note"})
        ui("store",{"project":"eval/private-other","text":"Canaryprivate aurora isolation probe.","kind":"fact"})
        assert not ui("recall",{"project":"eval/plugin","query":"Canaryprivate"})["memories"]
        for mode in ("lexical","hybrid"):
            if mode=="hybrid":
                daemon.terminate();daemon.wait(timeout=10);daemon=None
                model=ui("semantic",{"enabled":True,"model_dir":str(args.model_dir.resolve())})["model"]
                daemon=start()
                endpoint=root/"c/hyphae/runtime/embedding.sock"
                worker=subprocess.Popen([str(embed),"serve","--model-dir",str(args.model_dir.resolve()),"--endpoint",str(endpoint)],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(400):
                    if endpoint.exists(): break
                    if worker.poll() is not None: raise AssertionError("embedding worker exited")
                    time.sleep(.025)
                for _ in range(20):
                    subprocess.run([str(binary),"agent","maintain"],env=environment,check=True,capture_output=True,timeout=60)
                    if ui("status")["pending_embeddings"]==0: break
                assert ui("status")["pending_embeddings"]==0
            for record in fixture["records"]:
                for language in ("en","es"):
                    begin=time.perf_counter_ns()
                    result=ui("recall",{"project":"eval/plugin","query":record[language],"mode":mode,"limit":5,"layer":"work"})
                    elapsed=(time.perf_counter_ns()-begin)/1e6
                    assert result["retrieval_mode"]==mode, result
                    assert all(m["project"]=="eval/plugin" for m in result["memories"])
                    ranked=[m["id"] for m in result["memories"]]
                    rank=ranked.index(identities[record["key"]])+1 if identities[record["key"]] in ranked else None
                    rows.append({"query":record["key"],"language":language,"mode":mode,"rank":rank,"milliseconds":round(elapsed,3)})
            print(json.dumps({"mode":mode,"status":"measured"}),flush=True)
        groups=[]
        for mode in ("lexical","hybrid"):
            for language in ("en","es"):
                group=[r for r in rows if r["mode"]==mode and r["language"]==language]
                latencies=sorted(r["milliseconds"] for r in group)
                groups.append({"mode":mode,"language":language,"queries":len(group),"recall_at_1":sum(r["rank"]==1 for r in group)/len(group),"recall_at_5":sum(r["rank"] is not None for r in group)/len(group),"mrr_at_5":statistics.mean(1/r["rank"] if r["rank"] else 0 for r in group),"ndcg_at_5":statistics.mean(1/math.log2(1+r["rank"]) if r["rank"] else 0 for r in group),"p50_ms":statistics.median(latencies),"p95_ms":latencies[math.ceil(.95*len(latencies))-1]})
        receipt={"schema":"hyphae-omarchy-retrieval-evaluation-v1","status":"measured","timestamp":datetime.now(timezone.utc).isoformat(),"fixture_sha256":digest(ROOT/"tests/retrieval.json"),"binary_sha256":digest(binary),"embed_sha256":digest(embed),"model":model,"records":49,"queries":48,"isolation_leaks":0,"scope":"Curated integration fixture; warm local worker; latency includes agent-ui subprocess and transport. No answer-generation or superiority claim.","groups":groups,"results":rows}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(receipt,indent=2)+"\n")
        print(json.dumps({"groups":groups,"isolation_leaks":0}),flush=True)
    finally:
        for process in (worker,daemon):
            if process and process.poll() is None: process.terminate();process.wait(timeout=10)


if __name__=="__main__": main()
