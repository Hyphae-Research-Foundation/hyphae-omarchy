# Marketplace submission

Title: **[Plugin]: Hyphae Memory**

| Form field | Proposed value |
| --- | --- |
| Repository URL | `https://github.com/Hyphae-Research-Foundation/hyphae-omarchy` |
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

The repository includes a public Hyphae source lock, signed runtime provenance,
test drivers, validation receipts and screenshots. Agent Memory is integrated
in public Hyphae commit `8fe08dfce903d09e4e5f4b82ba02d3d28ec45191`; its native
protocol minor 7 operations are newer than the Hyphae 3.0.0 registry packages.
The plugin installs its exact verified runtime from the versioned HTTPS release
URL in `runtime.lock.json`. An offline archive is also provided. See the README,
[release notes](RELEASE.md) and [validation report](VALIDATION.md) for the
installation process, source provenance, tested scope and retrieval measurements.

Suggested preview: `docs/screenshots/01-memory-status.png`.

## Submission process

The [official submission form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml)
uses the fields above and requires confirmation of repository visibility,
installation and removal instructions, licensing and external dependencies,
permission to submit the plugin and preview, and consent for configuration
changes. The [publishing guide](https://plugins.omarchy.org/publish.html) and
form were checked on 2026-09-12.

Submit after the versioned downloads and public source installation have been
verified. Automated validation checks the current public commit; marketplace
maintainers decide whether to approve the listing. Listing approval does not
constitute a security review.
