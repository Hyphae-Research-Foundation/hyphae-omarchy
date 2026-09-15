// SPDX-License-Identifier: Apache-2.0
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'ProcessLimits.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.replace(/^\.pragma library\s*$/m, ''), context);

function retain(chunks, limit = context.STDOUT_BYTES) {
  let text = '', remaining = limit;
  for (const chunk of chunks) {
    const charge = context.stdoutCharge(chunk, remaining);
    if (charge < 0 || chunk.length > context.STDOUT_CHARACTERS - text.length)
      return { text, rejected: true, remaining };
    remaining -= charge;
    text += chunk;
  }
  return { text, rejected: false, remaining };
}

test('Unicode request size follows UTF-8 bytes, including astral text', () => {
  for (const text of ['status', '大阪', 'café', '𠮷'])
    assert.equal(context.utf8Bytes(text), Buffer.byteLength(text, 'utf8'));
  assert.throws(() => context.requestPacket({text:'é'.repeat(32 * 1024)}), /request_limit/);
});

test('ASCII response carries Unicode without non-ASCII transport characters', () => {
  const text = '{"result":{"note":"\\u5927\\u962a"}}\n';
  const result = retain([text.slice(0, 8), text.slice(8)]);
  assert.equal(result.rejected, false);
  assert.equal(JSON.parse(result.text).result.note, '大阪');
});

test('budget is checked before retaining the next chunk', () => {
  const result = retain(['abc', 'def'], 11);
  assert.equal(result.rejected, true);
  assert.equal(result.text, 'abc');
  assert.equal(result.remaining, 5);
});

test('non-ASCII decoded output is rejected without concatenation', () => {
  for (const chunk of ['é', '\ufffd', '\ufeff', '𠮷']) {
    const result = retain(['ok', chunk]);
    assert.equal(result.rejected, true);
    assert.equal(result.text, 'ok');
  }
});

test('every accepted chunk reserves room for a stripped leading UTF-8 BOM', () => {
  const decoder = new TextDecoder('utf-8');
  const raw = [Buffer.from('\ufeffabc'), Buffer.from('\ufeff'), Buffer.from('def')];
  let accounted = 0;
  for (const bytes of raw) {
    const text = decoder.decode(bytes);
    const charge = context.stdoutCharge(text, 100);
    assert.ok(charge >= bytes.length);
    accounted += charge;
  }
  assert.ok(accounted >= raw.reduce((n,b) => n+b.length,0));
  assert.equal(retain(['', '', '', ''], 9).rejected, true);
});

test('retained-text limit remains separate from conservative raw accounting', () => {
  const result = retain(['a'.repeat(context.STDOUT_CHARACTERS), 'b']);
  assert.equal(result.rejected, true);
  assert.equal(result.text.length, context.STDOUT_CHARACTERS);
});

test('only explicit memory mutations require outcome reconciliation', () => {
  for (const op of ['store', 'forget', 'backup']) assert.equal(context.isMutation(op), true);
  for (const op of ['status', 'projects', 'recall', 'list', 'backups']) assert.equal(context.isMutation(op), false);
  assert.match(context.errorMessage('outcome_unknown'), /may have completed/);
});

test('launch paths reject relative and NUL-containing values', () => {
  assert.equal(context.absolutePath('/home/user/.config'), true);
  for (const value of ['', 'relative/path', '/tmp/\u0000bad', null])
    assert.equal(context.absolutePath(value), false);
});
