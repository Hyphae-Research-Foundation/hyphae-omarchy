# Marketplace submission draft

Title: **[Plugin]: Hyphae Memory**

| Form field | Proposed value |
| --- | --- |
| Repository URL | `https://github.com/Hyphae-Research-Foundation/hyphae-omarchy` — proposed location; not yet published |
| Category | Developer Tools |
| Tags | AI, Bar, Quickshell |
| Suggested tag | Leave empty |

## Maintainer notes

Hyphae Memory adds a native bar widget and panel for local memory shared by
Claude Code, Codex, OpenCode, Pi and other MCP clients. It stores decisions,
facts, constraints and selected successful commands in a user-owned Hyphae
directory, with project isolation, pause controls, explicit global sharing,
offline query verification and verified backups.

The plugin is Apache-2.0 and targets Linux x86_64 on Omarchy 4.0.3. QML imports
the installed Omarchy/Quickshell components. Python 3.11+ installs the pinned
Hyphae runtime; the distribution archive includes that runtime for offline
installation. Runtime files and the optional BGE reference model are checked
against complete SHA-256 inventories. Memory works without the model. Optional
semantic search uses Hyphae's own local Candle component on the CPU.

Setup creates user services and private local credentials. Host connection
and writing tools are explicit panel actions; unrelated host configuration is
preserved, and edited managed entries require review before replacement or
removal. Codex hook review remains in Codex's `/hooks` interface. The plugin
does not index the home directory or synchronize memories to a cloud service.
Disabling the widget leaves memory available; removing the integration keeps
memories, models and backups. Destructive panel actions require confirmation.

The repository includes the source lock, unpublished Hyphae candidate bundle
and readable patch, test drivers, validation receipts and screenshots. This
candidate contains native memory changes beyond the published Hyphae 3.0.0
crates; the runtime must match its lock. See the README and validation report
for the installation process, tested scope and retrieval measurements.

Suggested preview: `docs/screenshots/01-memory-status.png`.

## Owner submission steps

Review the concrete archive, source changes, licensing and validation report.
Confirm the repository location and publish the reviewed repository and
runtime assets. Set the runtime lock's HTTPS URL to the published, matching
asset and rebuild the plugin package before submission; the digest and member
inventory must continue to identify the tested runtime.

The official form also asks the owner to attest to repository visibility,
permission to submit the code and preview, documented dependencies, consent
for configuration changes, and understanding the marketplace's listing
review. Those owner attestations have not been submitted by this draft.

Open the [official submission form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml)
using the fields above. The [publishing guide](https://plugins.omarchy.org/publish.html)
and form were checked on 2026-09-11. The marketplace validates the current
public commit before a maintainer approves the listing.
