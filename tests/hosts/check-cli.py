#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run official host CLIs in a disposable container; never use host credentials."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time

root = Path(tempfile.mkdtemp(prefix="hyo-hosts-"))
work = root / "project"
work.mkdir()
environment = os.environ.copy()
environment["PATH"] = "/hosts/node_modules/.bin:" + environment["PATH"]
environment.update(XDG_CONFIG_HOME=str(Path.home() / ".config"), XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"))
environment["OPENCODE_DISABLE_MODELS_FETCH"] = "true"
environment["OPENCODE_DISABLE_AUTOUPDATE"] = "true"
environment["OPENCODE_DISABLE_DEFAULT_PLUGINS"] = "true"
binary = "/runtime/hyphae"
steps = []


def run(argv, payload=None, check=True, timeout=30):
    try:
        completed = subprocess.run(argv, input=None if payload is None else json.dumps(payload).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, cwd=work, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        Path("/artifacts/host-timeout.log").write_bytes((error.stdout or b"") + (error.stderr or b""))
        raise
    if check and completed.returncode:
        raise AssertionError(f"{argv}: {completed.stderr.decode(errors='replace')[:1000]} {completed.stdout.decode(errors='replace')[:1000]}")
    return completed


def ui_result(operation, arguments=None):
    result = json.loads(run([binary,"agent","ui"], {"schema":"hyphae-omarchy-control-v1","operation":operation,"arguments":arguments or {}}).stdout)
    return result


def ui(operation, arguments=None):
    result = ui_result(operation, arguments)
    assert result["ok"], result
    return result["result"]


daemon = None
try:
    run(["git","init","--quiet"])
    versions = {host:run([host,"--version"]).stdout.decode().strip() for host in ("claude","codex","opencode","pi")}
    ui("setup", {"enable_service":False})
    endpoint = ui("status")["endpoint"]
    daemon = subprocess.Popen([binary,"serve","--data-dir",str(root / "data/hyphae/agent-memory"),"--endpoint",endpoint,"--native-api-key-auth"], env=environment, cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if Path(endpoint).exists(): break
        time.sleep(.05)
    assert ui("status")["service_active"]
    # Independent hook handlers must survive configure, reconnect and removal.
    unrelated = {"type":"command","command":"/usr/bin/true"}
    for path in (Path.home()/".claude/settings.json", Path.home()/".codex/hooks.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"hooks":{"SessionStart":[{"hooks":[unrelated]}]}}))
    for host in versions:
        run([binary,"agent","configure",host,"--access","write","--apply"])
    steps.append("official-cli-registration-for-four-hosts")
    print(json.dumps({"step":steps[-1],"status":"passed"}),flush=True)
    assert all(agent["configured"] for agent in ui("agents")["agents"])
    codex = json.loads(run(["codex","mcp","get","hyphae-memory","--json"]).stdout)
    assert codex["transport"]["command"] == binary, codex
    claude = run(["claude","mcp","get","hyphae-memory"])
    config_files = [str(path.relative_to(Path.home())) for path in Path.home().rglob("*.json") if path.is_file() and "node_modules" not in str(path)]
    Path("/artifacts/host-config-files.json").write_text(json.dumps(config_files, indent=2))
    Path("/artifacts/claude-get.txt").write_bytes(claude.stdout + claude.stderr)
    assert b"hyphae-memory" in claude.stdout + claude.stderr
    ui("store", {"text":"Decision: nebula keeps shared host context.","kind":"decision"})
    run(["node","/hosts/check-extensions.mjs",str(work)], timeout=60)
    steps.append("real-pi-loader-and-opencode-lifecycle-apis")
    print(json.dumps({"step":steps[-1],"status":"passed"}),flush=True)
    # OpenCode resolves its generated local plugin and contributes MCP config.
    oc_config = Path(environment["XDG_CONFIG_HOME"])/"opencode"
    (oc_config/"package.json").write_bytes(Path("/hosts/package.json").read_bytes())
    (oc_config/"package-lock.json").write_bytes(Path("/hosts/package-lock.json").read_bytes())
    (oc_config/"node_modules").symlink_to("/hosts/node_modules",target_is_directory=True)
    oc_command = ["opencode","debug","config","--print-logs","--log-level","DEBUG"]
    if environment.get("HYO_TRACE_OPENCODE"):
        oc_command = ["strace","-f","-e","trace=connect,openat,execve,wait4,epoll_wait,poll,statx","-o","/artifacts/opencode.strace",*oc_command]
    opencode = run(oc_command, timeout=30)
    oc = json.loads(opencode.stdout)
    assert oc["mcp"]["hyphae-memory"]["command"][0] == binary, oc
    steps.append("opencode-native-plugin-loader-and-mcp-config")
    # Refuse edited managed entries before touching any other registration or
    # deleting credentials. Keep unrelated hooks and all memory data intact.
    edits = [
        ("claude", Path.home()/".claude.json"),
        ("codex", Path.home()/".codex/config.toml"),
        ("opencode", Path(environment["XDG_CONFIG_HOME"])/"opencode/plugins/hyphae-memory.ts"),
        ("pi", Path.home()/".pi/agent/extensions/hyphae-memory.ts"),
    ]
    credentials = {p:hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (Path(environment["XDG_CONFIG_HOME"])/"hyphae/credentials").glob("*.key")}
    assert credentials
    for host, path in edits:
        original = path.read_bytes()
        if host == "claude":
            value = json.loads(original)
            value["mcpServers"]["hyphae-memory"]["command"] = "/usr/bin/false"
            edited = json.dumps(value).encode()
        elif host == "codex":
            assert binary.encode() in original
            edited = original.replace(binary.encode(), b"/usr/bin/false")
        else:
            edited = original + b"\n// QA operator edit: preserve this file.\n"
        path.write_bytes(edited)
        try:
            for operation, arguments in [("configure", {"host":host,"access":"read"}),
                                         ("disconnect", {"host":host}), ("remove", {"confirm":True})]:
                assert not ui_result(operation, arguments)["ok"], (host, operation)
                assert path.read_bytes() == edited
                assert all(a["configured"] for a in ui("agents")["agents"])
                assert ui("status")["service_active"]
                assert all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest
                           for p,digest in credentials.items())
        finally:
            path.write_bytes(original)
    steps.append("edited-mcp-and-extensions-block-reconnect-disconnect-and-removal")
    for host in versions:
        run([binary,"agent","configure",host,"--access","read","--apply"])
        ui("disconnect", {"host":host})
    for path in (Path.home()/".claude/settings.json", Path.home()/".codex/hooks.json"):
        groups = json.loads(path.read_text())["hooks"]["SessionStart"]
        assert any(unrelated in group["hooks"] for group in groups), path
        assert not any("hyphae" in hook["command"] for group in groups for hook in group["hooks"]), path
    assert not any(agent["configured"] for agent in ui("agents")["agents"])
    steps.append("reconnect-disconnect-preserves-independent-handlers")
    receipt = {"schema":"hyphae-host-conformance-v1","status":"passed","versions":versions,"steps":steps}
    Path("/artifacts/hosts.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps(receipt), flush=True)
finally:
    if daemon:
        daemon.terminate()
        daemon.wait(timeout=10)
