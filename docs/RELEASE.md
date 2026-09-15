# Hyphae Memory 0.2.1

This maintainer-review patch hardens the local helper process used by the
Omarchy memory client. It keeps the `hyphae-memory-panel-v1` interface and the
same memory-data authority. Runtime/service administration and external
integrations remain independently managed through Hyphae.

The helper now launches directly through `/usr/bin/python3 -I -S -B` with a
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

Validation passes 29 Python client tests, eight JavaScript limits tests, five
native Quickshell fixture scenarios and official Omarchy manifest validation.
The native cases cover Unicode, queue ordering, uncertain outcomes, deadline
cleanup and failed startup. The [validation record](VALIDATION.md) includes
source hashes, test-only overrides and the single QML lint type-metadata warning;
the native normal-exit tests pass. The unchanged 0.2.0 desktop receipts are
labeled as historical evidence. Marketplace listing still requires review of
the final default-branch commit.

The versioned client archive is named `hyphae-memory-0.2.1.tar.gz`; a published
release pairs it with `package.json` and `SHA256SUMS`. The package receipt
inventories every source member. Omarchy, system Python and the separately
provisioned Hyphae service supply runtime dependencies. Node.js is needed only
for development/CI tests. Restart the desktop shell after updating so Qt loads
the new process components.

Complete native proofs retain their separate 16-MiB limit; the panel receives
verified digest metadata. Proof verification establishes retrieval at a
snapshot, not the factual correctness of remembered text. Backups are created
by the service; restoration remains an independent Hyphae operation.
