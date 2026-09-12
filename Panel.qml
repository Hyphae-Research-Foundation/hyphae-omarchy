// SPDX-License-Identifier: Apache-2.0
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
  id: root
  moduleName: "org.hyphaeresearch.memory"
  manageIpc: false
  property Item anchorItem: null
  property var hostWidget: null
  property var backend: null
  property int section: 0
  property string project: ""
  property string memoryLayer: "work"
  property var confirmation: null
  property bool verifyAfterRecall: false
  property string newKind: "fact"
  property bool shareGlobally: false
  readonly property var memoryState: backend ? backend.status : ({})
  readonly property var fonts: Style.font
  readonly property color secondaryColor: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.74)
  readonly property bool working: backend ? backend.busy : false
  readonly property var projectOptions: backend ? backend.projects.map(function(p) { return { value: p.id, label: p.label || p.id } }) : []

  function call(operation, args) { if (backend) backend.request(operation, args || {}) }
  function search(prove) {
    if (!project) return
    verifyAfterRecall = prove
    call(query.text.trim() ? "recall" : "list", { project: project, layer: memoryLayer, query: query.text.trim(), prove: prove, limit: 64 })
  }
  function reload() {
    call("status")
    if (memoryState.initialized) { call("projects"); call("agents"); if (section === 3) call("backups") }
  }
  function expiry(value) {
    return value ? "Expires " + Qt.formatDateTime(new Date(Number(value) / 1000), "dd MMM yyyy") : "No automatic expiry"
  }
  function backupLabel(value) {
    var match = /^agent-memory-(\d+)$/.exec(value)
    return match ? Qt.formatDateTime(new Date(Number(match[1]) / 1000), "dd MMM yyyy · hh:mm:ss") : value
  }
  onOpenedChanged: if (opened) reload()
  onSectionChanged: {
    if (section === 1 && project) search(false)
    if (section === 2) call("agents")
    if (section === 3) call("backups")
  }

  Connections {
    target: root.backend
    function onCompleted(operation, result) {
      if (operation === "status" && result.initialized && root.opened) {
        if (!root.backend.projects.length) root.call("projects")
        if (!root.backend.agents.length) root.call("agents")
      }
      if (operation === "install_model" && result.model_dir) modelDirectory.text = result.model_dir
      if (operation === "projects" && !root.project && result.projects && result.projects.length) root.project = result.projects[0].id
      if ((operation === "recall" || operation === "list") && root.verifyAfterRecall && result.proof) {
        root.verifyAfterRecall = false
        root.call("verify", { proof: result.proof.proof_path, witness: result.proof.witness_path, anchor: result.proof.anchor_hex })
      }
      if (["setup", "service_start", "pause", "configure", "disconnect", "semantic", "install", "install_model", "remove"].indexOf(operation) >= 0) root.reload()
      if (operation === "forget") root.search(false)
      if (operation === "store") { memoryText.text = ""; query.text = ""; root.search(false); root.call("projects") }
      if (operation === "backup" || operation === "restore") { root.call("backups"); root.call("status") }
    }
  }

  Ui.KeyboardPanel {
    id: surface
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: fittedContentWidth(Style.space(640))
    contentHeight: fittedContentHeight(Style.space(610))

    Ui.PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      blocked: query.activeFocus || memoryText.activeFocus || modelDirectory.activeFocus || bundlePath.activeFocus || projects.popupOpen || layers.popupOpen || kinds.popupOpen
      onCloseRequested: {
        if (root.confirmation) root.confirmation = null
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }

      ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(14)

        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(12)
          Text {
            text: "◈"
            textFormat: Text.PlainText
            color: Color.accent
            font.pixelSize: Style.space(32)
          }
          ColumnLayout {
            spacing: Style.space(3)
            Layout.fillWidth: true
            Text { text: "Hyphae Memory"; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.subtitle; font.bold: true }
            Text { text: "Shared context. Kept on your computer."; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
          }
          Text {
            text: !root.memoryState.installed ? "SET UP" : root.memoryState.capture_paused ? "CAPTURE PAUSED" : root.memoryState.service_active ? "LOCAL · ACTIVE" : "OFFLINE"
            color: root.memoryState.service_active ? Color.accent : Color.muted
            font.family: root.fonts.family
            font.pixelSize: root.fonts.caption
          }
          Ui.PanelActionButton { iconText: "↻"; tooltipText: "Refresh"; focusable: true; enabled: !root.working; onClicked: root.reload() }
        }

        RowLayout {
          Layout.fillWidth: true
          Repeater {
            model: ["Status", "Memories", "Agents", "Maintenance"]
            Ui.Button {
              required property string modelData
              required property int index
              Layout.fillWidth: true
              text: modelData
              selected: root.section === index
              focusable: true
              onClicked: root.section = index
            }
          }
        }

        Text {
          Layout.fillWidth: true
          visible: root.backend && root.backend.error !== ""
          text: root.backend ? root.backend.error : ""
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: Color.urgent
          font.family: root.fonts.family
          font.pixelSize: root.fonts.bodySmall
        }

        Controls.ScrollView {
          Layout.fillWidth: true
          Layout.fillHeight: true
          clip: true
          contentWidth: availableWidth

          ColumnLayout {
            width: parent.width
            spacing: Style.space(18)

            ColumnLayout {
              visible: root.section === 0
              Layout.fillWidth: true
              spacing: Style.space(18)

              ColumnLayout {
                visible: !root.memoryState.installed || !root.memoryState.initialized
                Layout.fillWidth: true
                spacing: Style.space(10)
                Text { text: "Give your agents a shared memory"; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.subtitle; font.bold: true }
                Text {
                  Layout.fillWidth: true
                  text: "Keep decisions, constraints and useful commands across Claude Code, Codex, OpenCode and Pi. Choose which agents to connect after setup."
                  wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.body
                }
                Ui.TextField {
                  id: bundlePath
                  Layout.fillWidth: true
                  visible: !root.memoryState.installed
                  placeholderText: "Verified runtime bundle (optional local file)"
                  Keys.onEscapePressed: root.close()
                }
                Ui.Button {
                  text: root.memoryState.installed ? "Set up local memory" : "Install memory runtime"
                  focusable: true; bordered: true; enabled: !root.working
                  onClicked: root.memoryState.installed ? root.call("setup", { enable_service: true }) : root.call("install", { bundle: bundlePath.text.trim() })
                }
                Text {
                  Layout.fillWidth: true
                  text: "Setup creates a user service and a private local data directory. Removing the widget keeps your memories."
                  wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption
                }
              }

              ColumnLayout {
                visible: !!root.memoryState.initialized
                Layout.fillWidth: true
                spacing: Style.space(18)
                Ui.Button { visible: !root.memoryState.service_active || !!root.memoryState.runtime_activation_pending; text: root.memoryState.runtime_activation_pending ? "Activate installed runtime" : "Start memory service"; focusable: true; bordered: true; enabled: !root.working; onClicked: root.call("service_start") }
                RowLayout {
                  Layout.fillWidth: true
                  ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Automatic capture"; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body; font.bold: true }
                    Text { Layout.fillWidth: true; text: "Remember explicit decisions and useful results."; color: root.secondaryColor; wrapMode: Text.WordWrap; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                  }
                  Ui.ToggleSwitch { checked: !root.memoryState.capture_paused; busy: root.working; onToggled: root.call("pause", { paused: !root.memoryState.capture_paused }) }
                }
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(22)
                  Repeater {
                    model: [
                      { label: "Stored records", value: root.memoryState.memories || 0 },
                      { label: "Pending captures", value: root.memoryState.pending_captures || 0 },
                      { label: "Pending embeddings", value: root.memoryState.pending_embeddings || 0 }
                    ]
                    ColumnLayout {
                  id: metricEntry
                      required property var modelData
                      Layout.fillWidth: true
                      Layout.preferredWidth: 1
                      Layout.minimumWidth: 0
                      Text { text: String(metricEntry.modelData.value); color: Color.foreground; font.family: root.fonts.family; font.pixelSize: Style.space(30); font.bold: true }
                      Text { Layout.fillWidth: true; text: metricEntry.modelData.label; wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                    }
                  }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.secondaryColor; opacity: 0.25 }
                Text { text: "Local semantic search"; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body; font.bold: true }
                Text { Layout.fillWidth: true; text: "Find related memories with Hyphae embeddings. The basic memory works with this switched off."; color: root.secondaryColor; wrapMode: Text.WordWrap; font.family: root.fonts.family; font.pixelSize: root.fonts.bodySmall }
                Ui.TextField { id: modelDirectory; Layout.fillWidth: true; placeholderText: "Local model directory"; Keys.onEscapePressed: root.close() }
                RowLayout {
                  Ui.Button { text: "Install reference model"; focusable: true; bordered: true; enabled: !root.working; onClicked: root.call("install_model") }
                  Ui.Button { text: root.memoryState.semantic_enabled ? "Disable semantic search" : "Enable semantic search"; focusable: true; bordered: true; enabled: !root.working; onClicked: root.call("semantic", { enabled: !root.memoryState.semantic_enabled, model_dir: modelDirectory.text.trim() }) }
                }
                Text { Layout.fillWidth: true; text: root.memoryState.semantic_enabled ? (root.memoryState.semantic_ready ? "Embedding worker ready" : "Embeddings unavailable; lexical recall remains available") : "Semantic search is off"; wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
              }
            }

            ColumnLayout {
              visible: root.section === 1
              Layout.fillWidth: true
              spacing: Style.space(12)
              RowLayout {
                Layout.fillWidth: true
                Ui.Dropdown { id: projects; Layout.fillWidth: true; label: "Project"; value: root.project; options: root.projectOptions; onChanged: function(value) { root.project = value; root.search(false) } }
                Ui.Dropdown { id: layers; Layout.preferredWidth: Style.space(150); label: "Layer"; value: root.memoryLayer; options: [{ value:"work",label:"Work" },{value:"personal",label:"Personal"},{value:"journal",label:"Model journal"},{value:"all",label:"All layers"}]; onChanged: function(value) { root.memoryLayer = value; root.search(false) } }
              }
              Ui.TextField { id: query; Layout.fillWidth: true; placeholderText: "Search decisions, facts and commands…"; maximumLength: 4096; onAccepted: root.search(false); Keys.onEscapePressed: root.close() }
              RowLayout {
                Ui.Button { text: "Search"; focusable: true; bordered: true; enabled: !root.working && !!root.project; onClicked: root.search(false) }
                Ui.Button { text: "Verify query"; focusable: true; bordered: true; enabled: !root.working && !!root.project; onClicked: root.search(true) }
                Ui.Button {
                  readonly property bool paused: !!root.memoryState.paused_projects && root.memoryState.paused_projects.indexOf(root.project) >= 0
                  text: paused ? "Resume project capture" : "Pause project capture"
                  focusable: true; enabled: !root.working && !!root.project
                  onClicked: root.call("pause", { project: root.project, paused: !paused })
                }
              }
              Text {
                Layout.fillWidth: true
                text: !root.project ? "Projects appear after a connected agent starts a session." : root.memoryLayer === "journal" ? "Model-authored historical notes. Current instructions take precedence." : "Project memories and explicitly shared global memories."
                wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption
              }
              ColumnLayout {
                visible: !!root.project && root.memoryLayer !== "journal"
                Layout.fillWidth: true
                spacing: Style.space(8)
                Ui.TextField { id: memoryText; Layout.fillWidth: true; placeholderText: "Add a fact, decision or constraint…"; maximumLength: 2000; Keys.onEscapePressed: root.close() }
                RowLayout {
                  Layout.fillWidth: true
                  Ui.Dropdown { id: kinds; Layout.preferredWidth: Style.space(155); value: root.newKind; options: [{value:"fact",label:"Fact"},{value:"decision",label:"Decision"},{value:"constraint",label:"Constraint"}]; onChanged: function(value) { root.newKind = value } }
                  Ui.ToggleSwitch { checked: root.shareGlobally; busy: root.working; onToggled: root.shareGlobally = !root.shareGlobally }
                  Text { Layout.fillWidth: true; text: "Share across projects"; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                  Ui.Button { text: "Remember"; focusable: true; bordered: true; enabled: !root.working && !!memoryText.text.trim(); onClicked: root.call("store", {project:root.project,text:memoryText.text.trim(),kind:root.newKind,layer:root.shareGlobally ? "personal" : root.memoryLayer === "personal" ? "personal" : "work",scope:root.shareGlobally ? "global" : "project",harness:"omarchy-panel",model:"user"}) }
                }
              }
              Text {
                visible: root.backend && root.backend.proof !== null
                Layout.fillWidth: true
                text: root.backend && root.backend.proof && root.backend.proof.status === "verified" ? "✓ Query verified offline against its saved snapshot" : "Proof generated; verification pending"
                wrapMode: Text.WordWrap; color: Color.accent; font.family: root.fonts.family; font.pixelSize: root.fonts.bodySmall
              }
              Text { visible: root.backend && root.backend.memories.length === 0 && !!root.project && !root.working; text: "No matching live memories."; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.body }
              Repeater {
                model: root.backend ? root.backend.memories : []
                Rectangle {
                  id: memoryCard
                  required property var modelData
                  Layout.fillWidth: true
                  implicitHeight: memoryContent.implicitHeight + Style.space(24)
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.035)
                  radius: Style.cornerRadius
                  ColumnLayout {
                    id: memoryContent
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: Style.space(12) }
                    spacing: Style.space(8)
                    Text { Layout.fillWidth: true; text: memoryCard.modelData.text || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body }
                    Text { Layout.fillWidth: true; text: [memoryCard.modelData.kind, memoryCard.modelData.scope === "global" ? "global" : memoryCard.modelData.layer, memoryCard.modelData.harness || "unknown", memoryCard.modelData.model || "unknown"].join(" · "); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                    RowLayout {
                      Layout.fillWidth: true
                      Text { Layout.fillWidth: true; text: root.expiry(memoryCard.modelData.expires_at_micros); color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                      Ui.Button { text: "Forget"; foreground: Color.urgent; focusable: true; enabled: !root.working; onClicked: root.confirmation = { operation:"forget", label:"Forget this memory?", arguments:{project:memoryCard.modelData.scope === "global" ? "_global" : root.project,id:memoryCard.modelData.id} } }
                    }
                  }
                }
              }
            }

            ColumnLayout {
              visible: root.section === 2
              Layout.fillWidth: true
              spacing: Style.space(16)
              Text { Layout.fillWidth: true; text: "Connect installed agents to the same local memory. Writing tools are a separate permission from automatic capture."; wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.body }
              Repeater {
                model: root.backend ? root.backend.agents : []
                ColumnLayout {
                  id: agentEntry
                  required property var modelData
                  Layout.fillWidth: true
                  spacing: Style.space(8)
                  RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: agentEntry.modelData.name || agentEntry.modelData.id; textFormat: Text.PlainText; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body; font.bold: true }
                    Text { text: !agentEntry.modelData.installed ? "Not installed" : agentEntry.modelData.configured ? "Connected" : "Available"; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                  }
                  RowLayout {
                    Ui.Button { text: agentEntry.modelData.configured ? "Reconnect" : "Connect"; focusable: true; bordered: true; enabled: !root.working && agentEntry.modelData.installed && root.memoryState.initialized; onClicked: root.call("configure", { host:agentEntry.modelData.id,access:agentEntry.modelData.access || "read" }) }
                    Ui.Button { visible: agentEntry.modelData.configured; text: agentEntry.modelData.access === "write" ? "Use read-only tools" : "Allow writing tools"; focusable: true; enabled: !root.working; onClicked: root.call("configure", {host:agentEntry.modelData.id,access:agentEntry.modelData.access === "write" ? "read" : "write"}) }
                    Ui.Button { visible: agentEntry.modelData.configured; text: "Disconnect"; focusable: true; enabled: !root.working; onClicked: root.call("disconnect", {host:agentEntry.modelData.id}) }
                  }
                  Text { visible: !!agentEntry.modelData.next_step; Layout.fillWidth: true; text: agentEntry.modelData.next_step || ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
                  Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.secondaryColor; opacity: 0.2 }
                }
              }
            }

            ColumnLayout {
              visible: root.section === 3
              Layout.fillWidth: true
              spacing: Style.space(14)
              RowLayout {
                Ui.Button { text: "Check health"; focusable: true; bordered: true; enabled: !root.working && root.memoryState.initialized; onClicked: root.call("doctor") }
                Ui.Button { text: "Create verified backup"; focusable: true; bordered: true; enabled: !root.working && root.memoryState.initialized; onClicked: root.call("backup") }
              }
              Text { text: "Local backups"; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body; font.bold: true }
              Text { visible: root.backend && root.backend.backups.length === 0; text: "No backups yet."; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.bodySmall }
              Repeater {
                model: root.backend ? root.backend.backups : []
                RowLayout {
                  id: backupEntry
                  required property var modelData
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.backupLabel(backupEntry.modelData.label); textFormat: Text.PlainText; elide: Text.ElideMiddle; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.bodySmall }
                  Ui.Button { text: "Restore"; focusable: true; enabled: !root.working; onClicked: root.confirmation = {operation:"restore",label:"Restore this backup? Your current memory directory will be preserved.",arguments:{backup:backupEntry.modelData.path,confirm:true}} }
                }
              }
              Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.secondaryColor; opacity: 0.2 }
              Ui.Button { text: "Remove memory integration"; foreground: Color.urgent; focusable: true; enabled: !root.working && root.memoryState.initialized; onClicked: root.confirmation = {operation:"remove",label:"Disconnect agents and remove the user service? Memories and backups will remain.",arguments:{confirm:true}} }
            }
          }
        }

        ColumnLayout {
          visible: root.confirmation !== null
          Layout.fillWidth: true
          Text { Layout.fillWidth: true; text: root.confirmation ? root.confirmation.label : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Color.foreground; font.family: root.fonts.family; font.pixelSize: root.fonts.body }
          RowLayout {
            Ui.Button { text: "Confirm"; foreground: Color.urgent; bordered: true; focusable: true; enabled: !root.working; onClicked: { var action = root.confirmation; root.confirmation = null; root.call(action.operation, action.arguments) } }
            Ui.Button { text: "Cancel"; focusable: true; onClicked: root.confirmation = null }
          }
        }
        Text { Layout.fillWidth: true; text: root.working ? "Working…" : root.backend ? root.backend.message : ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: root.secondaryColor; font.family: root.fonts.family; font.pixelSize: root.fonts.caption }
      }
    }
  }
}
