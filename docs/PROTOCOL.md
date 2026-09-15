# Dedicated memory connection

The normative upstream contract is `native-memory-panel-v1.json` in Hyphae's
`contracts/` directory. The included copy is `contracts/memory-panel-v1.json`.
The server implementation and ADR 0030 describe the authority boundary.

Hyphae provisions a dedicated Unix socket and OS-random 256-bit credential.
The token uses the `hypm1_` domain and is separate from native/operator keys.
The connection file schema is `hyphae-memory-panel-connection-v1` and contains
only `schema`, `endpoint` and `token`. The client rejects generic credentials,
symlinks, non-socket endpoints and files or directories accessible by other users.

One UTF-8 JSON request is sent per connection, followed by write EOF. The
service sends one JSON response and closes the connection. Requests identify
schema `hyphae-memory-panel-v1`, a numeric `id`, the dedicated token, an
operation and its arguments. The Python client supplies the token; it stays
out of the QML state and displayed errors.

| Operation | Authority |
| --- | --- |
| `status`, `projects` | Read memory status and project identifiers |
| `recall`, `list` | Read scoped memories; `prove` requests verified retrieval |
| `store`, `forget` | Explicit memory data changes |
| `backups`, `backup` | List and create backups with destinations chosen by the service |

The server authenticates the request, checks this operation set and validates
operation-specific arguments before dispatch. Its dispatcher calls memory
functions directly. It provides no generic operator, command, path, native API
or proxy endpoint. The client receives neither a native socket nor an operator
credential. Service lifecycle, runtime/model installation, capture configuration,
agent integrations and restore operations are outside this interface.

A verified query returns proof, witness and anchor digests after the service
performs offline semantic verification. Generated temporary proof files are
removed; their local paths are omitted from the response. Independent proof
export is available through the separate Hyphae application.

The interface bounds input to 64 KiB, responses to 1 MiB and concurrent service
requests to four. Input, operation and output deadlines are 5, 120 and 5 seconds.
The native complete-proof limit remains 16 MiB. Oversized, malformed, unauthorized
and unsupported requests return bounded errors.

## Client process boundary in 0.2.1

`BoundedMemoryProcess.qml` launches the helper directly as
`/usr/bin/python3 -I -S -B /absolute/path/to/scripts/bridge.py`, without a shell
or interpreter lookup through `PATH`. The bridge uses only the Python standard
library. Isolated mode excludes the script/current directory from normal import
search and ignores Python environment settings; `-S` skips site initialization
and `-B` prevents bytecode writes.

The inherited process environment is cleared. The only entries are
`LC_ALL=C.UTF-8` and the nonempty `HOME`, `XDG_CONFIG_HOME` and
`HYPHAE_MEMORY_PANEL_CONFIG` values supplied by the session. These path values
must be absolute, contain no NUL and fit the client's 4,096-character limit.
An omitted `HOME` lets Python resolve the account's home directory. No `PATH`,
display, DBus, loader or `PYTHON*` variables are forwarded.

| Client boundary | Limit or behavior |
| --- | --- |
| QML request packet | 60 KiB of UTF-8, including the framing newline |
| Bridge stdin and authenticated service request | 64 KiB each |
| Service response read by the bridge | 1 MiB |
| Bridge stdout | Compact ASCII JSON, at most 2 MiB before one framing newline |
| QML retained stdout | At most 2 MiB plus that newline, admitted ASCII only |
| Stdout admission accounting | 4 MiB total; each chunk is charged its ASCII length plus three bytes before retention |
| Stderr retention | Zero; any stderr read event aborts the request |

ASCII escaping preserves Unicode values through JSON decoding. The Python
emitter checks the final encoded body before writing anything to stdout; an
encoding failure or overflow becomes a small, sanitized error. The QML reader
checks the remaining admission and retained-text budgets before concatenation.
The three-byte charge per accepted chunk conservatively accounts for a leading
UTF-8 BOM that Qt may remove. Non-ASCII decoded output is rejected. Fragmented
output can exhaust this conservative budget before reaching the retained-text
limit. Stderr is never retained, concatenated, logged or displayed by the client.

This accounting uses the empty-marker `SplitParser` fragment interface and
Qt's stateless UTF-8 conversion: [Qt 6.11.2 strips at most one leading BOM](https://github.com/qt/qtbase/blob/ef55f427f2c8b410d34f8a7681020a3000cf6866/src/corelib/text/qstringconverter.cpp#L847),
and [invalid or non-ASCII encodings cannot silently become ASCII](https://github.com/qt/qtbase/blob/ef55f427f2c8b410d34f8a7681020a3000cf6866/src/corelib/text/qstringconverter_p.h#L199).
An admitted fragment's original byte count is therefore no greater than its
ASCII length plus three. Recheck this assumption when upgrading the native stack.

These are **admission and retention bounds**. Qt reads and decodes each chunk
before the QML handler sees it. QML does not bound those transient pipe-read or
UTF-8 conversion allocations, or overall process memory. The separate 16-MiB
native proof limit does not enlarge this transport: the panel receives verified
proof digest metadata rather than the complete proof files.

## Deadlines and uncertain outcomes

The bridge has one 135-second socket-phase deadline, including connection
overhead around the service's 5/120/5-second deadlines. Receiving another chunk
does not restart it. QML starts a 140-second lifetime watchdog before process
creation, covering startup and stdin waiting as well as the request itself.

On a process fault or lifetime expiry, the client closes stdin, detaches both
output channels, clears retained data and sends SIGTERM. After two seconds it
sends SIGKILL if the same child is still running. A further two-second reap
watchdog reports a cleanup stall and holds the in-flight slot. An unreaped child
never permits another helper launch; the cleanup latch requires disabling and
re-enabling the plugin. Component destruction also requests child termination.
The [native fixture tests](VALIDATION.md) check normal exit/reaping, startup
failure, queue ordering and deadline-triggered TERM cleanup.

The client sends each request once. For `store`, `forget` and `backup`, it marks
transmission as possible before sending bytes. A later timeout, disconnection,
invalid acknowledgement or size-limit failure returns `outcome_unknown`:

> The result could not be confirmed. This change may have completed. Check
> current memories or backups before submitting it again.

The service can replace an oversized response after dispatch has completed, so
even a response-size error does not establish that a mutation failed. Killing
the helper does not confirm cancellation in the independently running service.
Pre-send rejection remains a definite failure, and valid native `unauthorized`
or `busy` rejections retain their meaning. Request IDs correlate responses;
they are not an idempotency or cancellation contract.

There is no automatic mutation retry. QML process-boundary faults discard
pending requests and pause background polling. Success messages are cleared on
failure, and drafts are preserved when success is unconfirmed. The client does
not infer mutation success from an unrelated status response. Process completion
is handled before releasing the slot for another request.

This separates the authority of the provided API and credential. Omarchy
plugins still execute as the local user; the interface is not an operating-system
sandbox against arbitrary code already running with that user's filesystem access.
