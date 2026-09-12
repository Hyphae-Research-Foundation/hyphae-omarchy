#!/bin/bash
set -u
QA_RUNTIME=$(mktemp -d)
export XDG_RUNTIME_DIR="$QA_RUNTIME"
export LIBGL_ALWAYS_SOFTWARE=1
WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=gles2 WLR_RENDERER_ALLOW_SOFTWARE=1 sway --unsupported-gpu --config /plugin/tests/omarchy/sway.conf >"$QA_RUNTIME/parent.log" 2>&1 &
QA_WESTON=$!
QA_HYPRLAND=""
trap '[[ -z $QA_HYPRLAND ]] || kill "$QA_HYPRLAND" 2>/dev/null; kill "$QA_WESTON" 2>/dev/null; wait 2>/dev/null' EXIT
for _ in {1..100}; do [[ ! -S $QA_RUNTIME/wayland-1 ]] || break; sleep 0.05; done
WAYLAND_DISPLAY=wayland-1 Hyprland --config /plugin/tests/omarchy/hyprland.lua >"$QA_RUNTIME/hypr.stdout" 2>&1 &
QA_HYPRLAND=$!
sleep 4
hyprctl instances -j || true
find "$QA_RUNTIME/hypr" -name hyprland.log -exec tail -60 {} \; 2>/dev/null
tail -65 "$QA_RUNTIME/hypr.stdout"
tail -25 "$QA_RUNTIME/parent.log"
