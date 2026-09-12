#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded QML-to-Hyphae bridge. Memory policy and operations live in Hyphae."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

# Omarchy watches plugin source for hot reload. Helper imports must not write
# bytecode into that watched directory during installation or panel actions.
sys.dont_write_bytecode = True

SCHEMA = "hyphae-omarchy-control-v1"
MAX_BYTES = 1024 * 1024
OPERATIONS = {"status", "projects", "agents", "backups", "recall", "list", "store", "forget", "verify", "pause", "configure", "disconnect", "doctor", "backup", "restore", "setup", "service_start", "semantic", "remove", "install", "install_model"}


def fail(code: str, message: str) -> dict:
    return {"schema": SCHEMA, "ok": False, "error": {"code": code, "message": message}}


def data_root() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "hyphae-omarchy"


def runtime_binary() -> str | None:
    override = os.environ.get("HYPHAE_OMARCHY_BINARY")
    if override:
        path = Path(override)
        return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else None
    receipt = data_root() / "runtime.json"
    if receipt.is_file():
        value = json.loads(receipt.read_text(encoding="utf-8"))
        path = Path(value["binary"]).resolve(strict=True)
        if not path.is_relative_to(data_root().resolve()) or not os.access(path, os.X_OK):
            raise ValueError("invalid managed binary")
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != value["sha256"]:
            raise ValueError("managed runtime digest mismatch")
        return str(path)
    return shutil.which("hyphae")


def execute(request: dict) -> dict:
    if set(request) - {"schema", "operation", "arguments", "id"} or not {"schema", "operation", "arguments"} <= set(request) or request["schema"] != SCHEMA or request["operation"] not in OPERATIONS or not isinstance(request["arguments"], dict):
        return fail("invalid_request", "Unsupported memory request.")
    operation = request["operation"]
    if operation in {"install", "install_model"}:
        from runtime import install_model, install_runtime
        result = install_runtime(request["arguments"]) if operation == "install" else install_model(request["arguments"])
        return {"schema": SCHEMA, "ok": True, "result": result}
    binary = runtime_binary()
    if not binary:
        if operation == "status":
            return {"schema": SCHEMA, "ok": True, "result": {"installed": False, "initialized": False, "service_active": False}}
        return fail("not_installed", "Install the Hyphae Memory runtime first.")
    environment = os.environ.copy()
    for key in ("HYPHAE_NATIVE_API_KEY_FILE", "HYPHAE_BASE_URL", "HYPHAE_DATA_DIR", "HYPHAE_ENDPOINT"):
        environment.pop(key, None)
    proved_query = operation in {"recall", "list"} and request["arguments"].get("prove") is True
    timeout = 300 if proved_query or operation in {"semantic", "setup", "service_start", "verify"} else 120 if operation in {"backup", "restore", "doctor", "configure", "disconnect", "remove"} else 10
    process = subprocess.Popen([binary, "agent", "ui"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=environment, start_new_session=True)
    try:
        output, _ = process.communicate(json.dumps(request).encode() + b"\n", timeout=timeout)
    except subprocess.TimeoutExpired:
        # Host CLIs can spawn installers. Stop the whole operation so a timed-out
        # request cannot keep changing agent configuration in the background.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    if len(output) > MAX_BYTES:
        return fail("response_too_large", "The memory response exceeded its bound.")
    try:
        value = json.loads(output)
    except (ValueError, UnicodeError):
        return fail("runtime_incompatible", "This Hyphae runtime needs the Agent Memory control interface. Install the compatible runtime.")
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("id") != request.get("id"):
        return fail("runtime_incompatible", "The installed runtime uses an unsupported memory interface.")
    if value.get("ok") and operation == "status":
        receipt = data_root() / "runtime.json"
        if receipt.is_file():
            value["result"]["runtime_activation_pending"] = bool(json.loads(receipt.read_text()).get("activation_pending"))
    if value.get("ok") and operation in {"setup", "service_start"}:
        receipt = data_root() / "runtime.json"
        if receipt.is_file():
            from runtime import write_json
            installed = json.loads(receipt.read_text())
            installed["activation_pending"] = False
            write_json(receipt, installed)
    return value


def main() -> int:
    try:
        request = {}
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            result = fail("request_too_large", "The memory request is too large.")
        else:
            request = json.loads(raw)
            result = execute(request)
    except subprocess.TimeoutExpired:
        result = fail("timeout", "The operation took too long. Memory data has been preserved; refresh its status before retrying.")
    except (OSError, ValueError, KeyError, TypeError):
        result = fail("operation_failed", "The memory operation could not be completed. Check the selected runtime and local files.")
    result["id"] = request.get("id") if isinstance(request, dict) else None
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
