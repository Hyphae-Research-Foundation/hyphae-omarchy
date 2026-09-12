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

This separates the authority of the provided API and credential. Omarchy
plugins still execute as the local user; the interface is not an operating-system
sandbox against arbitrary code already running with that user's filesystem access.
