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
  property string project: "personal"
  property string memoryLayer: "work"
  property var confirmation: null
  property string newKind: "fact"
  property bool shareGlobally: false
  readonly property var memoryState: backend ? backend.status : ({})
  readonly property var fonts: Style.font
  readonly property color secondaryColor: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.74)
  readonly property bool working: backend ? backend.busy : false
  readonly property bool connected: !!memoryState.connected
  readonly property var projectOptions: backend ? backend.projects.map(function(p) { return { value:p.id, label:p.label || p.id } }) : []

  function call(operation, args) { if (backend) backend.request(operation, args || {}) }
  function search(prove) {
    if (!project || !connected) return
    call(query.text.trim() ? "recall" : "list", { project:project, layer:memoryLayer, query:query.text.trim(),
      mode:memoryState.semantic_enabled ? "hybrid" : "lexical", prove:prove, limit:64 })
  }
  function reload() {
    call("status")
    if (connected) { call("projects"); if (section === 2) call("backups") }
  }
  function expiry(value) {
    return value ? "Expires " + Qt.formatDateTime(new Date(Number(value) / 1000), "dd MMM yyyy") : "No automatic expiry"
  }
  function backupLabel(value) {
    var match = /^agent-memory-(\d+)$/.exec(value)
    return match ? Qt.formatDateTime(new Date(Number(match[1]) / 1000), "dd MMM yyyy · hh:mm:ss") : value
  }
  function dismissOrCancel() { if (confirmation) confirmation = null; else close() }
  onOpenedChanged: if (opened) reload()
  onSectionChanged: {
    if (section === 1) search(false)
    if (section === 2 && connected) call("backups")
  }
  Connections {
    target: root.backend
    function onCompleted(operation, result) {
      if (operation === "status" && result.connected && root.opened && !root.backend.projects.length) root.call("projects")
      if (operation === "store") { if (result.scope === "global") root.memoryLayer = "all"; memoryText.text = ""; query.text = ""; root.search(false); root.call("projects"); root.call("status") }
      if (operation === "forget") { root.search(false); root.call("status") }
      if (operation === "backup") root.call("backups")
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
      blocked: query.activeFocus || memoryText.activeFocus || projectName.activeFocus || projects.popupOpen || layers.popupOpen || kinds.popupOpen
      onCloseRequested: root.dismissOrCancel()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(14)
        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(12)
          Text { text:"◈"; textFormat:Text.PlainText; color:Color.accent; font.pixelSize:Style.space(32) }
          ColumnLayout {
            spacing: Style.space(3)
            Layout.fillWidth: true
            Text { text:"Hyphae Memory"; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.subtitle; font.bold:true }
            Text { text:"Your local memory, within reach."; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
          }
          Text { text:root.connected ? "LOCAL · CONNECTED" : "OFFLINE"; color:root.connected ? Color.accent : Color.muted; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
          Ui.PanelActionButton { iconText:"↻"; tooltipText:"Refresh"; focusable:true; enabled:!root.working; onClicked:root.reload() }
        }
        RowLayout {
          Layout.fillWidth: true
          Repeater {
            model: ["Status", "Memories", "Backups"]
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
              Text { text:root.connected ? "Memory is available" : "Connect your Hyphae service"; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.subtitle; font.bold:true }
              Text {
                Layout.fillWidth: true
                text: root.connected ? "Search and save memories, verify a query, or create a backup. Your Hyphae service keeps the data on this computer."
                  : "Prepare the memory service and its dedicated desktop connection in Hyphae, then refresh this panel."
                wrapMode: Text.WordWrap
                color: root.secondaryColor
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body
              }
              RowLayout {
                visible: root.connected
                Layout.fillWidth: true
                spacing: Style.space(32)
                ColumnLayout {
                  Layout.fillWidth: true
                  Text { text:String(root.memoryState.memories || 0); color:Color.foreground; font.family:root.fonts.family; font.pixelSize:Style.space(38) }
                  Text { text:"Stored records"; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                }
                ColumnLayout {
                  Layout.fillWidth: true
                  Text { text:root.memoryState.semantic_enabled ? "Hybrid enabled" : "Lexical"; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.subtitle }
                  Text { text:"Search mode provided by Hyphae"; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                }
              }
              Rectangle { Layout.fillWidth:true; implicitHeight:1; color:Color.muted }
              Text { text:"Desktop connection"; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.body; font.bold:true }
              Text {
                Layout.fillWidth: true
                text: "Hyphae provides a dedicated connection file at ~/.config/hyphae-panel/client.json. Service setup and administration are managed independently."
                wrapMode: Text.WordWrap
                color: root.secondaryColor
                font.family: root.fonts.family
                font.pixelSize: root.fonts.bodySmall
              }
              RowLayout {
                Ui.Button { text:"Refresh connection"; focusable:true; bordered:true; enabled:!root.working; onClicked:root.reload() }
                Ui.Button { text:"Open setup guide"; focusable:true; bordered:true; onClicked:Qt.openUrlExternally("https://github.com/Hyphae-Research-Foundation/hyphae/blob/main/docs/memory-panel.md") }
              }
            }
            ColumnLayout {
              visible: root.section === 1
              enabled: root.connected
              Layout.fillWidth: true
              spacing: Style.space(12)
              RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(4)
                  Text { text:"Project"; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                  Ui.TextField {
                    id: projectName
                    Layout.fillWidth: true
                    text: root.project
                    maximumLength: 256
                    placeholderText: "Project name"
                    onEditingFinished: { if (text.trim()) root.project = text.trim() }
                    onAccepted: { root.project = text.trim(); root.search(false) }
                    Keys.onEscapePressed: root.dismissOrCancel()
                  }
                }
                Ui.Dropdown { id:projects; label:"Known projects"; Layout.preferredWidth:Style.space(190); value:root.project; options:root.projectOptions; onChanged:function(value) { root.project=value; root.search(false) } }
                Ui.Dropdown { id:layers; label:"Layer"; Layout.preferredWidth:Style.space(120); value:root.memoryLayer; options:[{value:"work",label:"Work"},{value:"personal",label:"Personal"},{value:"journal",label:"Journal"},{value:"all",label:"All layers"}]; onChanged:function(value) { root.memoryLayer=value; root.search(false) } }
              }
              Ui.TextField { id:query; Layout.fillWidth:true; placeholderText:"Search your memories…"; maximumLength:4096; onAccepted:root.search(false); Keys.onEscapePressed:root.dismissOrCancel() }
              RowLayout {
                Ui.Button { text:"Search"; focusable:true; bordered:true; enabled:!root.working && !!root.project; onClicked:root.search(false) }
                Ui.Button { text:"Verify query"; focusable:true; bordered:true; enabled:!root.working && !!root.project; onClicked:root.search(true) }
              }
              Text { Layout.fillWidth:true; text:"Project memories and explicitly shared global memories."; color:root.secondaryColor; wrapMode:Text.WordWrap; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
              ColumnLayout {
                visible: root.memoryLayer !== "journal"
                Layout.fillWidth: true
                spacing: Style.space(8)
                Ui.TextField { id:memoryText; Layout.fillWidth:true; placeholderText:"Add a fact, decision or constraint…"; maximumLength:2000; Keys.onEscapePressed:root.dismissOrCancel() }
                RowLayout {
                  Ui.Dropdown { id:kinds; Layout.preferredWidth:Style.space(155); value:root.newKind; options:[{value:"fact",label:"Fact"},{value:"decision",label:"Decision"},{value:"constraint",label:"Constraint"}]; onChanged:function(value) { root.newKind=value } }
                  Ui.ToggleSwitch { checked:root.shareGlobally; busy:root.working; onToggled:root.shareGlobally=!root.shareGlobally }
                  Text { Layout.fillWidth:true; text:"Share across projects"; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                  Ui.Button { text:"Remember"; focusable:true; bordered:true; enabled:!root.working && !!root.project && !!memoryText.text.trim(); onClicked:root.call("store", {project:root.project,text:memoryText.text.trim(),kind:root.newKind,layer:root.shareGlobally ? "personal" : root.memoryLayer === "personal" ? "personal" : "work",scope:root.shareGlobally ? "global" : "project"}) }
                }
              }
              Text { Layout.fillWidth:true; visible:root.backend && root.backend.proof !== null; text:root.backend && root.backend.proof && root.backend.proof.status === "verified" ? "✓ Hyphae verified this query at its saved snapshot" : ""; color:Color.accent; wrapMode:Text.WordWrap; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
              Repeater {
                model: root.backend ? root.backend.memories : []
                Rectangle {
                  id: memoryCard
                  required property var modelData
                  Layout.fillWidth: true
                  implicitHeight: cardContents.implicitHeight + Style.space(20)
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.025)
                  ColumnLayout {
                    id: cardContents
                    anchors { left:parent.left; right:parent.right; top:parent.top; margins:Style.space(10) }
                    spacing: Style.space(7)
                    Text { Layout.fillWidth:true; text:memoryCard.modelData.text || ""; textFormat:Text.PlainText; wrapMode:Text.Wrap; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.bodySmall }
                    Text { Layout.fillWidth:true; text:[memoryCard.modelData.kind || "memory",memoryCard.modelData.layer || "work",memoryCard.modelData.harness || "",memoryCard.modelData.model || ""].filter(function(value) { return value !== "" }).join(" · "); textFormat:Text.PlainText; wrapMode:Text.Wrap; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                    RowLayout {
                      Text { Layout.fillWidth:true; text:root.expiry(memoryCard.modelData.expires_at_micros); color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
                      Ui.Button { text:"Forget"; foreground:Color.urgent; focusable:true; enabled:!root.working; onClicked:root.confirmation={operation:"forget",label:"Forget this memory?",arguments:{project:memoryCard.modelData.scope === "global" ? "_global" : root.project,id:memoryCard.modelData.id}} }
                    }
                  }
                }
              }
              Text { visible:root.backend && root.backend.memories.length === 0; text:"No memories to show for this query."; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.bodySmall }
            }
            ColumnLayout {
              visible: root.section === 2
              Layout.fillWidth: true
              spacing: Style.space(14)
              Ui.Button { text:"Create verified backup"; focusable:true; bordered:true; enabled:root.connected && !root.working; onClicked:root.call("backup") }
              Text { Layout.fillWidth:true; text:"Backups are created and retained by Hyphae. Restore them through the independently managed application."; wrapMode:Text.WordWrap; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.bodySmall }
              Repeater {
                model: root.backend ? root.backend.backups : []
                Text {
                  required property var modelData
                  Layout.fillWidth: true
                  text: root.backupLabel(modelData.label)
                  textFormat: Text.PlainText
                  color: Color.foreground
                  font.family: root.fonts.family
                  font.pixelSize: root.fonts.bodySmall
                }
              }
            }
          }
        }
        ColumnLayout {
          visible: root.confirmation !== null
          Layout.fillWidth: true
          Text { Layout.fillWidth:true; text:root.confirmation ? root.confirmation.label : ""; color:Color.foreground; font.family:root.fonts.family; font.pixelSize:root.fonts.body }
          RowLayout {
            Ui.Button { text:"Confirm"; foreground:Color.urgent; bordered:true; focusable:true; enabled:!root.working; onClicked: { var action=root.confirmation; root.confirmation=null; root.call(action.operation,action.arguments) } }
            Ui.Button { text:"Cancel"; focusable:true; onClicked:root.confirmation=null }
          }
        }
        Text { Layout.fillWidth:true; text:root.working ? "Working…" : root.backend ? root.backend.message : ""; textFormat:Text.PlainText; wrapMode:Text.WordWrap; color:root.secondaryColor; font.family:root.fonts.family; font.pixelSize:root.fonts.caption }
      }
    }
  }
}
