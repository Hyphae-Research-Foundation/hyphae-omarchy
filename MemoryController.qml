// SPDX-License-Identifier: Apache-2.0
import QtQuick
import Quickshell.Io

Item {
  id: root
  visible: false
  property bool busy: false
  property int nextId: 1
  property var status: ({ connected: false })
  property var memories: []
  property var projects: []
  property var backups: []
  property string error: ""
  property string errorOperation: ""
  property string message: ""
  property var proof: null
  property var activeRequest: ({})
  property var pending: []
  property bool panelOpen: false
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("scripts/bridge.py").toString().replace(/^file:\/\//, ""))
  readonly property var operations: ["status", "projects", "recall", "list", "store", "forget", "backups", "backup"]
  signal completed(string operation, var result)

  function request(operation, arguments) {
    if (operations.indexOf(operation) < 0) { error = "Unsupported memory operation."; return }
    if (pending.length >= 16) { error = "Too many pending requests. Please wait."; return }
    pending.push({ id: nextId++, schema: "hyphae-memory-panel-v1", operation: operation, arguments: arguments || {} })
    startNext()
  }
  function refresh() { request("status", {}) }
  function startNext() {
    if (busy || pending.length === 0) return
    activeRequest = pending.shift()
    busy = true
    if (["status", "projects", "backups"].indexOf(activeRequest.operation) < 0) { error = ""; errorOperation = "" }
    process.stdinEnabled = true
    process.running = true
  }
  function receive(value) {
    if (value.schema !== "hyphae-memory-panel-v1" || value.id !== activeRequest.id) {
      error = "The service returned an unsupported memory response."
      return
    }
    if (!value.ok) {
      if (activeRequest.operation === "status") status = { connected: false }
      errorOperation = activeRequest.operation
      error = value.error && value.error.message ? value.error.message : "The memory operation failed."
      return
    }
    var result = value.result || {}
    switch (activeRequest.operation) {
    case "status": status = result; if (result.connected && errorOperation === "status") { error = ""; errorOperation = "" }; break
    case "projects": projects = result.projects || []; break
    case "backups": backups = result.backups || []; break
    case "recall":
    case "list": memories = result.memories || []; proof = result.proof || null; break
    default: message = result.message || "Completed."; break
    }
    completed(activeRequest.operation, result)
  }
  function finishRequest() {
    try {
      if (reply.text.trim()) root.receive(JSON.parse(reply.text))
      else root.error = "The memory client did not return a response."
    } catch (e) { root.error = "The memory response could not be read." }
    root.busy = false
    Qt.callLater(root.startNext)
  }
  Process {
    id: process
    command: ["python3", root.helperPath]
    stdinEnabled: true
    onStarted: { write(JSON.stringify(root.activeRequest) + "\n"); stdinEnabled = false }
    stdout: StdioCollector { id: reply }
    stderr: StdioCollector {}
    onRunningChanged: if (!running && root.busy) Qt.callLater(root.finishRequest)
  }
  Timer {
    interval: root.panelOpen ? 15000 : 60000
    repeat: true
    running: true
    onTriggered: if (!root.busy) root.refresh()
  }
  Component.onCompleted: refresh()
}
