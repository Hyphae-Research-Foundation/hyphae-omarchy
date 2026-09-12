# Validation of Hyphae Memory 0.2.0

The client and the independent server were checked on 12 September 2026.
The receipts below record the tested production-file hashes, server source,
real socket results and actual Omarchy desktop environment. Release
`package.json` binds the final clean source commit and every archive member.

| Surface | Result | Receipt |
| --- | --- | --- |
| Python client | 14 real-socket tests passed | [Client](validation/client.json) |
| Independent server | 3 handler tests and 2 real-engine socket tests passed | [Server](validation/server.json) |
| Full Hyphae workspace | 1,788 passed; 1 hosted-only test skipped locally | [Server](validation/server.json) |
| Omarchy 4.0.3 / Quickshell 0.3.1 / Qt 6.11.2 | Official manifest validation and QML lint passed without diagnostics | [Desktop](validation/desktop.json) |
| Direct requests using the panel credential | 9 boundary and memory behavior checks passed | [Boundary](validation/boundary.json) |
| Service outage, restart and client removal | 5 lifecycle checks passed | [Lifecycle](validation/lifecycle.json) |

## Authority and memory behavior

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

## Desktop and lifecycle

The installed production files match the hashes in the desktop receipt. The
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

The validated desktop environment is Linux x86_64 on Omarchy 4.0.3. Python
client CI also exercises the supported 3.11 and 3.13 runtimes. The service API
and credential enforce the operation boundary; they do not sandbox arbitrary
code already running with the same user's filesystem permissions. Native
proofs retain their 16-MiB bound and establish retrieval at a snapshot, not
the truth of remembered statements. Marketplace listing requires the
maintainer's fresh review of the submitted commit.
