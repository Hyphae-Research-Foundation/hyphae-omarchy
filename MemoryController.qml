// SPDX-License-Identifier: Apache-2.0
import QtQuick
import Quickshell.Io

Item {
  id: root
  visible: false
  property bool busy: false
  property int nextId: 1
  property var status: ({ installed: false, initialized: false, service_active: false })
  property var memories: []
  property var projects: []
  property var agents: []
  property var backups: []
  property string error: ""
  property string message: ""
  property var proof: null
  property var activeRequest: ({})
  property var pending: []
  property bool panelOpen: false
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("scripts/bridge.py").toString().replace(/^file:\/\//, ""))
  signal completed(string operation, var result)

  function request(operation, arguments) {
    if (pending.length >= 16) { error = "Too many pending requests. Please wait."; return }
    pending.push({ id: nextId++, schema: "hyphae-omarchy-control-v1", operation: operation, arguments: arguments || {} })
    startNext()
  }

  function refresh() { request("status", {}) }

  function startNext() {
    if (busy || pending.length === 0) return
    activeRequest = pending.shift()
    busy = true
    // Periodic status and list refreshes must not hide an action failure.
    if (["status", "projects", "agents", "backups"].indexOf(activeRequest.operation) < 0)
      error = ""
    process.stdinEnabled = true
    process.running = true
  }

  function receive(value) {
    if (value.schema !== "hyphae-omarchy-control-v1" || value.id !== activeRequest.id) {
      error = "The installed runtime uses an unsupported control interface."
      return
    }
    if (!value.ok) {
      error = value.error && value.error.message ? value.error.message : "The operation could not be completed."
      if (value.error && value.error.code === "not_installed") status = { installed: false, initialized: false }
      return
    }
    var result = value.result || {}
    switch (activeRequest.operation) {
    case "status": status = result; break
    case "projects": projects = result.projects || []; break
    case "agents": agents = result.agents || []; break
    case "backups": backups = result.backups || []; break
    case "recall":
    case "list": memories = result.memories || []; proof = result.proof || null; break
    case "verify": proof = result; break
    default: message = result.message || "Completed."; break
    }
    completed(activeRequest.operation, result)
  }

  function finishRequest() {
      try {
        if (reply.text.trim()) root.receive(JSON.parse(reply.text))
        else root.error = "The memory service did not return a response."
      } catch (e) { root.error = "The memory service returned an invalid response." }
      root.busy = false
      Qt.callLater(root.startNext)
  }

  Process {
    id: process
    command: ["python3", root.helperPath]
    stdinEnabled: true
    onStarted: {
      write(JSON.stringify(root.activeRequest) + "\n")
      stdinEnabled = false
    }
    stdout: StdioCollector { id: reply }
    stderr: StdioCollector { id: failure }
    onRunningChanged: if (!running && root.busy) Qt.callLater(root.finishRequest)
  }

  Timer {
    interval: root.panelOpen ? 5000 : 30000
    repeat: true
    running: true
    onTriggered: if (!root.busy) root.refresh()
  }
  Component.onCompleted: refresh()
}
