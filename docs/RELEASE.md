# Hyphae Memory 0.2.2

This maintainer-review patch closes the credential/socket pathname boundary
reported for 0.2.1. It keeps the `hyphae-memory-panel-v1` interface and the same
memory-data authority. Runtime/service administration and external integrations
remain independently managed through Hyphae.

Every credential and endpoint directory component is opened from the filesystem
root with descriptor-relative `O_DIRECTORY | O_NOFOLLOW` traversal and checked
for safe ownership and write modes. The credential is opened relative to the
validated parent. The socket is inspected there and connected through the held
parent's `/proc/self/fd` identity. `SO_PEERCRED` is mandatory and checked before
the token is transmitted. Descriptors are released after connect and on every
failure path.

The bounded process behavior introduced in 0.2.1 remains unchanged. The helper
launches directly through `/usr/bin/python3 -I -S -B` with a
cleared environment: `LC_ALL=C.UTF-8` plus optional absolute `HOME`,
`XDG_CONFIG_HOME` and `HYPHAE_MEMORY_PANEL_CONFIG` paths. It does not select an
interpreter through `PATH` or load Python site initialization.

The process reader checks a 4-MiB conservative stdout admission budget before
retention, charging ASCII length plus three bytes per chunk for a BOM that Qt
may discard. Retained/emitted ASCII JSON is separately limited to 2 MiB plus
one newline. The Python emitter checks encoded size before writing; oversized
output becomes a small sanitized error. Stderr has zero client retention and
any read event aborts the request. These bounds do not cover Qt's transient
pipe-read/decode allocations or total process memory.

A 140-second lifetime watchdog covers startup and request handling. Termination
uses SIGTERM with a two-second grace, then SIGKILL and a two-second reap grace.
An unreaped helper holds its slot and blocks another launch. Mutating requests
whose result cannot be confirmed return `outcome_unknown`; the client never
automatically retries `store`, `forget` or `backup`. Check current records or
backups before resubmitting an uncertain change.

Validation passes 44 Python client tests, eight JavaScript limits tests, five
native Quickshell fixture scenarios and official Omarchy manifest validation.
The Python cases include all 29 original tests plus path substitution, unsafe
ancestor, peer identity, descriptor lifecycle and preservation checks. The
native cases cover Unicode, queue ordering, uncertain outcomes, deadline cleanup
and failed startup. The [validation record](VALIDATION.md) includes source
hashes, test-only overrides and the single QML lint type-metadata warning; the
native normal-exit tests pass. The unchanged 0.2.0 desktop receipts and 0.2.1
process receipt remain labeled with their original source hashes. Marketplace
listing still requires review of the final default-branch commit.

The versioned client archive is named `hyphae-memory-0.2.2.tar.gz`; a published
release pairs it with `package.json` and `SHA256SUMS`. The package receipt
inventories every source member. Omarchy, system Python and the separately
provisioned Hyphae service supply runtime dependencies. Node.js is needed only
for development/CI tests. Restart the desktop shell after updating so Qt loads
the new process components.

Complete native proofs retain their separate 16-MiB limit; the panel receives
verified digest metadata. Proof verification establishes retrieval at a
snapshot, not the factual correctness of remembered text. Backups are created
by the service; restoration remains an independent Hyphae operation.
