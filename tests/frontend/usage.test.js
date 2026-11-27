const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const dir = path.join(__dirname, '..', '..', 'frontend');
const src = fs.readFileSync(path.join(dir, 'usage.js'), 'utf8');
const html = fs.readFileSync(path.join(dir, 'usage.html'), 'utf8');

test('usage.js has no inline handlers and calls /usage with escapeHtml', () => {
    assert.ok(!src.includes('onclick'));
    assert.ok(src.includes('escapeHtml'));
    assert.ok(src.includes("'/usage'"));
    assert.ok(src.includes('addEventListener'));
});

test('usage.html has no inline script or handlers and has credit', () => {
    assert.ok(!/<script(?![^>]*src=)/.test(html));
    assert.ok(!/\son\w+=/.test(html));
    assert.ok(html.includes('https://db-ip.com'));
});

test('usernames are escaped when rendered', async () => {
    const els = {};
    const el = id => (els[id] ||= { value: '', hidden: false, innerHTML: '', addEventListener() {} });
    const sample = {
        from: '2026-11-01', to: '2026-11-27',
        rows: [{ day: '2026-11-27', username: '<script>x</script>', network: 'n', country: 'NL', requests: 1, logins: 0, failed_logins: 0, blocked_logins: 0 }],
        summary: { users: [{ username: '<script>x</script>', requests: 1, logins: 0, active_days: 1 }], failed_logins: 0, blocked_logins: 0 },
    };
    const escapeHtml = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const ctx = { document: { getElementById: el }, requireAuth: () => true, escapeHtml,
        api: async () => sample, showFlash() {}, URLSearchParams };
    vm.runInNewContext(src, ctx);
    await new Promise(r => setImmediate(r));
    assert.ok(!els['rows-body'].innerHTML.includes('<script>'));
    assert.ok(!els['summary-body'].innerHTML.includes('<script>'));
    assert.ok(els['rows-body'].innerHTML.includes('&lt;script&gt;'));
    assert.strictEqual(els['from'].value, '2026-11-01');
});
