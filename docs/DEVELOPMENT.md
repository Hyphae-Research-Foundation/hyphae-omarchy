# Develop the memory client

The repository contains QML presentation, a pure JavaScript limits library and
a Python standard-library Unix socket client. Prepare the separate Hyphae
service using its own documentation. The installed client requires Python
3.11+ at `/usr/bin/python3` and the Omarchy/Quickshell UI imports. Node.js is a
development/CI test dependency; the installed widget does not run Node.

Run the client tests and package source with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node tests/test_process_limits.cjs
python3 -m compileall -q scripts tests
python3 scripts/package-plugin.py
```

The tests use actual temporary Unix sockets and private credential files.
They exercise request/response framing, missing/incorrect/insecure credentials,
symlink and non-socket preservation, wrong response identities, bounded output,
credential redaction, request limits, and rejection of operator requests.
The 0.2.1 coverage also starts the real bridge with
`/usr/bin/python3 -I -S -B`, a minimal explicit environment and a normal temporary
socket fixture. It checks Unicode round-tripping through ASCII JSON, final
encoded stdout bounds, sanitized overflow, the 135-second socket deadline and
uncertain mutation outcomes with one send and no reconnect/retry. Fault cases
use bounded unit mocks and small fixtures.

The Node tests evaluate `ProcessLimits.js` with Node's built-in test/VM modules;
there is no npm dependency installation. They cover UTF-8 request sizing,
pre-retention stdout admission, the per-chunk BOM allowance, the separate
retained-ASCII limit, mutation classification and absolute launch paths. Qt
process signals, timers, channel detachment and OS reaping require separate
native validation. See [the protocol](PROTOCOL.md) for the transient Qt
read/decode allocations outside these QML bounds.

The server's real-engine integration tests live in Hyphae. They send prohibited
requests directly to its socket, inspect preserved independent configuration,
and then exercise memory writes, reads, complete proof verification and backups.
Client filtering complements that server enforcement; it does not replace it.

For real desktop validation, install the packaged client in an Omarchy VM with
an independently provisioned service. Run the official manifest validator and
`qmllint` against the installed Omarchy imports. Inspect all three tabs; exercise
manual capture, Enter search, verified recall, Escape cancellation/close, global
sharing, backup creation, and offline/reconnected states. Compare the installed
production files and package inventory with the release source. For 0.2.1,
validate normal isolated-helper startup and completion, controlled process
failure, channel cleanup, the 140-second lifetime followed by the two-second
TERM and two-second reap grace periods, and the no-overlap behavior when a child
has not been reaped. Confirm uncertain writes are not replayed.

On a Linux host with Quickshell installed, reproduce the isolated native checks:

```bash
/usr/bin/python3 -I -S -B tests/native_process_smoke.py --report target/native-process-smoke.json
```

The five scenarios use private temporary sockets and dummy responses. Normal
responses, queued operations and uncertainty use unchanged production copies.
The deadline case shortens only its copied lifetime to 200 ms; the startup-failure
case uses an absolute nonexistent interpreter in a separate copy. The report
records every override and source hash, minimal environment names, callback
reaping observations and remaining child checks. It preserves diagnostics.
These cases do not simulate an unkillable kernel process or exercise SIGKILL
escalation separately. See the [validation record](VALIDATION.md).

`package-plugin.py` records every regular source member's size and digest.
Release receipts must identify a clean, committed source tree. GitHub Actions
runs the client tests and packaging checks on Python 3.11.15 and 3.13.9, and the
JavaScript suite on Node 24.16.0. Actions are pinned to complete commit hashes;
the Node setup uses the pin already recorded by upstream Hyphae. The subprocess
test deliberately uses the runner's `/usr/bin/python3` independently of the
matrix interpreter. Staging includes Git-visible regular sources, including
`BoundedMemoryProcess.qml`, `ProcessLimits.js` and the test files. Publishing a
new version requires fresh desktop evidence and marketplace review of its exact
commit; the independently installed server has its own source and test record.
