#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real Hyphae runtime in an isolated XDG profile with synthetic data."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time

SCHEMA = "hyphae-omarchy-control-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--embed-binary", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract-dir", type=Path, help="Validate each exchange with the upstream JSON Schemas (requires jsonschema)")
    args = parser.parse_args()
    contracts = None
    if args.contract_dir:
        from contracts import Contracts
        contracts = Contracts(args.contract_dir)
    binary = args.binary.resolve()
    fixture = Path(tempfile.mkdtemp(prefix="hyo-"))
    work = fixture / "work"
    work.mkdir()
    environment = os.environ.copy()
    for key in ("HYPHAE_NATIVE_API_KEY_FILE", "HYPHAE_BASE_URL", "HYPHAE_DATA_DIR", "HYPHAE_ENDPOINT", "HYPHAE_MEMORY_PROJECT"):
        environment.pop(key, None)
    environment.update(XDG_DATA_HOME=str(fixture / "d"), XDG_CONFIG_HOME=str(fixture / "c"), XDG_STATE_HOME=str(fixture / "s"))
    if args.embed_binary:
        environment["HYPHAE_EMBED_BINARY"] = str(args.embed_binary.resolve())
    daemon = None
    worker = None
    transcript = bytearray()
    steps = []

    def command(arguments, payload=None, timeout=120):
        result = subprocess.run([str(binary), *arguments], input=None if payload is None else json.dumps(payload).encode(),
                                capture_output=True, timeout=timeout, env=environment, cwd=work)
        transcript.extend(result.stdout)
        transcript.extend(result.stderr)
        if result.returncode:
            raise AssertionError(f"command failed: {arguments}: {result.stderr.decode(errors='replace')[:500]}")
        return result.stdout

    def ui(operation, arguments=None, *, expect=True):
        request = {"schema": SCHEMA, "operation": operation, "arguments": arguments or {}}
        value = json.loads(command(["agent", "ui"], request))
        if contracts:
            contracts.control(request, value)
        assert value["schema"] == SCHEMA
        if expect:
            assert value["ok"], (operation, value)
        return value.get("result", value)

    data = fixture / "d/hyphae/agent-memory"
    endpoint = None

    def start():
        process = subprocess.Popen([str(binary), "serve", "--data-dir", str(data), "--endpoint", str(endpoint), "--native-api-key-auth"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=environment, cwd=work)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode(errors="replace"))
            if endpoint.exists() and ui("status", expect=False).get("service_active"):
                return process
            time.sleep(.025)
        raise AssertionError("daemon did not bind")

    def step(name):
        steps.append(name)
        print(json.dumps({"step": name, "status": "passed"}), flush=True)

    try:
        ui("setup", {"enable_service": False})
        endpoint = Path(ui("status")["endpoint"])
        daemon = start()
        assert ui("status")["service_active"]
        step("setup-and-native-control")
        stored = ui("store", {"project": "audit/project", "text": "Decision: aurora keeps durable build decisions.", "kind": "decision"})
        for layer in ("work", "all"):
            result = ui("recall", {"project": "audit/project", "query": "aurora durable", "layer": layer, "prove": True})
            assert any(memory["id"] == stored["id"] for memory in result["memories"])
            proof = result["proof"]
            checked = ui("verify", {"proof": proof["proof_path"], "witness": proof["witness_path"], "anchor": proof["anchor_hex"]})
            assert checked["kind"] == "memory" and checked["scope"] == "semantic_reexecution"
        step("proved-multilayer-recall")
        assert not ui("recall", {"project": "audit/other", "query": "aurora durable"})["memories"]
        step("project-isolation")
        command(["agent", "hook", "--host", "opencode"], {"event": "prompt", "cwd": str(work), "prompt": "Decision: nebula uses a reproducible packaging workflow.", "model": "test/model"})
        command(["agent", "maintain"])
        assert ui("recall", {"query": "nebula packaging"})["memories"]
        step("shared-hook-and-mcp-project-identity")
        ui("pause", {"paused": True})
        command(["agent", "hook", "--host", "pi"], {"event": "prompt", "cwd": str(work), "prompt": "Decision: forbiddenpause must not be captured.", "model": "test/model"})
        command(["agent", "maintain"])
        assert not ui("recall", {"query": "forbiddenpause"})["memories"]
        ui("pause", {"paused": False})
        step("paused-capture-does-not-spool")
        daemon.kill()
        daemon.wait(timeout=5)
        daemon = start()
        assert ui("recall", {"project": "audit/project", "query": "aurora"})["memories"]
        step("hard-restart-durability")
        ui("backup")
        backups = ui("backups")["backups"]
        assert backups
        refused = ui("restore", {"backup":backups[0]["path"],"confirm":True}, expect=False)
        assert not refused["ok"]
        assert ui("recall", {"project":"audit/project","query":"aurora"})["memories"]
        step("restore-refuses-an-independently-owned-directory")
        damaged = Path(backups[0]["path"]).with_name("agent-memory-damaged")
        shutil.copytree(backups[0]["path"], damaged)
        victim = next(path for path in damaged.rglob("*") if path.is_file() and path.name != "LOCK")
        with victim.open("ab") as output:
            output.write(b"intentional-corruption-fixture")
        ui("forget", {"project": "audit/project", "id": stored["id"]})
        assert not ui("recall", {"project": "audit/project", "query": "aurora"})["memories"]
        step("forget-removes-recallability")
        daemon.terminate()
        daemon.wait(timeout=5)
        daemon = None
        refused = ui("restore", {"backup":str(damaged),"confirm":True}, expect=False)
        assert not refused["ok"]
        daemon = start()
        assert not ui("recall", {"project":"audit/project","query":"aurora"})["memories"]
        daemon.terminate()
        daemon.wait(timeout=5)
        daemon = None
        step("corrupt-backup-preserves-the-current-memory-directory")
        ui("restore", {"backup": backups[0]["path"], "confirm": True})
        daemon = start()
        assert ui("recall", {"project": "audit/project", "query": "aurora"})["memories"]
        step("verified-backup-and-restore")
        if args.model_dir:
            assert args.embed_binary
            daemon.terminate()
            daemon.wait(timeout=5)
            daemon = None
            ui("semantic", {"enabled": True, "model_dir": str(args.model_dir.resolve())})
            daemon = start()
            socket = fixture / "c/hyphae/runtime/embedding.sock"
            worker = subprocess.Popen([str(args.embed_binary.resolve()), "serve", "--model-dir", str(args.model_dir.resolve()), "--endpoint", str(socket)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=environment, cwd=work)
            for _ in range(400):
                if worker.poll() is not None:
                    raise AssertionError(worker.stderr.read().decode(errors="replace"))
                if socket.exists():
                    break
                time.sleep(.025)
            else:
                raise AssertionError("embedding worker did not bind")
            for _ in range(8):
                command(["agent", "maintain"])
                if ui("status")["pending_embeddings"] == 0:
                    break
            assert ui("status")["pending_embeddings"] == 0
            unproved = ui("recall", {"project": "audit/project", "query": "remember reliable compilation choices", "mode": "hybrid"})
            assert unproved["retrieval_mode"] == "hybrid", unproved
            step("native-embedding-migration-backfill-and-hybrid-recall")
            result = ui("recall", {"project": "audit/project", "query": "remember reliable compilation choices", "mode": "hybrid", "prove": True})
            assert result["retrieval_mode"] == "hybrid", result
            assert any(memory["id"] == stored["id"] for memory in result["memories"]), result
            proof = result["proof"]
            assert ui("verify", {"proof": proof["proof_path"], "witness": proof["witness_path"], "anchor": proof["anchor_hex"]})["status"] == "verified"
            step("native-embedding-migration-backfill-and-hybrid-proof")
            worker.terminate()
            worker.wait(timeout=5)
            worker = None
            result = ui("recall", {"project": "audit/project", "query": "aurora", "mode": "hybrid"})
            assert result["retrieval_mode"] == "lexical" and result["semantic_status"] == "unavailable"
            step("embedding-outage-retains-lexical-memory")
        for key in (fixture / "c/hyphae/credentials").glob("*.key"):
            assert key.read_bytes().strip() not in transcript, "credential appeared in output"
        step("credential-canary-output-scan")
        with binary.open("rb") as source:
            binary_digest = hashlib.file_digest(source, "sha256").hexdigest()
        receipt = {"schema": "hyphae-omarchy-runtime-check-v1", "status": "passed", "steps": steps,
            "timestamp": datetime.now(timezone.utc).isoformat(), "binary_sha256": binary_digest, "fixture": str(fixture)}
        if args.embed_binary:
            with args.embed_binary.open("rb") as source:
                receipt["embed_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
        if contracts:
            receipt.update(contracts=contracts.digests, contract_exchanges=contracts.exchanges)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)
        return 0
    finally:
        for process in (worker, daemon):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        print(json.dumps({"fixture": str(fixture)}), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
