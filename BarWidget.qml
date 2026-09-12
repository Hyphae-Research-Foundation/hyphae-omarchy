// SPDX-License-Identifier: Apache-2.0
import QtQuick
import qs.Ui as Ui

Ui.BarWidget {
  id: root
  moduleName: "org.hyphaeresearch.memory"
  readonly property var loadedPanel: panel.item
  readonly property bool opened: root.loadedPanel ? root.loadedPanel.opened : false
  readonly property bool popoutSwitchClosing: root.loadedPanel ? root.loadedPanel.popoutSwitchClosing : false
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function open() { if (root.loadedPanel) root.loadedPanel.open() }
  function close() { if (root.loadedPanel) root.loadedPanel.close() }
  function toggle() { if (root.loadedPanel) root.loadedPanel.toggle() }
  function closeForPopoutSwitch() { if (root.loadedPanel) root.loadedPanel.closeForPopoutSwitch() }
  function attach() {
    if (!panel.item) return
    panel.item.bar = root.bar
    panel.item.anchorItem = button
    panel.item.hostWidget = root
    panel.item.backend = backend
  }
  onBarChanged: attach()

  MemoryController { id: backend; panelOpen: root.opened }
  Loader {
    id: panel
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    onLoaded: { root.attach(); Qt.callLater(root.attach) }
  }
  Ui.WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.setting("showLabel", true) && !root.vertical ? "◈ Memory" : "◈"
    dimmed: !backend.status.service_active
    tooltipText: !backend.status.installed ? "Set up Hyphae Memory"
      : backend.status.capture_paused ? "Hyphae Memory · capture paused"
      : backend.status.service_active ? "Hyphae Memory · local and active" : "Hyphae Memory · service stopped"
    onPressed: function(buttonCode) { if (buttonCode === Qt.LeftButton) root.toggle() }
  }
}
