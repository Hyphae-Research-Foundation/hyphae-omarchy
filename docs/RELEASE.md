# Hyphae Memory 0.2.0

This release provides the Omarchy desktop client for an independently managed
Hyphae memory service. It supports project and layer selection, explicit memory
capture and forgetting, scoped search, verified queries and backup creation.

The client uses a dedicated Unix socket and credential whose authority is
restricted by the service to the documented memory operations. Runtime/service
administration and external integrations are managed independently through Hyphae.
A Hyphae build providing `hyphae-memory-panel-v1` is required; follow the upstream
memory-panel guide linked in the README.

Download `hyphae-memory-0.2.0.tar.gz`, `package.json` and `SHA256SUMS` from this
release. Verify checksums before installing the client archive. The package
receipt inventories every source member. The archive contains the desktop client,
its protocol contract and documentation; dependencies are provided by Omarchy,
Python and the separate Hyphae installation.

The validation report describes client, server-boundary and actual Omarchy
checks. Native proof responses retain the 16-MiB limit. Proof verification
establishes retrieval at a snapshot, not factual correctness of remembered text.
Backups are created by the service; restore remains an independent Hyphae action.
