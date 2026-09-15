// SPDX-License-Identifier: Apache-2.0
.pragma library

var REQUEST_BYTES = 60 * 1024;
var STDOUT_BYTES = 4 * 1024 * 1024;
var STDOUT_CHARACTERS = 2 * 1024 * 1024 + 1;
var LIFETIME_MS = 140000;
var TERMINATE_GRACE_MS = 2000;
var REAP_GRACE_MS = 2000;

function absolutePath(value) {
  return typeof value === "string" && value.length > 0 && value.length <= 4096
    && value[0] === "/" && value.indexOf("\u0000") < 0;
}

function utf8Bytes(value) {
  var bytes = 0;
  for (var i = 0; i < value.length; ++i) {
    var c = value.charCodeAt(i);
    if (c < 0x80) bytes += 1;
    else if (c < 0x800) bytes += 2;
    else if (c >= 0xd800 && c <= 0xdbff && i + 1 < value.length
             && value.charCodeAt(i + 1) >= 0xdc00 && value.charCodeAt(i + 1) <= 0xdfff) {
      bytes += 4;
      ++i;
    } else bytes += 3;
    if (bytes > REQUEST_BYTES) return bytes;
  }
  return bytes;
}

function requestPacket(request) {
  var packet = JSON.stringify(request) + "\n";
  if (utf8Bytes(packet) > REQUEST_BYTES) throw new Error("request_limit");
  return packet;
}

function stdoutCharge(chunk, remaining) {
  if (typeof chunk !== "string" || !Number.isFinite(remaining) || remaining < 0) return -1;
  // Qt's UTF-8 conversion may remove one leading three-byte BOM per chunk.
  // The bridge emits ASCII JSON. Any other decoded character is rejected.
  // For an accepted chunk, length + 3 is a conservative RAW-byte upper bound,
  // including a discarded BOM. Check that bound BEFORE retaining/concatenating.
  var charge = chunk.length + 3;
  if (charge > remaining) return -1;
  for (var i = 0; i < chunk.length; ++i) {
    if (chunk.charCodeAt(i) > 0x7f) return -1;
  }
  return charge;
}

function isMutation(operation) {
  return operation === "store" || operation === "forget" || operation === "backup";
}

function errorMessage(code) {
  var messages = {
    connection_required: "Set up the dedicated Hyphae memory connection independently first.",
    unavailable: "The memory service is unavailable. Check it in Hyphae.",
    unauthorized: "The service rejected the dedicated memory credential.",
    invalid_request: "The memory request is invalid.",
    forbidden_operation: "This connection grants only memory data operations.",
    busy: "The memory service is busy. Try again shortly.",
    timeout: "The memory client exceeded its time limit.",
    limit_exceeded: "The memory request or response exceeds its size limit.",
    protocol_error: "The memory client returned an unsupported response.",
    startup: "The memory client could not start. Check the installed Python and plugin files.",
    environment: "The memory connection paths must be absolute filesystem paths.",
    stderr: "The memory client reported an unexpected process error.",
    process_exit: "The memory client exited without confirming the request.",
    cleanup: "The memory client has not stopped. Disable and re-enable the plugin before trying again.",
    outcome_unknown: "The result could not be confirmed. This change may have completed. Check current memories or backups before submitting it again."
  };
  return Object.prototype.hasOwnProperty.call(messages, code)
    ? messages[code] : "The memory operation could not be completed.";
}
