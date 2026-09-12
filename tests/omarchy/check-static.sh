#!/bin/bash
set -euo pipefail
/omarchy/bin/omarchy-plugin-validate /plugin
mkdir -p /tmp/hyphae-qml-imports
ln -s /omarchy/shell /tmp/hyphae-qml-imports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/hyphae-qml-imports -I /omarchy/shell /plugin/BarWidget.qml /plugin/Panel.qml /plugin/MemoryController.qml
