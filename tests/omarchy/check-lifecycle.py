#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a packaged candidate and real systemd lifecycle in the disposable QA VM."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time

PLUGIN_ID = "org.hyphaeresearch.memory"
SCHEMA = "hyphae-omarchy-control-v1"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    if platform.node() != "hyphae-omarchy-qa" or not Path("/mnt/hyphae").is_mount():
        raise SystemExit("Run only in the disposable Hyphae Omarchy QA VM with its project share mounted.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=Path("/mnt/hyphae/release"))
    parser.add_argument("--output", type=Path, default=Path.home() / "hyphae-qa-lifecycle.json")
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Preserve the current synthetic QA profile and initialize a fresh one")
    args = parser.parse_args()
    plugin = Path.home() / ".config/omarchy/plugins" / PLUGIN_ID
    receipt_file = Path.home() / ".local/share/hyphae-omarchy/runtime.json"
    environment = os.environ.copy()
    environment["OMARCHY_PATH"] = "/usr/share/omarchy"
    environment["PATH"] = "/usr/share/omarchy/bin:" + environment["PATH"]
    package = json.loads((args.package_dir / "package.json").read_text())
    archive = args.package_dir / package["archive"]
    assert archive.name == package["archive"] and package["plugin_id"] == PLUGIN_ID
    assert archive.stat().st_size == package["bytes"] and digest(archive) == package["sha256"]
    report = {"schema": "hyphae-omarchy-vm-lifecycle-v1", "status": "running",
        "started": datetime.now(timezone.utc).isoformat(), "source_commit": package["source_commit"],
        "package_sha256": package["sha256"], "runtime_sha256": package["runtime_sha256"], "steps": []}

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    def step(name):
        report["steps"].append(name)
        save()
        print(json.dumps({"step": name, "status": "passed"}), flush=True)

    def run(command, *, check=True):
        return subprocess.run(command, env=environment, check=check, capture_output=True, text=True, timeout=180)

    def control(operation, arguments=None, *, success=True):
        request = {"schema": SCHEMA, "operation": operation, "arguments": arguments or {}, "id": 1}
        process = subprocess.run(["python3", str(plugin / "scripts/bridge.py")],
            input=json.dumps(request), env=environment, capture_output=True, text=True, timeout=330, check=True)
        response = json.loads(process.stdout)
        assert response["schema"] == SCHEMA and response["id"] == 1
        if operation == "store" and response["ok"] is not success:
            # Inputs here are synthetic QA fixtures. Retain a rejected fixture
            # privately so intermittent validation failures can be replayed.
            (Path.home() / "hyphae-qa-rejected-store.json").write_text(json.dumps(request, indent=2) + "\n")
        assert response["ok"] is success, (operation, response.get("error"))
        return response.get("result")

    def wait_ready(*, semantic=False):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = control("status")
            if state["service_active"] and (not semantic or (state["semantic_ready"] and state["pending_embeddings"] == 0)):
                return state
            time.sleep(0.5)
        raise AssertionError("The managed services did not become ready")

    try:
        original_agents = control("agents")["agents"] if plugin.exists() else []
        if args.fresh:
            control("remove", {"confirm": True})
            preserved = Path.home() / ".local/state/hyphae-omarchy-qa" / ("preserved-" + str(time.time_ns()))
            preserved.mkdir(parents=True, mode=0o700)
            for name, path in (("data", Path.home() / ".local/share/hyphae/agent-memory"),
                               ("config", Path.home() / ".config/hyphae"),
                               ("state", Path.home() / ".local/state/hyphae")):
                if path.exists():
                    path.rename(preserved / name)
            report["fresh_profile"] = True
            step("previous-synthetic-profile-preserved")
        if plugin.exists():
            run(["omarchy-plugin-disable", PLUGIN_ID])
        cache = Path.home() / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hyphae-package-", dir=cache) as temporary:
            with tarfile.open(archive) as source:
                members = source.getmembers()
                assert sum(member.size for member in members) <= 512 * 1024 * 1024
                assert all(member.isfile() and member.name.startswith(PLUGIN_ID + "/") for member in members)
                source.extractall(temporary, filter="data")
            previous = Path(temporary) / "previous-plugin"
            if plugin.exists():
                plugin.rename(previous)
            try:
                (Path(temporary) / PLUGIN_ID).rename(plugin)
                run(["omarchy-plugin-validate", str(plugin)])
            except Exception:
                if plugin.exists():
                    shutil.rmtree(plugin)
                if previous.exists():
                    previous.rename(plugin)
                raise
        run(["omarchy-plugin-validate", str(plugin)])
        run(["omarchy-shell", "shell", "rescanPlugins"])
        run(["omarchy-plugin-enable", PLUGIN_ID])
        step("packaged-plugin-passes-official-validator-and-loads")
        control("install")
        installed = json.loads(receipt_file.read_text())
        assert installed["activation_pending"] and installed["source_commit"] == package["source_commit"]
        assert installed["bundle_sha256"] == package["runtime_sha256"]
        assert digest(Path(installed["binary"])) == installed["sha256"]
        assert digest(Path(installed["embed_binary"])) == installed["embed_sha256"]
        step("offline-runtime-inventory-verification")
        state = control("status")
        control("service_start" if state["initialized"] else "setup", {} if state["initialized"] else {"enable_service": True})
        assert control("status")["service_active"], "Activation returned before native IPC was ready"
        state = wait_ready(semantic=state.get("semantic_enabled", False))
        assert not state["runtime_activation_pending"]
        unit = run(["systemctl", "--user", "show", "hyphae-agent-memory.service", "--property=ExecStart", "--value"]).stdout
        assert installed["binary"] in unit
        if state["semantic_enabled"]:
            unit = run(["systemctl", "--user", "show", "hyphae-agent-embed.service", "--property=ExecStart", "--value"]).stdout
            assert installed["embed_binary"] in unit
        if args.fresh:
            for agent in original_agents:
                if agent["configured"]:
                    control("configure", {"host": agent["id"], "access": agent["access"] or "read"})
            control("service_start")
            assert control("status")["service_active"]
        report["binary_sha256"] = installed["sha256"]
        report["embed_sha256"] = installed["embed_sha256"]
        step("runtime-activation-refreshes-systemd-and-existing-agents")
        if not args.install_only:
            if not state["semantic_enabled"]:
                model = control("install_model")
                control("semantic", {"enabled": True, "model_dir": model["model_dir"]})
            wait_ready(semantic=True)
            nonce = "lifecycle" + str(time.time_ns())
            project = "qa/lifecycle"
            stored = control("store", {"project": project, "text": "Decision: " + nonce + " keeps memories across reinstall and restart.", "kind": "decision"})
            wait_ready(semantic=True)

            def recall(prove=False, mode="lexical"):
                return control("recall", {"project": project, "query": nonce, "mode": mode, "prove": prove})

            result = recall(prove=True, mode="hybrid")
            assert result["retrieval_mode"] == "hybrid" and any(item["id"] == stored["id"] for item in result["memories"])
            proof = result["proof"]
            assert control("verify", {"proof": proof["proof_path"], "witness": proof["witness_path"], "anchor": proof["anchor_hex"]})["status"] == "verified"
            step("systemd-embedding-backfill-and-hybrid-proof")
            control("pause", {"paused": True})
            assert control("status")["capture_paused"]
            control("pause", {"paused": False})
            assert not control("status")["capture_paused"]
            step("capture-pause-and-resume")
            run(["systemctl", "--user", "stop", "hyphae-agent-embed.service"])
            result = recall(mode="hybrid")
            assert result["retrieval_mode"] == "lexical" and result["semantic_status"] == "unavailable"
            run(["systemctl", "--user", "start", "hyphae-agent-embed.service"])
            wait_ready(semantic=True)
            step("worker-outage-and-systemd-recovery")
            old_pid = run(["systemctl", "--user", "show", "hyphae-agent-memory.service", "--property=MainPID", "--value"]).stdout.strip()
            run(["systemctl", "--user", "kill", "--signal=SIGKILL", "hyphae-agent-memory.service"])
            wait_ready(semantic=True)
            new_pid = run(["systemctl", "--user", "show", "hyphae-agent-memory.service", "--property=MainPID", "--value"]).stdout.strip()
            assert new_pid != old_pid and new_pid != "0"
            assert any(item["id"] == stored["id"] for item in recall()["memories"])
            step("sigkill-restart-retains-memory")
            before = {item["path"] for item in control("backups")["backups"]}
            control("backup")
            backup = next(Path(item["path"]) for item in control("backups")["backups"] if item["path"] not in before)
            control("forget", {"project": project, "id": stored["id"]})
            assert not recall()["memories"]
            damaged = backup.with_name("agent-memory-invalid-" + nonce)
            credential_dir = Path.home() / ".config/hyphae/credentials"
            credential_hashes = {name: digest(credential_dir / name) for name in ("operator.key", "memory-reader.key", "memory-writer.key")}
            try:
                shutil.copytree(backup, damaged)
                victim = next(path for path in damaged.rglob("*") if path.is_file() and path.name != "LOCK")
                with victim.open("ab") as output:
                    output.write(b"intentional-backup-corruption")
                control("restore", {"backup": str(damaged), "confirm": True}, success=False)
                wait_ready(semantic=True)
                assert not recall()["memories"]
                assert all(digest(credential_dir / name) == expected for name, expected in credential_hashes.items())
            finally:
                if damaged.exists():
                    shutil.rmtree(damaged)
            step("failed-restore-preserves-current-data-and-restarts-service")
            control("restore", {"backup": str(backup), "confirm": True})
            wait_ready(semantic=True)
            assert any(item["id"] == stored["id"] for item in recall(mode="hybrid")["memories"])
            step("verified-restore-recovers-memory-and-worker")
            run(["omarchy-plugin-disable", PLUGIN_ID])
            assert control("status")["service_active"] and recall()["memories"]
            run(["omarchy-plugin-enable", PLUGIN_ID])
            step("widget-disable-preserves-running-memory")
            control("remove", {"confirm": True})
            assert (Path.home() / ".local/share/hyphae/agent-memory/FORMAT").is_file() and backup.is_dir()
            assert run(["systemctl", "--user", "is-active", "hyphae-agent-memory.service"], check=False).returncode != 0
            assert all(not agent["configured"] for agent in control("agents")["agents"])
            assert not control("status")["initialized"], "The panel must offer setup for the preserved data directory"
            step("integration-removal-preserves-data-and-backups")
            control("setup", {"enable_service": True})
            assert control("status")["service_active"], "Setup returned before native IPC was ready"
            wait_ready(semantic=True)
            assert any(item["id"] == stored["id"] for item in recall(mode="hybrid")["memories"])
            control("restore", {"backup": str(backup), "confirm": True})
            wait_ready(semantic=True)
            assert any(item["id"] == stored["id"] for item in recall(mode="hybrid")["memories"])
            assert list((Path.home() / ".config/hyphae").glob("credentials-before-restore-*"))
            step("older-backup-recovers-credentials-after-reinstall")
            for agent in original_agents:
                if agent["configured"]:
                    control("configure", {"host": agent["id"], "access": agent["access"] or "read"})
            connected = {agent["id"] for agent in control("agents")["agents"] if agent["configured"]}
            assert connected == {agent["id"] for agent in original_agents if agent["configured"]}
            step("reinstall-recovers-memory-worker-and-agent-connections")
        report["packages"] = run(["pacman", "-Q", "omarchy", "omarchy-settings", "hyprland", "quickshell"]).stdout.strip().splitlines()
        report["status"] = "passed"
        report["finished"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps(report), flush=True)
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = type(error).__name__ + ": " + str(error)
        save()
        raise


if __name__ == "__main__":
    main()
