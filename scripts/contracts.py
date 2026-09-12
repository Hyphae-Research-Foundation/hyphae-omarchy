#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the public operator and worker contracts against real local exchanges.

This development check requires jsonschema==4.25.1; the plugin does not.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

NAMES = ("agent-memory-control-v1", "hyphae-attested-model-v1", "hyphae-embed-worker-v1")


class Contracts:
    def __init__(self, directory):
        self.schemas = {}
        self.digests = {}
        self.exchanges = 0
        for name in NAMES:
            raw = (Path(directory) / f"{name}.schema.json").read_bytes()
            schema = json.loads(raw)
            Draft202012Validator.check_schema(schema)
            self.schemas[name] = schema
            self.digests[name] = hashlib.sha256(raw).hexdigest()
        self.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in self.schemas.values()
        )

    def validator(self, name, part=None):
        prefixes = {"agent-memory-control-v1": "AgentMemoryControl", "hyphae-embed-worker-v1": "HyphaeEmbedWorker"}
        reference = self.schemas[name]["$id"] + (f"#/$defs/{prefixes[name]}{part.title()}" if part else "")
        return Draft202012Validator({"$ref": reference}, registry=self.registry)

    def control(self, request, response):
        self.validator("agent-memory-control-v1", "request").validate(request)
        self.validator("agent-memory-control-v1", "response").validate(response)
        self.exchanges += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-dir", type=Path, required=True)
    parser.add_argument("--embed-binary", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contracts = Contracts(args.contract_dir)
    binary = args.embed_binary.resolve(strict=True)
    model_dir = args.model_dir.resolve(strict=True)
    manifest = json.loads(subprocess.check_output(
        [str(binary), "model-info", "--model-dir", str(model_dir)], timeout=60
    ))
    contracts.validator("hyphae-attested-model-v1").validate(manifest)
    request_validator = contracts.validator("hyphae-embed-worker-v1", "request")
    response_validator = contracts.validator("hyphae-embed-worker-v1", "response")
    steps = ["standalone-model-manifest"]
    with tempfile.TemporaryDirectory(prefix="hyphae-contract-") as temporary, tempfile.TemporaryFile() as log:
        endpoint = Path(temporary) / "worker.sock"
        process = subprocess.Popen(
            [str(binary), "serve", "--model-dir", str(model_dir), "--endpoint", str(endpoint)],
            stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while not endpoint.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError("The local worker did not become ready")
                time.sleep(0.025)

            def exchange(request, *, valid_request=True, success=True):
                assert request_validator.is_valid(request) == valid_request
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                    stream.settimeout(30)
                    stream.connect(str(endpoint))
                    stream.sendall(json.dumps(request, ensure_ascii=False).encode() + b"\n")
                    with stream.makefile("rb") as incoming:
                        raw = incoming.readline(16 * 1024 * 1024 + 1)
                    assert len(raw) <= 16 * 1024 * 1024 and raw.endswith(b"\n")
                response = json.loads(raw)
                response_validator.validate(response)
                assert response["ok"] is success
                assert response["id"] == request["id"]
                contracts.exchanges += 1
                return response.get("result")

            request = {"schema": "hyphae-embed-request-v1", "id": 1, "operation": "status"}
            assert exchange(request) == manifest
            steps.append("worker-status-and-model-identity")
            request.update(operation="embed", texts=["Decisión: conservar las memorias."], expected_model=manifest["fingerprint"])
            result = exchange(request)
            assert len(result["vectors"]) == 1 and len(result["vectors"][0]) == manifest["dimensions"]
            assert result["model"] == manifest
            steps.append("bounded-unicode-embedding")
            result = exchange({**request, "operation": "rerank", "query": "keep memory"})
            assert len(result["scores"]) == 1 and result["model"] == manifest
            steps.append("worker-rerank-contract")
            exchange({**request, "expected_model": "0" * 64}, success=False)
            steps.append("mismatched-model-is-rejected")
            exchange({**request, "id": 0}, valid_request=False, success=False)
            steps.append("invalid-request-id-is-rejected")
            control = contracts.validator("agent-memory-control-v1", "request")
            assert not control.is_valid({"schema": "hyphae-omarchy-control-v1", "operation": "restore", "arguments": {"backup": "/tmp/example", "confirm": False}})
            assert not control.is_valid({"schema": "hyphae-omarchy-control-v1", "operation": "status", "arguments": {"access": "write"}})
            steps.append("operator-shapes-reject-missing-confirmation-and-extra-fields")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    receipt = {"schema": "hyphae-omarchy-contract-check-v1", "status": "passed",
        "timestamp": datetime.now(timezone.utc).isoformat(), "contracts": contracts.digests,
        "model_fingerprint": manifest["fingerprint"], "exchanges": contracts.exchanges, "steps": steps}
    with binary.open("rb") as source:
        receipt["embed_binary_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
