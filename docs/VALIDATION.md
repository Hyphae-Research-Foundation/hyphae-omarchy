# Release validation

Hyphae Memory 0.1.0 is bound to public Hyphae source
`8fe08dfce903d09e4e5f4b82ba02d3d28ec45191` and native protocol minor 7. The runtime archive SHA-256 is
`2c93f3ee4af72615fcff4d4ae390538c7f7db9f5136429ad85a1e36504183255`. The CLI is the exact signed upstream artifact
whose tree matches this merge; the optional Candle worker is built from that
same source with Rust 1.96.0 for Linux x86_64.

## Evidence

| Check | Result | Receipt |
| --- | --- | --- |
| Native workspace and development checks | 21 checks passed; 1,783 Rust tests passed, one ignored in the normal run and exercised separately | [Upstream](validation/upstream.json) |
| Python / TypeScript / embedding component | 102 Python tests (15 optional/platform skips), 52 TypeScript tests, 3 embedding tests; generated models and cross-SDK fixture passed | [Upstream](validation/upstream.json) |
| Plugin installer, cancellation and source pin | 10 tests passed, including tamper/preservation, timeout descendants and source drift | [Review](validation/review.json) |
| Release runtime and operator JSON | 14 lifecycle/proof steps passed with schema validation | [Runtime](validation/runtime.json) |
| Local model and worker contracts | Real model manifest, Unicode inference, reranking, fingerprint rejection and request validation passed | [Contracts](validation/contracts.json) |
| Four official host clients | Registration, loader/callback interfaces, edited-file protection, reconnect and removal passed with networking disabled | [Hosts](validation/hosts.json), [binary/image identity](validation/hosts-run.json) |
| Packaged Omarchy lifecycle | 14 steps passed, including systemd restart, corrupt/valid restore, removal, reinstall and restoring an older credential authority | [VM](validation/vm-lifecycle.json) |
| Actual desktop | QML lint and six inspected screenshots; bar open, keyboard search, proof verification, cancellation, explicit global sharing and maintenance controls exercised | [Visual](validation/visual.json), [installed files](validation/production-files.json) |
| Public source | Exact public commit fetched; Git tree and clean checkout verified | [Source](validation/source-reconstruction.json) |
| Runtime contents | 10 inventoried members; CycloneDX 1.6 validation, 325 normal/build dependencies and retained license texts | [Inventory](validation/runtime-inventory.json) |

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
| EN | lexical | 16.7% | 25.0% | 0.188 | 3.03 | 3.88 |
| ES | lexical | 25.0% | 50.0% | 0.361 | 3.11 | 4.12 |
| EN | hybrid | 16.7% | 58.3% | 0.311 | 18.55 | 21.80 |
| ES | hybrid | 41.7% | 50.0% | 0.458 | 25.37 | 30.10 |

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
