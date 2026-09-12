# Hyphae Memory 0.1.0

This release targets Linux x86_64 on Omarchy 4.0.3. It provides the native bar
widget and panel, a pinned local runtime, project-scoped memory, optional local
semantics, verified recall and backups, and integration with Claude Code,
Codex, OpenCode and Pi.

The runtime source is public Hyphae commit
`8fe08dfce903d09e4e5f4b82ba02d3d28ec45191`. Its native protocol is minor 7;
the Hyphae 3.0.0 registry packages do not contain the Agent Memory additions.
Install the plugin's pinned runtime when using this release.

## Download and verify

Download from the [0.1.0 release](https://github.com/Hyphae-Research-Foundation/hyphae-omarchy/releases/tag/v0.1.0):

- `hyphae-memory-0.1.0.tar.gz`: complete plugin and runtime for offline installation.
- `hyphae-memory-0.1.0-linux-x86_64-8fe08dfce903.tar.gz`: the exact runtime used by source installations.
- `hyphae-memory-0.1.0-upstream-evidence.zip`: signed upstream artifacts, G8 receipts and verification data.
- `hyphae-memory-0.1.0.cdx.json`: combined runtime dependency inventory.
- `hyphae-memory-0.1.0-dependency-licenses.txt`: retained dependency license texts.
- `SHA256SUMS`: identities of the release files.

Verify the downloaded files with `sha256sum --check SHA256SUMS`. The installer
also verifies the complete runtime archive and every inventoried member before
activating either binary. A mismatch preserves the existing installation.

The full archive extracts into `org.hyphaeresearch.memory`; place that directory
under `~/.config/omarchy/plugins`, validate it and enable the widget. A source
installation retrieves the exact runtime through the public HTTPS URL in
`runtime.lock.json`. See the [README](../README.md) for setup and removal.

## Source and verification scope

The Hyphae CLI is the exact Linux binary from
[Release run 34699387730](https://github.com/Hyphae-Research-Foundation/hyphae/actions/runs/34699387730).
That run built commit `98792adde4bdb90eca0bee778e5b23a5c7ee804d`; its tree is
identical to the public merge above. The supplied lock preserves both identities
and the executable hash. All four upstream platform archives, 12 signatures
and 12 attestations were verified with the pinned upstream verifier.

[G8 run 34702899455](https://github.com/Hyphae-Research-Foundation/hyphae/actions/runs/34702899455)
closed all nine G8 requirements for the exact merge, using
[readiness run 34702184771](https://github.com/Hyphae-Research-Foundation/hyphae/actions/runs/34702184771).
G7 used authority mode. The closure and signed artifacts describe the upstream
native engine. The optional Candle worker is built from the same public source
and has its own model, runtime and Omarchy integration checks. The
[validation report](VALIDATION.md) records their results and limits.

The upstream signed artifact retains its original candidate identity and
workflow certificate. This Omarchy release does not rename or replace an
existing Hyphae registry release or its version tag.

## Known limits

The reference BGE model is English-oriented. The small ES/EN fixture is a
reproducible check, not a production quality guarantee. Proofs verify retrieval
against a snapshot and can include private retained data; they do not establish
that remembered statements are true. Forget/expiry does not securely erase old
versions or backups. Complete proof responses retain the native 16-MiB bound.

The optional embedding build retains the existing unmaintained `paste` macro
dependency through Candle and tokenizers (RUSTSEC-2024-0436). No advisory
exception was added. Its license and package identity remain in the dependency
inventory.

User services, local credentials and host configuration are created through
explicit setup actions. Removing the integration preserves memories, backups
and models. Edited managed host entries require review before replacement.
