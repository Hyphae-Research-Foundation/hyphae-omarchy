# Local candidate validation

The local candidate is ready for owner review. Hyphae source is
`6ef8914381af3073f69dc1981b0ca1f605da73fa`, built with Rust 1.96.0 for Linux x86_64. The runtime archive SHA-256
is `53692ff83c02d2f05cd7b9d0c9905ebb578114a3b80313f6305d9e7750fb9808`. This is an unpublished integration candidate
on top of Hyphae 3.0.0, with native protocol minor 7.

## Evidence

| Check | Result | Receipt |
| --- | --- | --- |
| Native workspace and development checks | 21 checks passed; 1,783 Rust tests passed, one ignored in the normal run and exercised separately | [Upstream](validation/upstream.json) |
| Python / TypeScript / embedding component | 102 Python tests (15 optional/platform skips), 52 TypeScript tests, 3 embedding tests; generated models and cross-SDK fixture passed | [Upstream](validation/upstream.json) |
| Plugin installer and cancellation | 6 tests passed, including tamper/preservation and stopping descendants on timeout | [Review](validation/review.json) |
| Release runtime and operator JSON | 14 lifecycle/proof steps passed with schema validation | [Runtime](validation/runtime.json) |
| Local model and worker contracts | Real model manifest, Unicode inference, reranking, fingerprint rejection and request validation passed | [Contracts](validation/contracts.json) |
| Four official host clients | Registration, loader/callback interfaces, edited-file protection, reconnect and removal passed with networking disabled | [Hosts](validation/hosts.json), [binary/image identity](validation/hosts-run.json) |
| Packaged Omarchy lifecycle | 14 steps passed, including systemd restart, corrupt/valid restore, removal, reinstall and restoring an older credential authority | [VM](validation/vm-lifecycle.json) |
| Actual desktop | QML lint and six inspected screenshots; bar open, keyboard search, proof verification, cancellation, explicit global sharing and maintenance controls exercised | [Visual](validation/visual.json), [installed files](validation/production-files.json) |
| Portable source | Public base fetched; bundle verified; clean candidate reconstructed; readable patch matches | [Source](validation/source-reconstruction.json) |
| Runtime contents | Eight inventoried members; CycloneDX 1.6 validation, 330 normal/build dependencies and retained license texts | [Inventory](validation/runtime-inventory.json) |

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
| EN | lexical | 16.7% | 25.0% | 0.188 | 3.35 | 4.50 |
| ES | lexical | 25.0% | 50.0% | 0.361 | 3.57 | 4.41 |
| EN | hybrid | 16.7% | 58.3% | 0.311 | 20.20 | 23.63 |
| ES | hybrid | 41.7% | 50.0% | 0.458 | 28.62 | 33.17 |

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
The GitHub Actions workflow is prepared but has not run on a hosted runner.
Local evidence does not replace Hyphae's exact-commit G7/G8 publication gates.
No repository, release or marketplace listing has been published.

See [development](DEVELOPMENT.md) for commands and [the marketplace draft](MARKETPLACE.md)
for the proposed listing and owner submission steps.
