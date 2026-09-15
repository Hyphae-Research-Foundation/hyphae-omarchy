# Hyphae Memory for Omarchy

A native Omarchy panel for an independently managed local Hyphae memory service.
Search and save memories, verify queries at their recorded snapshot, and create
verified backups. Project scopes and explicitly shared global memories stay
visible in the panel.

Version 0.2.1 is a desktop client for the dedicated `hyphae-memory-panel-v1`
interface. The service enforces its memory-only authority through a separate
Unix socket and credential. This patch hardens helper startup, retained output
and process cleanup. See the native tests and their scope in the
[validation record](docs/VALIDATION.md).

![Hyphae Memory on Omarchy](preview.png)

## Install

Use Omarchy 4.0.3 or newer on Linux with Python 3.11+ at `/usr/bin/python3`:

```bash
omarchy plugin add https://github.com/Hyphae-Research-Foundation/hyphae-omarchy.git
omarchy plugin enable org.hyphaeresearch.memory
```

After updating the plugin, restart the desktop shell with
`omarchy restart shell` so Qt loads the changed process components.

For offline installation, use a published client archive from the
[releases page](https://github.com/Hyphae-Research-Foundation/hyphae-omarchy/releases).
Extract it into `~/.config/omarchy/plugins`, validate the extracted directory
with `omarchy plugin validate`, then enable its widget.

## Connect to Hyphae

Prepare Hyphae and its dedicated desktop connection independently using the
[Hyphae memory-panel guide](https://github.com/Hyphae-Research-Foundation/hyphae/blob/main/docs/memory-panel.md).
A build providing the version-1 memory-panel interface is required. Older
Hyphae 3.0.0 registry packages predate this interface.

Automatic agent capture uses the Hyphae executable configured in each agent.
Use a runtime containing
[Hyphae PR #287](https://github.com/Hyphae-Research-Foundation/hyphae/pull/287)
(merge `8992f91754e0e55f5329d770bc29197d90513f00` or later). It fixes safe memory
notes discarded when other parts of a response contain paths or identifiers.
Update and activate the runtime through the independently managed Hyphae
installation, then complete any hook review requested by the agent. Updating
this desktop client alone does not replace the agents' executable.

The client reads `~/.config/hyphae-panel/client.json` (respecting
`XDG_CONFIG_HOME`). `HYPHAE_MEMORY_PANEL_CONFIG` can select another connection
file. Hyphae creates the file with its dedicated endpoint and credential; keep
it private. The file, socket and their parent directories must belong to the
current user and exclude access by other users. Refresh the panel after the
service becomes available.

The helper runs through the absolute system interpreter with `-I -S -B` and a
cleared environment. It receives only `LC_ALL=C.UTF-8` and any configured,
absolute `HOME`, `XDG_CONFIG_HOME` and `HYPHAE_MEMORY_PANEL_CONFIG` paths.
The client bounds retained ASCII output, retains no stderr, and uses process
lifetime and cleanup watchdogs. [Exact limits and their scope](docs/PROTOCOL.md)
include the Qt read/decode allocations that QML cannot bound.

The plugin's connection grants only memory data, query/proof and backup
operations. Hyphae runtime installation, service administration, model setup
and external tool integrations belong to the independently managed application.
See the [protocol and authority boundary](docs/PROTOCOL.md).

## Use the panel

**Status** shows the connection, record count and search mode provided by
Hyphae. **Memories** lets you select or enter a project, search by layer, save
a fact/decision/constraint, and confirm forgetting a memory. **Share across
projects** explicitly creates global memory. Enter submits a query; Escape
cancels a confirmation or closes the panel.

**Verify query** asks Hyphae to generate and verify the complete memory proof
at the saved snapshot. The panel displays its verification result. A proof
establishes retrieval at that snapshot; it does not establish the truth of a
remembered statement. Native proof responses retain their 16-MiB limit.

**Backups** lists and creates backups for this dedicated interface. Hyphae
keeps them under its memory backup directory's `panel` subdirectory. Restoring
backups and administering the service are separate Hyphae operations.

If a write result cannot be confirmed, the panel reports that the change may
have completed. Check the current memories or backups before submitting it
again. The client never automatically retries `store`, `forget` or `backup`.
A helper that cannot be reaped blocks further launches; follow the panel's
cleanup message before trying again.

## Remove

```bash
omarchy plugin disable org.hyphaeresearch.memory
omarchy plugin remove org.hyphaeresearch.memory
```

Removing the client preserves the independently installed Hyphae service,
memories, models, credentials and backups. Manage those resources in Hyphae.

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node tests/test_process_limits.cjs
python3 scripts/package-plugin.py
```

See [development](docs/DEVELOPMENT.md), [validation](docs/VALIDATION.md), and
[release notes](docs/RELEASE.md). The source is Apache-2.0; [NOTICE](NOTICE)
identifies the independent components.
