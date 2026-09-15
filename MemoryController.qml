// SPDX-License-Identifier: Apache-2.0
import QtQuick
import "ProcessLimits.js" as Limits

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
  readonly property var operations: ["status", "projects", "recall", "list", "store", "forget", "backups", "backup"]
  signal completed(string operation, var result)

  function request(operation, args) {
    if (operations.indexOf(operation) < 0) { error = "Unsupported memory operation."; return; }
    if (pending.length >= 16) { error = "Too many pending requests. Please wait."; return; }
    var item = { id: nextId++, schema: "hyphae-memory-panel-v1", operation: operation, arguments: args || {} };
    try { item.packet = Limits.requestPacket(item); }
    catch (ignored) { errorOperation = operation; error = Limits.errorMessage("limit_exceeded"); return; }
    pending.push(item);
    startNext();
  }
  function refresh() { request("status", {}); }
  function startNext() {
    if (busy || processBoundary.busy || pending.length === 0) return;
    activeRequest = pending.shift();
    busy = true;
    if (["status", "projects", "backups"].indexOf(activeRequest.operation) < 0) {
      error = ""; errorOperation = ""; message = "";
    }
    if (activeRequest.operation === "recall" || activeRequest.operation === "list") proof = null;
    processBoundary.begin(activeRequest.packet);
  }
  function failRequest(code, possiblySubmitted) {
    if (!busy) return;
    if (possiblySubmitted && Limits.isMutation(activeRequest.operation)) code = "outcome_unknown";
    errorOperation = activeRequest.operation || "status";
    error = Limits.errorMessage(code);
    message = "";
    if (activeRequest.operation === "status") status = { connected: false };
    pending = []; // Dropped requests are never replayed after a transport fault.
  }
  function releaseRequest() {
    busy = false;
    activeRequest = ({});
    Qt.callLater(root.startNext);
  }
  function receive(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)
        || value.schema !== "hyphae-memory-panel-v1" || value.id !== activeRequest.id
        || typeof value.ok !== "boolean"
        || Object.keys(value).some(function(key) { return ["schema", "id", "ok", "result", "error"].indexOf(key) < 0; })
        || (value.ok && (!value.result || typeof value.result !== "object" || Array.isArray(value.result) || value.error !== undefined))) {
      processBoundary.faulted = true;
      failRequest("protocol_error", processBoundary.submitted);
      return;
    }
    if (!value.ok) {
      if (!value.error || typeof value.error !== "object" || Array.isArray(value.error)
          || typeof value.error.code !== "string") {
        processBoundary.faulted = true;
        failRequest("protocol_error", processBoundary.submitted); return;
      }
      if (value.error.code === "outcome_unknown") {
        processBoundary.faulted = true;
        failRequest("outcome_unknown", false); return;
      }
      if (activeRequest.operation === "status") status = { connected: false };
      errorOperation = activeRequest.operation;
      error = Limits.errorMessage(value.error && value.error.code ? value.error.code : "protocol_error");
      message = "";
      return;
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
  BoundedMemoryProcess {
    id: processBoundary
    onResponse: function(value) {
      root.receive(value);
      root.releaseRequest();
    }
    onFailed: function(code, possiblySubmitted) {
      root.failRequest(code, possiblySubmitted);
      root.releaseRequest();
    }
    onStalled: function(possiblySubmitted) {
      root.failRequest("cleanup", possiblySubmitted);
      // Keep the slot busy until the child actually exits; no retry or overlap.
    }
  }
  Timer {
    interval: root.panelOpen ? 15000 : 60000
    repeat: true
    running: !processBoundary.faulted
    onTriggered: if (!root.busy) root.refresh()
  }
  Component.onCompleted: refresh()
}
