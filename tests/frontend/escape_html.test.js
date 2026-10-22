const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'app.js'), 'utf8');
const context = { document: { querySelectorAll: () => [] } };
vm.runInNewContext(source, context);
const { escapeHtml } = context;

test('escapes HTML special characters and quotes', () => {
  assert.strictEqual(
    escapeHtml(`<a href="x">Tom's & co</a>`),
    '&lt;a href=&quot;x&quot;&gt;Tom&#39;s &amp; co&lt;/a&gt;'
  );
});

test('null and undefined become empty string', () => {
  assert.strictEqual(escapeHtml(null), '');
  assert.strictEqual(escapeHtml(undefined), '');
});

test('numbers are kept, including zero', () => {
  assert.strictEqual(escapeHtml(0), '0');
  assert.strictEqual(escapeHtml(7), '7');
});
