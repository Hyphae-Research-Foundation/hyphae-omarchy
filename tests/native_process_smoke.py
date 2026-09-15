#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Benign native Quickshell process smoke tests in private temporary fixtures.

Run on the QA VM: python3 tests/native_process_smoke.py --report target/native-process.json
No live Hyphae configuration, service, memory, PATH substitution or persistence is used.
The only production-copy overrides are the documented short deadline and a separate
missing-dependency case. Native qmllint remains a separate check; diagnostics are kept.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("BoundedMemoryProcess.qml", "ProcessLimits.js", "MemoryController.qml", "scripts/bridge.py")
QUICKSHELL = "/usr/bin/quickshell"
MARKER = b"HYPHAE_NATIVE_SMOKE "
NOTE = "水辺の記憶 ☂"
LOG_LIMIT = 256 * 1024
CASE_TIMEOUT = 12
CASES = {
    "unicode": ["status"],
    "queue": ["status", "projects", "backups"],
    "uncertain": ["status", "store"],
    "deadline": ["status"],
    "missing": [],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def process_identity(pid):
    """Read only a fixture child's process metadata, never its memory/configuration."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return fields[19]  # Linux starttime, so a reused PID is not treated as our child.
    except (FileNotFoundError, ProcessLookupError):
        return None


def process_group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def signal_process_group(pid, number):
    try:
        os.killpg(pid, number)
    except ProcessLookupError:
        pass


class FixtureServer:
    def __init__(self, directory, case):
        self.case = case
        self.secret = "hypm1_" + secrets.token_hex(32)
        self.endpoint = directory / "memory.sock"
        self.config = directory / "client.json"
        self.config.write_text(json.dumps({"schema": "hyphae-memory-panel-connection-v1",
                                          "endpoint": str(self.endpoint), "token": self.secret}))
        self.config.chmod(0o600)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.records, self.errors, self.overlaps, self.workers = [], [], [], []
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.endpoint))
        self.endpoint.chmod(0o600)
        self.listener.listen(8)
        self.listener.settimeout(0.1)
        self.acceptor = threading.Thread(target=self.accept, daemon=True)
        self.acceptor.start()

    def accept(self):
        while not self.stop.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            pid, uid, _ = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            with self.lock:
                if uid != os.getuid() or len(self.records) >= 8:
                    self.errors.append("Unexpected fixture peer or excessive fixture connections")
                    client.close()
                    continue
                for old in self.records:
                    if old["start"] is not None and process_identity(old["pid"]) == old["start"]:
                        self.overlaps.append([old["pid"], pid])
                record = {"pid": pid, "start": process_identity(pid), "operation": None}
                # Inspect only the fixture's authenticated child. Record names and
                # booleans; never include environment values in diagnostics.
                environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
                names = sorted(entry.split(b"=", 1)[0].decode("ascii") for entry in environment if entry)
                command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                record["environmentNames"] = names
                record["isolatedInterpreter"] = command[:4] == [b"/usr/bin/python3", b"-I", b"-S", b"-B"]
                allowed = {"LC_ALL", "HOME", "XDG_CONFIG_HOME", "HYPHAE_MEMORY_PANEL_CONFIG"}
                if not set(names) <= allowed or not record["isolatedInterpreter"]:
                    self.errors.append("Fixture child did not use the isolated interpreter/minimal environment")
                self.records.append(record)
            worker = threading.Thread(target=self.respond, args=(client, record), daemon=True)
            self.workers.append(worker)
            worker.start()

    def respond(self, client, record):
        try:
            with client:
                client.settimeout(2)
                data = bytearray()
                while True:
                    chunk = client.recv(16384)
                    if not chunk:
                        break
                    if len(data) + len(chunk) > 65536:
                        raise ValueError("Fixture request exceeded its small request budget")
                    data.extend(chunk)
                request = json.loads(data)
                if request.get("schema") != "hyphae-memory-panel-v1" or request.get("token") != self.secret:
                    raise ValueError("Fixture request authentication/schema mismatch")
                operation = request.get("operation")
                if operation not in {"status", "projects", "backups", "store", "recall"}:
                    raise ValueError("Unexpected fixture operation")
                with self.lock:
                    record["operation"] = operation
                if self.case == "deadline" and self.stop.wait(1.0):
                    return
                response = {"schema": request["schema"], "id": request["id"], "ok": True,
                            "result": {"fixturePid": record["pid"]}}
                if operation == "status":
                    response["result"].update(connected=True, message=NOTE)
                elif operation == "projects":
                    response["result"]["projects"] = ["qa-fixture"]
                elif operation == "backups":
                    response["result"]["backups"] = []
                elif operation == "store" and self.case == "uncertain":
                    # Explicit uncertainty about a dummy operation; nothing is persisted.
                    response = {"schema": request["schema"], "id": request["id"], "ok": False,
                                "error": {"code": "outcome_unknown"}}
                else:
                    raise ValueError("A queued operation reached the fixture unexpectedly")
                client.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            if self.case != "deadline" and not self.stop.is_set():
                self.errors.append("Fixture connection closed before its response")
        except (OSError, ValueError, TypeError) as error:
            if not self.stop.is_set():
                self.errors.append(str(error).replace(self.secret, "<fixture-secret>"))

    def snapshot(self):
        with self.lock:
            return [dict(record) for record in self.records]

    def close(self):
        self.stop.set()
        self.listener.close()
        self.acceptor.join(1)
        for worker in self.workers:
            worker.join(1)


def shell_source(case):
    """QML observes production signals and properties; it does not replace their logic."""
    if case in {"unicode", "missing"}:
        component = '''
  BoundedMemoryProcess {
    id: boundary
    onChildPidChanged: if (childPid > 0) harness.lastPid = childPid
    onResponse: function(value) {
      harness.completions++;
      harness.note("completed", {operation: "status", pid: value.result.fixturePid});
      if (CASE !== "unicode" || value.result.message !== EXPECTED || busy || childPid !== 0)
        harness.finish(false, "Unexpected response or unreleased boundary");
      else settle.restart();
    }
    onFailed: function(code, possiblySubmitted) {
      harness.failures++;
      harness.note("failure", {pid: harness.lastPid, code: code, submitted: possiblySubmitted});
      if (CASE !== "missing" || code !== "startup" || possiblySubmitted || busy || childPid !== 0)
        harness.finish(false, "Unexpected failure or unreleased boundary");
      else settle.restart();
    }
    onStalled: harness.finish(false, "Fixture child did not stop")
  }
  Component.onCompleted: boundary.begin(Limits.requestPacket({
    id: 1, schema: "hyphae-memory-panel-v1", operation: "status", arguments: {}
  }))
'''
        final_check = ('harness.completions === 1 && harness.failures === 0' if case == "unicode"
                       else 'harness.completions === 0 && harness.failures === 1 && !boundary.busy')
    else:
        actions = ('controller.request("projects", {}); controller.request("backups", {});'
                   if case in {"queue", "deadline"} else
                   'controller.request("store", {project: "qa-fixture", text: "dummy, no persistence"}); '
                   'controller.request("recall", {project: "qa-fixture", query: "dummy"}); '
                   'controller.request("backups", {});')
        component = '''
  MemoryController {
    id: controller
    onCompleted: function(operation, result) {
      harness.completions++;
      harness.note("completed", {operation: operation, pid: result.fixturePid});
      if (operation === "status" && result.message !== EXPECTED)
        harness.finish(false, "Unicode result did not survive ASCII framing");
      else if (CASE === "queue" && harness.completions === 3) settle.restart();
      else if (CASE !== "queue" && (CASE !== "uncertain" || operation !== "status"))
        harness.finish(false, "Queued operation continued after a fault");
    }
    onBusyChanged: if (!busy && error === Limits.errorMessage(FAILURE)) {
      harness.failures++;
      harness.note("failure", {code: FAILURE, operation: errorOperation, pending: pending.length});
      settle.restart();
    }
  }
  Component.onCompleted: Qt.callLater(function() { ACTIONS })
'''.replace("ACTIONS", actions)
        if case == "queue":
            final_check = 'harness.completions === 3 && !controller.busy && controller.pending.length === 0 && !controller.error'
        else:
            final_check = ('harness.completions === ' + ("1" if case == "uncertain" else "0")
                           + ' && harness.failures === 1 && !controller.busy && controller.pending.length === 0'
                           + ' && controller.error === Limits.errorMessage(FAILURE)'
                           + ' && controller.errorOperation === ' + json.dumps("store" if case == "uncertain" else "status"))
    text = '''import QtQuick
import Quickshell
import "."
import "ProcessLimits.js" as Limits
ShellRoot {
  id: harness
  property int completions: 0
  property int failures: 0
  property int lastPid: 0
  property bool finished: false
  function note(kind, value) {
    value.event = kind;
    console.log("HYPHAE_NATIVE_SMOKE " + JSON.stringify(value));
  }
  function finish(ok, reason) {
    if (finished) return;
    finished = true;
    note("done", {ok: ok, reason: reason, completions: completions, failures: failures});
    Qt.quit();
  }
  Timer { id: settle; interval: SETTLE; onTriggered: harness.finish(CHECK, "settled") }
  Timer { interval: 8000; running: true; onTriggered: harness.finish(false, "Native QML watchdog") }
COMPONENT
}
'''.replace("SETTLE", "1500" if case == "deadline" else "500")
    return (text.replace("COMPONENT", component).replace("CHECK", final_check)
            .replace("EXPECTED", json.dumps(NOTE)).replace("CASE", json.dumps(case))
            .replace("FAILURE", json.dumps("outcome_unknown" if case == "uncertain" else "timeout")))


def run_native(stage, server):
    env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
    env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1",
               HYPHAE_MEMORY_PANEL_CONFIG=str(server.config), LC_ALL="C.UTF-8")
    for variable, directory in (("XDG_RUNTIME_DIR", "runtime"), ("XDG_CONFIG_HOME", "config"),
                                ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data"),
                                ("XDG_STATE_HOME", "state")):
        path = stage / directory
        path.mkdir(mode=0o700)
        env[variable] = str(path)
    # HOME/CODEX_HOME are neither reassigned nor forwarded. The connection override
    # is mandatory and points only to this fixture's private config.
    process = subprocess.Popen([QUICKSHELL, "-p", str(stage / "shell.qml"), "--no-color"],
                               cwd=stage, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    log, pending, events, reap_checks = bytearray(), bytearray(), [], []
    deadline = time.monotonic() + CASE_TIMEOUT
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Native harness exceeded its bounded timeout")
            if not selector.select(0.1):
                continue
            data = os.read(process.stdout.fileno(), 16384)
            if not data:
                break
            if len(log) + len(data) > LOG_LIMIT:
                raise ValueError("Native diagnostics exceeded the harness log budget")
            log.extend(data)
            pending.extend(data)
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending = bytearray(rest)
                if MARKER not in line:
                    continue
                event, _ = json.JSONDecoder().raw_decode(line.split(MARKER, 1)[1].decode("utf-8"))
                events.append(event)
                pid = event.get("pid")
                if pid:
                    if not any(record["pid"] == pid for record in server.snapshot()):
                        raise ValueError("Callback referenced a PID not authenticated by the fixture")
                    gone = process_identity(pid) is None
                    reap_checks.append({"pid": pid, "absentWhenCallbackObserved": gone})
                    if not gone:
                        raise ValueError("Fixture child was still present when completion was observed")
                elif event.get("event") == "failure":
                    for record in server.snapshot():
                        gone = process_identity(record["pid"]) != record["start"]
                        reap_checks.append({"pid": record["pid"], "absentWhenFailureObserved": gone})
                        if not gone:
                            raise ValueError("Fixture child was still present when failure was observed")
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
        done = [event for event in events if event.get("event") == "done"]
        if process.returncode != 0 or len(done) != 1 or not done[0].get("ok"):
            raise ValueError("Native QML scenario did not report exactly one successful completion")
        if process_group_exists(process.pid):
            raise ValueError("The fixture's private process group still has a child after Quickshell exited")
        return {"events": events, "postReapObservations": reap_checks, "exitCode": process.returncode,
                "ownedProcessGroupEmptyAfterExit": True}
    finally:
        selector.close()
        if process.poll() is None:
            signal_process_group(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                signal_process_group(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
        if process_group_exists(process.pid):
            signal_process_group(process.pid, signal.SIGKILL)  # Only the new session created above.
        process.stdout.close()
        run_native.diagnostics = log.decode("utf-8", errors="replace").replace(server.secret, "<fixture-secret>")


def run_case(base, case, blobs):
    stage = base / case
    stage.mkdir(mode=0o700)
    copied = dict(blobs)
    overrides = []
    if case == "deadline":
        old = b"var LIFETIME_MS = 140000;"
        if copied["ProcessLimits.js"].count(old) != 1:
            raise ValueError("The production deadline changed; review the test-only override")
        copied["ProcessLimits.js"] = copied["ProcessLimits.js"].replace(old, b"var LIFETIME_MS = 200;")
        overrides.append({"file": "ProcessLimits.js", "testOnly": "LIFETIME_MS: 140000 -> 200"})
    if case == "missing":
        old = b'"/usr/bin/python3"'
        if copied["BoundedMemoryProcess.qml"].count(old) != 1:
            raise ValueError("The production interpreter changed; review the missing-dependency fixture")
        copied["BoundedMemoryProcess.qml"] = copied["BoundedMemoryProcess.qml"].replace(
            old, json.dumps(str(stage / "nonexistent-python")).encode())
        overrides.append({"file": "BoundedMemoryProcess.qml", "testOnly": "Interpreter is an absolute nonexistent fixture path"})
    for name, data in copied.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (stage / "shell.qml").write_text(shell_source(case))
    private = stage / "private"
    private.mkdir(mode=0o700)
    server = FixtureServer(private, case)
    result = {"case": case, "overrides": overrides, "copiedSourceHashes": {name: sha(data) for name, data in copied.items()}}
    run_native.diagnostics = ""
    try:
        result.update(run_native(stage, server))
        records = server.snapshot()
        callbacks = [event.get("operation") for event in result["events"] if event["event"] == "completed"]
        expected_callbacks = CASES[case] if case in {"unicode", "queue"} else (["status"] if case == "uncertain" else [])
        if ([r["operation"] for r in records] != CASES[case] or callbacks != expected_callbacks
                or any(r["start"] is None for r in records) or server.errors or server.overlaps):
            raise ValueError("Fixture request order, cleanup or no-overlap check failed")
        result["passed"] = True
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=str(error))
    finally:
        server.close()
        records = server.snapshot()
        result["fixtureRequests"] = [{key: r[key] for key in
                                      ("operation", "pid", "environmentNames", "isolatedInterpreter")}
                                     for r in records]
        result["overlappingChildConnections"] = server.overlaps
        result["remainingChildren"] = [r["pid"] for r in records if r["start"] is not None
                                       and process_identity(r["pid"]) == r["start"]]
        result["fixtureErrors"] = server.errors
        if server.errors or result["remainingChildren"]:
            result.update(passed=False, error="Fixture errors or remaining fixture children after cleanup")
        result["diagnostics"] = run_native.diagnostics.replace(str(base), "$FIXTURE")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    blobs = {name: (args.source / name).read_bytes() for name in SOURCES}
    hashes = {name: sha(data) for name, data in blobs.items()}
    report = {"schema": 1, "scope": "Native guarded-code smoke tests; private fixtures only", "sourceHashes": hashes,
              "liveServiceUsed": False, "liveMemoryConfigurationUsed": False, "persistentMemoryWrites": False,
              "nativeLintRun": False, "knownLintDiagnostic": "QProcess::ExitStatus signal parameter metadata warning; native success path verifies runtime delivery"}
    if not Path(QUICKSHELL).is_file():
        report.update(passed=False, error=f"Required native binary is missing: {QUICKSHELL}")
    else:
        with tempfile.TemporaryDirectory(prefix="hyp-qml-", dir="/tmp") as temporary:
            report["cases"] = [run_case(Path(temporary), case, blobs) for case in CASES]
        report["sourceChangedDuringRun"] = hashes != {name: sha((args.source / name).read_bytes()) for name in SOURCES}
        report["passed"] = all(case["passed"] for case in report["cases"]) and not report["sourceChangedDuringRun"]
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
