# Validation of Hyphae Memory 0.2.1

## 0.2.1 process-hardening checks

The maintainer-review patch passed client, JavaScript and native Quickshell
checks on 15 September 2026. The [0.2.1 receipt](validation/process-boundary-0.2.1.json)
records the tested production hashes. The older screenshots and full-engine
receipts below remain the 0.2.0 baseline.

| Surface | Current result | Reproduce |
| --- | --- | --- |
| Python bridge | 29 tests passed, including an isolated subprocess and temporary Unix socket | `/usr/bin/python3 -I -S -B -m unittest discover -s tests -p test_bridge.py -v` |
| Pure JavaScript process limits | 8 tests passed | `node tests/test_process_limits.cjs` |
| Official Omarchy manifest validation | Passed | `omarchy plugin validate <staged-plugin>` |
| QML lint, Qt 6.11.2 / Quickshell 0.3.1 | Exit 0; one type-metadata warning described below | `qmllint -I /usr/lib/qt6/qml BoundedMemoryProcess.qml MemoryController.qml` |
| Native process lifecycle | 5 scenarios passed; no overlapping connections or remaining fixture children | [Native report](validation/process-native-0.2.1.json), `python3 tests/native_process_smoke.py` |

The Python checks cover normal minimal-environment startup, ASCII JSON Unicode
round-tripping, final output-size checks before writing, bounded fallback errors,
the 135-second socket deadline, known native rejections and uncertain mutation
results without retries. Fault handling uses small fixtures or unit mocks; no
live memory service is involved.

The JavaScript checks cover UTF-8 request sizing, the 4-MiB stdout admission
budget before retention, its three-byte per-chunk BOM reserve, the separate
2-MiB-plus-newline retained ASCII bound, launch paths and mutation messages.
They exercise the pure policy functions. The native tests run the current QML
components and bridge on Omarchy 4.0.3, Quickshell 0.3.1, Qt 6.11.2 and Python
3.14.7. They check Unicode through ASCII JSON, startup plus two queued reads,
an uncertain dummy write that discards the queue, deadline-triggered TERM cleanup,
and deferred failed-start cleanup. Fixture child metadata confirms the absolute
isolated interpreter and allowlisted environment names. Completion/failure
observations find the prior children reaped; every private process group is
empty after exit. No live Hyphae service, configuration or memory is used.

Normal, queue and uncertainty scenarios use unchanged production copies. A
separate deadline copy shortens `LIFETIME_MS` from 140,000 to 200 ms against a
one-second fixture response; another copy uses an absolute nonexistent interpreter
to test FailedToStart. The report identifies both overrides. These tests do not
independently exercise SIGKILL escalation, simulate a kernel-unreapable child or
establish a total-process-memory bound. The two-second TERM/reap timers and
fail-closed slot handling also received source review against Quickshell/Qt.

`qmllint` reports missing `QProcess::ExitStatus` parameter metadata for `onExited`
in the Quickshell type information. The warning is retained, not suppressed;
native normal-exit and deadline-cleanup scenarios verify the signal at runtime.

Stdout admission/retention limits do not bound Qt's transient pipe-read or UTF-8
decode allocations or overall process memory. Stderr has zero client retention;
its read event causes termination. See [the exact protocol and process
limits](PROTOCOL.md). The configured CI matrix runs the Python checks on
3.11.15 and 3.13.9 and the JavaScript checks with pinned Node 24.16.0; hosted
results for this revision are a separate release check.

## 0.2.0 native baseline

The 0.2.0 client and the independent server were checked on 12 September 2026.
The receipts below record the tested production-file hashes, server source,
real socket results and actual Omarchy desktop environment for that version.
They are retained unchanged. Each release's `package.json` separately binds its
clean source commit and archive members.

| Surface | Result | Receipt |
| --- | --- | --- |
| Python client | 14 real-socket tests passed | [Client](validation/client.json) |
| Independent server | 3 handler tests and 2 real-engine socket tests passed | [Server](validation/server.json) |
| Full Hyphae workspace | 1,788 passed; 1 hosted-only test skipped locally | [Server](validation/server.json) |
| Omarchy 4.0.3 / Quickshell 0.3.1 / Qt 6.11.2 | Official manifest validation and QML lint passed without diagnostics | [Desktop](validation/desktop.json) |
| Direct requests using the panel credential | 9 boundary and memory behavior checks passed | [Boundary](validation/boundary.json) |
| Service outage, restart and client removal | 5 lifecycle checks passed | [Lifecycle](validation/lifecycle.json) |

### Authority and memory behavior

The independent server is implemented in
[Hyphae PR #285](https://github.com/Hyphae-Research-Foundation/hyphae/pull/285),
at reviewed source `a9f7a84d4cf69c8ae371ff484ab82a341a62f13f`.
All 33 applicable hosted checks passed before its merge into `main`; the two
publication-only jobs were skipped as expected. The existing macOS semantic
migration test needed a retry on that same commit after a directory-lock
failure. The native aggregate was then rerun against the successful CI result.
The locally skipped SDK test belongs to the passing hosted client-conformance
job, which installs the required TypeScript toolchain.

Real requests sent directly to the dedicated server socket with a valid panel
credential could not reach operator commands, generic native requests, agent
configuration, restore, install, service activation or proxy operations.
Unknown arguments and client-selected paths were rejected. The checks also
covered wrong credentials, bounded input, existing socket/configuration
preservation and server-assigned provenance.

Memory writes, project isolation, explicit global sharing, lexical and hybrid
queries, complete proof verification, forgetting and verified backup creation
worked with the actual engine. Eleven independently installed configuration
and credential files retained their hashes through denied requests, permitted
memory operations and client removal.

### Desktop and lifecycle

The installed 0.2.0 production files matched the hashes in the desktop receipt. The
three tabs were exercised in the actual Omarchy VM: manual capture, Enter
search, verified queries, forgetting confirmation, Escape cancellation/close,
global sharing and backup creation. Screenshots use synthetic test memories:

- [Connection status](screenshots/01-memory-status.png)
- [Memory search](screenshots/02-memory-search.png)
- [Verified query](screenshots/03-query-verification.png)
- [Backups](screenshots/04-memory-backups.png)

Stopping the independently managed listener reports an unavailable service
without replacing its credential. Restarting it reuses that credential.
Disabling and removing the plugin with Omarchy's official commands leaves
the data, listener, memory/embedding services and independent files intact.
Reinstalling the client reconnects to the same service.

## Scope

The recorded 0.2.0 desktop environment is Linux x86_64 on Omarchy 4.0.3. The service API
and credential enforce the operation boundary; they do not sandbox arbitrary
code already running with the same user's filesystem permissions. Native
proofs retain their 16-MiB bound and establish retrieval at a snapshot, not
the truth of remembered statements. Marketplace listing requires the
maintainer's fresh review of the submitted commit.
