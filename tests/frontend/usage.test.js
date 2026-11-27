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

const appSrc = fs.readFileSync(path.join(dir, 'app.js'), 'utf8');

function run(apiResult) {
    const els = {};
    const el = id => (els[id] ||= { value: '', hidden: false, innerHTML: '', addEventListener() {} });
    const flashes = [];
    const ctx = { document: { querySelectorAll: () => [], getElementById: el }, localStorage: { getItem: () => 't' }, window: { location: {} },
        fetch: async () => { throw new Error('unused'); }, URLSearchParams };
    vm.runInNewContext(appSrc, ctx);
    ctx.api = async () => apiResult;
    ctx.showFlash = (m, t) => flashes.push([m, t]);
    vm.runInContext(src, ctx);
    return new Promise(r => setImmediate(() => r({ els, flashes })));
}

test('every rendered string field is escaped', async () => {
    const x = f => `<script>${f}</script>`;
    const sample = {
        from: '2026-11-01', to: '2026-11-27',
        rows: [{ day: x('day'), username: x('user'), network: x('net'), country: x('cc'), requests: x('req'), logins: x('lg'), failed_logins: x('fl'), blocked_logins: x('bl') }],
        summary: { users: [{ username: x('suser'), requests: x('sreq'), logins: x('slg'), active_days: x('sad') }], failed_logins: x('tfl'), blocked_logins: x('tbl') },
    };
    const { els } = await run(sample);
    const out = els['rows-body'].innerHTML + els['summary-body'].innerHTML + els['usage-totals'].innerHTML;
    assert.ok(!out.includes('<script>'));
    for (const k of ['day', 'user', 'net', 'cc', 'req', 'lg', 'fl', 'bl', 'suser', 'sreq', 'slg', 'sad', 'tfl', 'tbl']) {
        assert.ok(out.includes(`&lt;script&gt;${k}&lt;/script&gt;`), k);
    }
    assert.strictEqual(els['from'].value, '2026-11-01');
});

test('null response (401 redirect) does not flash an error', async () => {
    const { flashes } = await run(null);
    assert.deepStrictEqual(flashes, []);
});

test('credit line names the licence', () => {
    assert.ok(html.includes('https://creativecommons.org/licenses/by/4.0/'));
    assert.ok(html.includes('CC BY 4.0'));
});
