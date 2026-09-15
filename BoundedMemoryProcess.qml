// SPDX-License-Identifier: Apache-2.0
import QtQuick
import Quickshell
import Quickshell.Io
import "ProcessLimits.js" as Limits

Item {
  id: root
  visible: false
  readonly property bool busy: inFlight
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("scripts/bridge.py").toString().replace(/^file:\/\//, ""))
  property bool inFlight: false
  property bool faulted: false
  property bool stuck: false
  property bool shuttingDown: false
  property bool terminating: false
  property bool started: false
  property bool submitted: false
  property int childPid: 0
  property double startedAt: 0
  property int remainingBytes: Limits.STDOUT_BYTES
  property string inputPacket: ""
  property string responseText: ""
  property string stopCode: ""
  signal response(var value)
  signal failed(string code, bool possiblySubmitted)
  signal stalled(bool possiblySubmitted)

  function launchEnvironment() {
    var env = { LC_ALL: "C.UTF-8" };
    var names = ["HOME", "XDG_CONFIG_HOME", "HYPHAE_MEMORY_PANEL_CONFIG"];
    for (var i = 0; i < names.length; ++i) {
      var value = Quickshell.env(names[i]);
      if (value) {
        if (!Limits.absolutePath(value)) throw new Error("environment");
        env[names[i]] = value;
      }
    }
    return env;
  }

  function begin(packet) {
    if (inFlight || shuttingDown || stuck) { failed("cleanup", false); return; }
    var env;
    try {
      env = launchEnvironment();
      if (!Limits.absolutePath(helperPath)) throw new Error("environment");
    } catch (ignored) { faulted = true; failed("environment", false); return; }
    terminating = false;
    started = false;
    submitted = false;
    childPid = 0;
    stopCode = "";
    responseText = "";
    remainingBytes = Limits.STDOUT_BYTES;
    inputPacket = packet;
    faulted = false;
    inFlight = true;
    startedAt = Date.now();
    worker.environment = env;
    worker.stdout = outputParser;
    worker.stderr = errorParser;
    worker.stdinEnabled = true;
    // Cover process creation and interpreter startup, before onStarted/input.
    lifetime.restart();
    wallClock.restart();
    worker.running = true;
  }

  function detachChannels() {
    worker.stdinEnabled = false;
    worker.stdout = null;
    worker.stderr = null;
    responseText = "";
    inputPacket = "";
  }

  function signalChild(number) {
    // Process.signal passes its PID to kill(2); never allow PID zero or a
    // different process generation. The in-flight slot is held until reaping.
    var pid = worker.processId;
    if (!inFlight || !worker.running || pid <= 0 || (childPid > 0 && childPid !== pid)) return;
    childPid = pid;
    worker.signal(number);
  }

  function abort(code) {
    if (!inFlight || terminating || shuttingDown) return;
    terminating = true;
    faulted = true;
    stopCode = code;
    lifetime.stop();
    wallClock.stop();
    detachChannels();
    signalChild(15);
    terminateGrace.restart();
  }

  function ended(exitCode, exitStatus) {
    if (!inFlight || shuttingDown) return;
    lifetime.stop();
    wallClock.stop();
    terminateGrace.stop();
    reapGrace.stop();
    var text = responseText;
    var wasSubmitted = submitted;
    var code = stopCode;
    if (!code && (!started || exitCode !== 0 || exitStatus !== 0)) code = "process_exit";
    detachChannels();
    childPid = 0;
    // Normal exited is post-reap. FailedToStart reaches here only after a
    // deferred callback lets Qt finish its synchronous startup cleanup.
    inFlight = false;
    if (code) { faulted = true; failed(code, wasSubmitted); return; }
    var value;
    try { value = JSON.parse(text); }
    catch (ignored) { faulted = true; failed("protocol_error", wasSubmitted); return; }
    response(value);
  }

  SplitParser {
    id: outputParser
    splitMarker: ""
    onRead: function(chunk) {
      if (!root.inFlight || root.terminating || root.shuttingDown) return;
      var charge = Limits.stdoutCharge(chunk, root.remainingBytes);
      if (charge < 0 || chunk.length > Limits.STDOUT_CHARACTERS - root.responseText.length) {
        root.abort("limit_exceeded"); return;
      }
      root.remainingBytes -= charge;
      root.responseText += chunk;
    }
  }
  SplitParser {
    id: errorParser
    splitMarker: ""
    // stderr has a zero-retention budget. Even an empty decoded chunk is an
    // error event; never retain, concatenate, log or display producer output.
    onRead: function(chunk) { root.abort("stderr"); }
  }
  Process {
    id: worker
    command: ["/usr/bin/python3", "-I", "-S", "-B", root.helperPath]
    clearEnvironment: true
    stdinEnabled: false
    onStarted: {
      root.started = true;
      root.childPid = processId;
      if (root.terminating || root.shuttingDown) { root.signalChild(15); return; }
      root.submitted = true; // A partial write can already reach the helper.
      write(root.inputPacket);
      stdinEnabled = false;
      root.inputPacket = "";
    }
    onExited: function(exitCode, exitStatus) { root.ended(exitCode, exitStatus); }
    onRunningChanged: if (!running && root.inFlight && !root.started) {
      if (!root.stopCode) root.stopCode = "startup";
      Qt.callLater(function() {
        if (!worker.running && root.inFlight && !root.started && !root.shuttingDown)
          root.ended(-1, 1);
      });
    }
  }
  Timer {
    id: lifetime
    interval: Limits.LIFETIME_MS
    onTriggered: root.abort("timeout")
  }
  Timer {
    id: wallClock
    interval: 1000
    repeat: true
    onTriggered: {
      var elapsed = Date.now() - root.startedAt;
      if (elapsed < 0 || elapsed >= Limits.LIFETIME_MS) root.abort("timeout");
    }
  }
  Timer {
    id: terminateGrace
    interval: Limits.TERMINATE_GRACE_MS
    onTriggered: {
      if (!root.inFlight) return;
      root.signalChild(9);
      reapGrace.restart();
    }
  }
  Timer {
    id: reapGrace
    interval: Limits.REAP_GRACE_MS
    onTriggered: {
      if (!root.inFlight) return;
      root.stuck = true;
      root.faulted = true;
      root.stopCode = "cleanup";
      root.detachChannels();
      // Hold busy: no second process is allowed while the first is unreaped.
      root.stalled(root.submitted);
    }
  }
  Component.onDestruction: {
    root.shuttingDown = true;
    lifetime.stop(); wallClock.stop(); terminateGrace.stop(); reapGrace.stop();
    root.detachChannels();
    root.signalChild(9);
    // Quickshell's Process destructor also kills and owns asynchronous reaping.
  }
}
