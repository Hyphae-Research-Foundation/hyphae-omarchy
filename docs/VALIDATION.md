# Validation of Hyphae Memory 0.2.2

## 0.2.2 path-identity and regression checks

The credential/socket boundary patch passed client, JavaScript, native
Quickshell, QML lint and official manifest checks on 16 September 2026. The
[path-binding receipt](validation/path-binding-0.2.2.json) records the commands,
environment and production hashes. The generated
[native report](validation/process-native-0.2.2.json) binds its five scenarios
to the current QML and bridge sources.

| Surface | Current result | Reproduce |
| --- | --- | --- |
| Python bridge | 44 tests passed on Python 3.12.14 and 3.14.7 | `/usr/bin/python3 -I -S -B -m unittest discover -s tests -p test_bridge.py -v` |
| Pure JavaScript process limits | 8 tests passed | `node tests/test_process_limits.cjs` |
| Official Omarchy manifest validation | Passed on staged 0.2.2 source | `omarchy plugin validate <staged-plugin>` |
| QML lint, Qt 6.11.2 / Quickshell 0.3.1 | Exit 0; one unchanged type-metadata warning described below | `/usr/lib/qt6/bin/qmllint -I /usr/lib/qt6/qml BoundedMemoryProcess.qml MemoryController.qml` |
| Native process lifecycle | 5 scenarios passed; no overlapping connections or remaining fixture children | [Native report](validation/process-native-0.2.2.json), `python3 tests/native_process_smoke.py` |

The 44 Python checks contain the 29 unmodified 0.2.1 tests, ten focused
path-binding tests and five preservation tests. The six original
counterexamples fail against exact release commit `ae68f24`: writable
credential/endpoint ancestors are accepted, a substituted credential is read,
a substituted socket receives the token, and an absent peer-credential check
fails open. All six pass against 0.2.2.

The added checks also cover a foreign-owned or pre-existing symbolic ancestor,
descriptor identity and idempotent release, and cleanup after successful and
pre-connect returns. Preservation fixtures confirm unchanged behavior under
root-owned sticky `/tmp`, an owner-owned `0755` configuration ancestor and
search-only components. Existing error codes, file contents, mutation
submission state, bounds and no-retry behavior remain unchanged.

The implementation opens each directory component relative to the preceding
held descriptor and opens the credential relative to the validated parent. It
inspects the socket there and connects through
`/proc/self/fd/<parent-fd>/<name>`, keeping that parent descriptor alive through
`connect()`. Linux `SO_PEERCRED` is mandatory before transmission. Tests verify
that ancestor replacement cannot redirect either use and that no held
descriptor survives the request.

The JavaScript checks cover UTF-8 request sizing, the 4-MiB stdout admission
budget before retention, its three-byte per-chunk BOM reserve, the separate
2-MiB-plus-newline retained ASCII bound, launch paths and mutation messages.
They exercise the pure policy functions.

The native tests run the current QML components and bridge on Omarchy 4.0.3,
Quickshell 0.3.1, Qt 6.11.2 and Python 3.14.7. They check Unicode through ASCII
JSON, startup plus two queued reads, an uncertain dummy write that discards the
queue, deadline-triggered TERM cleanup, and deferred failed-start cleanup.
Fixture child metadata confirms the absolute isolated interpreter and
allowlisted environment names. Completion/failure observations find the prior
children reaped; every private process group is empty after exit. No live
Hyphae service, configuration or memory is used.

Normal, queue and uncertainty scenarios use unchanged production copies. A
separate deadline copy shortens `LIFETIME_MS` from 140,000 to 200 ms against a
one-second fixture response; another copy uses an absolute nonexistent
interpreter to test FailedToStart. The report identifies both overrides.

`qmllint` reports missing `QProcess::ExitStatus` parameter metadata for
`onExited` in the Quickshell type information. The warning is retained, not
suppressed; native normal-exit and deadline-cleanup scenarios verify the signal
at runtime.

The descriptor binding pins the endpoint directory, not the final socket entry:
a same-UID process can replace that name between `lstat()` and `connect()`.
The immediate parent excludes every other UID, and the mandatory peer-UID check
occurs before token transmission. The same UID already has permission to read
the credential. The bound address also depends on Linux procfs and is rejected
if its encoded pathname exceeds 107 bytes.

The native checks do not independently exercise SIGKILL escalation, simulate a
kernel-unreapable child or establish a total-process-memory bound. Stdout
admission/retention limits do not bound Qt's transient pipe-read or UTF-8 decode
allocations or overall process memory. Stderr has zero client retention; its
read event causes termination. See [the exact protocol and process
limits](PROTOCOL.md). The configured CI matrix will separately run the Python
checks on 3.11.15 and 3.13.9 and JavaScript on pinned Node 24.16.0.

## 0.2.1 process-hardening evidence

The immutable [0.2.1 receipt](validation/process-boundary-0.2.1.json) and
[native report](validation/process-native-0.2.1.json) record the process
hardening tested at release commit `ae68f24` on 15 September 2026. Their bridge
hash intentionally identifies that release, not 0.2.2. The 0.2.2 native report
above reruns the same scenarios against the corrected bridge.

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
