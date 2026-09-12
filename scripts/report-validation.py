#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Publish only mutually consistent local candidate receipts and a review report."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "target/validation"


def read(path):
    return json.loads(path.read_text())


def main():
    source = read(ROOT / "source.lock.json")["hyphae"]["commit"]
    runtime = read(ROOT / "runtime.lock.json")
    assert runtime["source_commit"] == source
    binary = runtime["files"]["bin/hyphae"]["sha256"]
    embed = runtime["files"]["bin/hyphae-embed"]["sha256"]
    sources = {
        "upstream": "upstream/checks.json", "runtime": "runtime-release.json",
        "hosts-run": "hosts/run.json", "hosts": "hosts/hosts.json",
        "contracts": "contracts-release.json", "source-reconstruction": "source-reconstruction.json",
        "runtime-inventory": "runtime-inventory.json", "vm-lifecycle": "vm/lifecycle.json",
        "visual": "vm/visual.json", "production-files": "vm/production-files.json",
        "retrieval": "retrieval-release.json",
    }
    receipts = {name: read(VALIDATION / path) for name, path in sources.items()}
    for name, receipt in receipts.items():
        assert receipt["status"] == ("measured" if name == "retrieval" else "passed"), name
        if "source_commit" in receipt:
            assert receipt["source_commit"] == source, name
        if "binary_sha256" in receipt:
            assert receipt["binary_sha256"] == binary, name
        if "embed_sha256" in receipt:
            assert receipt["embed_sha256"] == embed, name
        if "embed_binary_sha256" in receipt:
            assert receipt["embed_binary_sha256"] == embed, name
        if "runtime_sha256" in receipt:
            assert receipt["runtime_sha256"] == runtime["bundle"]["sha256"], name
    upstream = receipts["upstream"]
    assert upstream["scope"] == "full local suite" and upstream["source_clean"]
    assert len(upstream["checks"]) == 21 and all(check["status"] == "passed" for check in upstream["checks"])
    assert len(receipts["runtime"]["steps"]) == 14
    assert len(receipts["vm-lifecycle"]["steps"]) == 14
    assert receipts["hosts-run"]["network"] == "none"
    assert receipts["retrieval"]["isolation_leaks"] == 0
    assert not receipts["production-files"]["bytecode_cache_created"]
    for field in (receipts["production-files"]["files"], receipts["visual"]["source_files"]):
        for name, expected in field.items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    for name, expected in receipts["visual"]["screenshots"].items():
        assert hashlib.sha256((ROOT / "docs/screenshots" / name).read_bytes()).hexdigest() == expected, name
    plugin_tests = int(re.search(r"Ran (\d+) tests", (VALIDATION / "plugin-tests.log").read_text()).group(1))
    assert plugin_tests == 10
    assert (VALIDATION / "plugin-tests.log").read_text().rstrip().endswith("OK")
    totals = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;", (VALIDATION / "upstream/rust.log").read_text())
    rust_passed = sum(int(value[0]) for value in totals)
    assert all(value[1] == "0" for value in totals)
    output = ROOT / "docs/validation"
    output.mkdir(parents=True, exist_ok=True)
    receipts["runtime"].pop("fixture", None)
    for name, receipt in receipts.items():
        (output / f"{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    summary = {"schema": "hyphae-omarchy-release-validation-v1", "status": "verified",
        "timestamp": datetime.now(timezone.utc).isoformat(), "source_commit": source,
        "binary_sha256": binary, "runtime_sha256": runtime["bundle"]["sha256"],
        "native_checks": len(upstream["checks"]), "rust_tests_passed": rust_passed,
        "plugin_tests_passed": plugin_tests, "runtime_steps": 14, "vm_steps": 14,
        "upstream_g8": "closed", "upstream_g8_receipt": "upstream/native-g8.json"}
    (output / "review.json").write_text(json.dumps(summary, indent=2) + "\n")
    rows = []
    for group in receipts["retrieval"]["groups"]:
        rows.append(f"| {group['language'].upper()} | {group['mode']} | {group['recall_at_1']:.1%} | {group['recall_at_5']:.1%} | {group['mrr_at_5']:.3f} | {group['p50_ms']:.2f} | {group['p95_ms']:.2f} |")
    inventory_members = len(runtime["files"])
    inventory_components = receipts["runtime-inventory"]["components"]
    g8 = read(ROOT / "upstream/native-g8.json")
    assert g8["status"] == "passed" and g8["source_commit"] == source and g8["closure_declared"]
    report = f"""# Release validation

Hyphae Memory 0.1.0 is bound to public Hyphae source
`{source}` and native protocol minor 7. The runtime archive SHA-256 is
`{runtime['bundle']['sha256']}`. The CLI is the exact signed upstream artifact
whose tree matches this merge; the optional Candle worker is built from that
same source with Rust 1.96.0 for Linux x86_64.

## Evidence

| Check | Result | Receipt |
| --- | --- | --- |
| Native workspace and development checks | 21 checks passed; {rust_passed:,} Rust tests passed, one ignored in the normal run and exercised separately | [Upstream](validation/upstream.json) |
| Python / TypeScript / embedding component | 102 Python tests (15 optional/platform skips), 52 TypeScript tests, 3 embedding tests; generated models and cross-SDK fixture passed | [Upstream](validation/upstream.json) |
| Plugin installer, cancellation and source pin | {plugin_tests} tests passed, including tamper/preservation, timeout descendants and source drift | [Review](validation/review.json) |
| Release runtime and operator JSON | 14 lifecycle/proof steps passed with schema validation | [Runtime](validation/runtime.json) |
| Local model and worker contracts | Real model manifest, Unicode inference, reranking, fingerprint rejection and request validation passed | [Contracts](validation/contracts.json) |
| Four official host clients | Registration, loader/callback interfaces, edited-file protection, reconnect and removal passed with networking disabled | [Hosts](validation/hosts.json), [binary/image identity](validation/hosts-run.json) |
| Packaged Omarchy lifecycle | 14 steps passed, including systemd restart, corrupt/valid restore, removal, reinstall and restoring an older credential authority | [VM](validation/vm-lifecycle.json) |
| Actual desktop | QML lint and six inspected screenshots; bar open, keyboard search, proof verification, cancellation, explicit global sharing and maintenance controls exercised | [Visual](validation/visual.json), [installed files](validation/production-files.json) |
| Public source | Exact public commit fetched; Git tree and clean checkout verified | [Source](validation/source-reconstruction.json) |
| Runtime contents | {inventory_members} inventoried members; CycloneDX 1.6 validation, {inventory_components} normal/build dependencies and retained license texts | [Inventory](validation/runtime-inventory.json) |

The VM uses Omarchy/settings 4.0.3-1, Hyprland 0.56.2-2 and Quickshell 0.3.1-1
on QEMU/KVM. The ISO package version is authoritative; its source version text
still says alpha. Repeated diagnostic profiles were preserved in the private
guest QA directory before the main lifecycle fixture was initialized.

The VM receipt records the archive tested at that point. Documentation and
receipt packaging can change the outer archive digest afterward; the installed
production-file inventory and runtime digest bind the behavior tested here.
The final archive identity is in `dist/package.json`, with a separate final
installation receipt retained under `dist/validation/`.

## Curated retrieval fixture

There are 12 annotated memories, 36 distractors and one separate-project
canary. The 12 English and 12 Spanish queries are each measured in lexical and
hybrid mode, for 48 observations. No project-isolation leak was observed.

| Language | Mode | Recall@1 | Recall@5 | MRR@5 | p50 ms | p95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

[Raw measurements](validation/retrieval.json) identify the fixture, model and
binaries. Latency includes the agent-ui subprocess and transport on a shared
development workstation with a warm local CPU worker. This small curated
fixture does not establish production quality, answer correctness, independent
model execution, or superiority over other systems. The English-oriented BGE
reference model did not improve every Spanish recall measure.

## Limits and release status

Complete proof and witness data share the native 16-MiB response bound.
Larger retained histories can exceed it; the request returns `limit_exceeded`
and ordinary recall remains available. A native regression reproduced the
previous timeout at the encoding boundary and verifies a terminal error plus
continued use of the connection.

Witnesses may contain retained directory data and stay private. Keep an anchor
separately for independent verification. Forget/expiry affects live recall;
historical versions and backups are not a secure-erase guarantee.

Host checks use real CLIs and lifecycle APIs without paid model conversations.
Codex still requires review of changed non-managed hooks through `/hooks`.
The [upstream G8 closure](../upstream/native-g8.json) covers the exact Hyphae
source and signed native engine artifacts. G7 remained in authority mode;
no new dedicated-hardware measurements are claimed. The optional worker and
Omarchy integration are covered by the additional checks recorded above.
The repository workflow verifies the public source and plugin on GitHub;
release assets retain the final publication and installation records.

See [development](DEVELOPMENT.md) for commands and [the marketplace submission](MARKETPLACE.md)
for listing details and the review process.
"""
    (ROOT / "docs/VALIDATION.md").write_text(report)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
