# Develop the memory client

The repository contains QML presentation and a Python standard-library Unix
socket client. Prepare the separate Hyphae service using its own documentation.
The client requires Python 3.11+ and the installed Omarchy/Quickshell UI imports.

Run the client tests and package source with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q scripts tests
python3 scripts/package-plugin.py
```

The tests use actual temporary Unix sockets and private credential files.
They exercise request/response framing, missing/incorrect/insecure credentials,
symlink and non-socket preservation, wrong response identities, bounded output,
credential redaction, request limits, and rejection of operator requests.

The server's real-engine integration tests live in Hyphae. They send prohibited
requests directly to its socket, inspect preserved independent configuration,
and then exercise memory writes, reads, complete proof verification and backups.
Client filtering complements that server enforcement; it does not replace it.

For real desktop validation, install the packaged client in an Omarchy VM with
an independently provisioned service. Run the official manifest validator and
`qmllint` against the installed Omarchy imports. Inspect all three tabs; exercise
manual capture, Enter search, verified recall, Escape cancellation/close, global
sharing, backup creation, and offline/reconnected states. Compare the installed
production files and package inventory with the release source.

`package-plugin.py` records every regular source member's size and digest.
Release receipts must identify a clean, committed source tree. GitHub Actions
runs the client tests and packaging checks on Python 3.11 and 3.13. Publishing a
new version requires fresh desktop evidence and marketplace review of its exact
commit; the independently installed server has its own source and test record.
