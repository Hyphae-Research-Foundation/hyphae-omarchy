#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
export XDG_RUNTIME_DIR
XDG_RUNTIME_DIR=$(mktemp -d)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
export QT_QUICK_BACKEND=software
export OMARCHY_PATH=/omarchy
export PATH="/omarchy/bin:$PATH"
export HYPHAE_OMARCHY_BINARY=/uninstalled-hyphae
mkdir -p "$XDG_CONFIG_HOME/omarchy/plugins" /artifacts
cp -a /plugin "$XDG_CONFIG_HOME/omarchy/plugins/org.hyphaeresearch.memory"
python3 - <<'PY'
import json, os
from pathlib import Path
config = {"version":1, "idle":{"screensaver":86400,"lock":86400},
          "bar":{"position":"top","transparent":False,"layout":{
              "left":[],"center":[],"right":[{"id":"org.hyphaeresearch.memory"}]}}, "plugins":[]}
Path(os.environ["XDG_CONFIG_HOME"], "omarchy/shell.json").write_text(json.dumps(config))
PY
WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman sway --unsupported-gpu --config /plugin/tests/omarchy/sway.conf >/artifacts/compositor.log 2>&1 &
QA_COMPOSITOR=$!
QA_SHELL=""
trap '[[ -z $QA_SHELL ]] || kill "$QA_SHELL" 2>/dev/null; kill "$QA_COMPOSITOR" 2>/dev/null; wait 2>/dev/null' EXIT
for _ in {1..100}; do [[ ! -S $XDG_RUNTIME_DIR/wayland-1 ]] || break; sleep 0.05; done
export WAYLAND_DISPLAY=wayland-1
quickshell -p /omarchy/shell/shell.qml >/artifacts/shell.log 2>&1 &
QA_SHELL=$!
for _ in {1..100}; do
  if quickshell -p /omarchy/shell/shell.qml ipc call shell ping >/dev/null 2>&1; then break; fi
  sleep 0.1
done
quickshell -p /omarchy/shell/shell.qml ipc call shell listPlugins >/artifacts/plugins.json
for _ in {1..100}; do
  if jq -e 'any(.[]; .id == "org.hyphaeresearch.memory" and .enabled)' /artifacts/plugins.json >/dev/null; then break; fi
  sleep 0.1
  quickshell -p /omarchy/shell/shell.qml ipc call shell listPlugins >/artifacts/plugins.json
done
quickshell -p /omarchy/shell/shell.qml ipc call shell summon org.hyphaeresearch.memory '{}'
sleep 2
grim -o HEADLESS-1 /artifacts/setup.png
quickshell -p /omarchy/shell/shell.qml ipc call shell debugBarGeometry >/artifacts/bar-geometry.json
python3 - <<'PY'
import json
from pathlib import Path
plugins = json.loads(Path('/artifacts/plugins.json').read_text())
assert any(p['id'] == 'org.hyphaeresearch.memory' and p['enabled'] for p in plugins), plugins
log = Path('/artifacts/shell.log').read_text()
assert 'Type BarWidget unavailable' not in log and 'Type Panel unavailable' not in log, log
print('Quattro loaded and opened the installed Hyphae Memory plugin.')
PY
