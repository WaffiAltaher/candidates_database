const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'candidate.js'), 'utf8');

test('candidate.js handles every data-action', () => {
    for (const action of ['delete-customer', 'edit-interview', 'delete-interview', 'save-verdict', 'add-customer', 'add-interview']) {
        assert.ok(src.includes(`case '${action}':`), action);
        assert.ok(src.includes(`data-action="${action}"`), action);
    }
});

test('candidate.js has no inline onclick', () => {
    assert.ok(!src.includes('onclick'));
});
