# Build and validate the candidate

Use Linux x86_64, Python 3.11 or newer, Node 26.7.0, and the Rust 1.96.0
toolchain. Commands below run from the plugin repository. Memory operations,
capture policy, migrations, native contracts and host adapters belong upstream
in Hyphae; the plugin owns QML presentation and artifact installation.

## Reconstruct and check Hyphae

```bash
python3 scripts/prepare-upstream.py
python3 scripts/verify-upstream.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The reconstruction helper fetches the exact public base, verifies the local
Git bundle against `source.lock.json`, and checks out the unpublished candidate.
It preserves an existing checkout that differs. A readable, binary-capable
patch is retained in `upstream/`. Keep the candidate in `.upstream/hyphae`;
temporary directories are unsuitable as the only copy of source changes.

After changing Hyphae, make a local candidate commit and run
`python3 scripts/lock-upstream.py` to refresh the bundle, patch and lock. Review
those artifacts before rebuilding and validating the new candidate.

The verifier records the source commit, selected checks, outcomes and complete
logs in `target/validation/upstream/`. It covers formatting, clippy, the Rust
workspace, rustdoc, the embedding component, generated models, Python and
TypeScript, the explicitly ignored cross-SDK wire fixture, live client and
JavaScript adapter conformance, architecture boundaries, documentation
examples and upstream packaging tests. `--only NAME ...` performs a selected
subset and identifies that scope in its receipt.

Native responses are bounded to 16 MiB, including proof and witness data.
The daemon regression exercises a value that fits the product budget but
exceeds the encoded response bound, and checks that the client receives a
terminal error and can reuse the connection.

## Build and exercise the runtime

```bash
python3 scripts/build-runtime.py --source .upstream/hyphae
python3 -m venv target/contract-tools
target/contract-tools/bin/pip install -r tests/contracts.requirements.txt
target/contract-tools/bin/python scripts/check-runtime.py \
  --binary target/native/x86_64-unknown-linux-gnu/release/hyphae \
  --embed-binary target/embed/x86_64-unknown-linux-gnu/release/hyphae-embed \
  --model-dir target/models/bge-small-en-v1.5 \
  --contract-dir .upstream/hyphae/contracts/json-schema \
  --output target/validation/runtime-release.json
target/contract-tools/bin/python scripts/contracts.py \
  --contract-dir .upstream/hyphae/contracts/json-schema \
  --embed-binary target/embed/x86_64-unknown-linux-gnu/release/hyphae-embed \
  --model-dir target/models/bge-small-en-v1.5 \
  --output target/validation/contracts-release.json
```

Prepare the model directory with the three exact files in `models.lock.json`,
or copy the model installed through the panel. Omit both model arguments to
run the lexical runtime checks without downloading a model. Schema validation
is optional for the runtime checker; `jsonschema` is a development dependency
and is not needed by the installed plugin.

The build requires a clean source checkout at the pinned candidate revision,
uses locked Cargo dependencies, remaps source paths, inventories every runtime
member and writes `runtime.lock.json`. Both binaries are built from that
source. Archive timestamps and file ownership are normalized; cross-machine
bit-for-bit compiler reproducibility has not been established.

## Real host clients

`tests/hosts/package-lock.json` fixes the complete test dependency graph.
Install it with `npm ci --ignore-scripts --prefix tests/hosts`, then explicitly
run the native distribution installers with
`npm rebuild --prefix tests/hosts --ignore-scripts=false @anthropic-ai/claude-code opencode-ai`.
Build the QA image with:

```bash
podman build -t localhost/hyphae-omarchy-qa:quattro-20260911 tests/omarchy
python3 scripts/check-hosts.py \
  --binary target/native/x86_64-unknown-linux-gnu/release/hyphae
```

The container uses private profiles, synthetic records and no network. The
wrapper copies an immutable binary before mounting it; do not mount a Cargo
output inode that another build may replace. The receipt records the binary
and container image digests. Host versions are Claude Code 2.1.251, Codex
0.153.4, OpenCode 1.18.27 and Pi 0.85.1.

These checks use official CLIs, Pi's real extension loader, OpenCode's native
plugin/config loader and their lifecycle interfaces. They do not start paid
model sessions. Codex retains its normal review of non-managed hooks through
[`/hooks`](https://developers.openai.com/codex/hooks/); its MCP registration
uses the [official CLI contract](https://developers.openai.com/codex/mcp/).

## Actual Omarchy VM

The disposable QEMU/KVM VM uses the official Omarchy 4.0.3 ISO pinned in
`tests/omarchy/image.lock.json`, a sparse 64-GiB virtual disk, four virtual
CPUs and 6 GiB RAM. Its disks, SSH identity and installer account stay under
the ignored, private `target/vm/` directory. It has no physical disk access.

```bash
python3 scripts/download-vm.py
python3 scripts/vm.py prepare
python3 scripts/vm.py start
python3 scripts/vm.py screen
```

Allow the seeded installer to complete and boot the installed disk. Use
`scripts/vm.py login` at the guest login screen, then `mount-share`. `screen`,
`key`, `click` and `type` drive the real guest desktop. `reference` retains the
installed Omarchy sources for inspection. Use package versions from
`pacman -Q`: this ISO's packaged source has an older alpha version text file.

```bash
python3 scripts/package-plugin.py
python3 scripts/check-vm.py --fresh
```

The VM check refuses to run outside the named disposable guest. It installs
the actual offline archive, verifies the official manifest, activates the
runtime, exercises systemd, hybrid proofs, pause/resume, worker outage,
SIGKILL restart, corrupt and valid restore, widget disable, integration removal
and reinstall. Existing synthetic agent connections are restored afterward.
`--fresh` first preserves the old synthetic data, configuration and state in
the guest's private QA directory. This keeps repeated diagnostic histories
from growing beyond the complete-proof wire limit in the main lifecycle case.
`--install-only` verifies a final package after documentation-only changes and
retains a separate receipt. Screenshots and keyboard/confirmation checks
complement the automated lifecycle evidence.

Run the official QML linter against the installed `/usr/share/omarchy/shell`
imports as well as the manifest validator; `tests/omarchy/check-static.sh`
shows the equivalent container command. A container compositor smoke check
does not replace the installed VM's Hyprland/systemd validation.

## Evaluation and delivery

```bash
python3 scripts/evaluate-memory.py \
  --binary target/native/x86_64-unknown-linux-gnu/release/hyphae \
  --embed-binary target/embed/x86_64-unknown-linux-gnu/release/hyphae-embed \
  --model-dir target/models/bge-small-en-v1.5 \
  --output target/validation/retrieval-release.json
python3 scripts/package-plugin.py
```

The ES/EN evaluation uses 12 annotated memories, 36 distractors and one
separate-project canary. It measures 24 distinct queries in two modes, with
one relevant record per query. Latency includes process startup and local
transport. See the validation report for observations and their limits.

GitHub Actions runs the plugin and native/SDK checks. Actual host loaders,
model evaluation, packaged installation and desktop behavior also require
the retained local QA evidence. Local checks do not confer the upstream
hosted G7/G8 release gates. Publication and marketplace submission remain
separate owner-reviewed actions.
