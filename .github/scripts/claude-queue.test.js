// Tests for claude-queue.js against a mocked GitHub API.
// Run with: node --test .github/scripts/
//
// The mock can make the label-filtered issue list lag: after a label write it
// returns the state from before that write for the next `lag` list calls.
// issues.get is always current.

const test = require('node:test');
const assert = require('node:assert/strict');
const run = require('./claude-queue.js');

const H = 3600e3;
const NOW = Date.now();
const iso = (t) => new Date(t).toISOString();
const REPO = 'WaffiAltaher/candidates_database';
const ALL = ['claude:queued', 'claude:in-progress', 'claude:done', 'claude:failed'];

function issue(number, labels, createdAgo, state = 'open') {
  return { number, state, created_at: iso(NOW - createdAgo), labels: labels.map((name) => ({ name })) };
}

function pr(issueNumber, { state, createdAgo, closedAgo = null, merged = false, body, ref, repo = REPO }) {
  return {
    state,
    created_at: iso(NOW - createdAgo),
    closed_at: closedAgo === null ? null : iso(NOW - closedAgo),
    merged_at: merged ? iso(NOW - closedAgo) : null,
    body: body === undefined ? `Closes #${issueNumber}` : body,
    head: { ref: ref || `claude/issue-${issueNumber}`, repo: { full_name: repo } },
  };
}

// World state shared across runs, so back-to-back runs see each other's writes.
function world({ labels = ALL, issues = [], events = {}, pulls = [], lag = 0 } = {}) {
  const w = { labels: [...labels], issues: {}, events, pulls, lag, lagLeft: 0, snapshot: null, log: [] };
  for (const i of issues) w.issues[i.number] = i;
  return w;
}

const clone = (o) => JSON.parse(JSON.stringify(o));

function client(w) {
  const err = (status) => Object.assign(new Error(`HTTP ${status}`), { status });
  const beforeWrite = () => {
    if (w.lagLeft === 0) w.snapshot = clone(w.issues);
    w.lagLeft = w.lag;
  };
  const has = (i, name) => i.labels.some((l) => l.name === name);
  const api = {
    issues: {
      get: async ({ issue_number }) => {
        const i = w.issues[issue_number];
        if (!i) throw err(404);
        return { data: clone(i) };
      },
      getLabel: async ({ name }) => { if (!w.labels.includes(name)) throw err(404); },
      createLabel: async ({ name }) => { w.labels.push(name); w.log.push(`create ${name}`); },
      removeLabel: async ({ issue_number, name }) => {
        const i = w.issues[issue_number];
        if (!has(i, name)) throw err(404);
        beforeWrite();
        i.labels = i.labels.filter((l) => l.name !== name);
        w.log.push(`-${name} #${issue_number}`);
      },
      addLabels: async ({ issue_number, labels }) => {
        const i = w.issues[issue_number];
        if (has(i, 'claude:in-progress')) w.log.push(`VIOLATION +${labels} on in-progress #${issue_number}`);
        beforeWrite();
        for (const name of labels) i.labels.push({ name });
        w.log.push(`+${labels} #${issue_number}`);
        if (labels.includes('claude:in-progress')) {
          w.events[issue_number] = [{ event: 'labeled', label: { name: 'claude:in-progress' }, created_at: iso(Date.now()) }];
        }
      },
      listForRepo: async () => {},
      listEvents: async () => {},
      createComment: async ({ issue_number }) => { w.log.push(`comment #${issue_number}`); },
    },
    pulls: { list: async () => {} },
  };
  const github = {
    rest: api,
    paginate: async (fn, p) => {
      if (fn === api.issues.listForRepo) {
        let source = w.issues;
        if (w.lagLeft > 0) { w.lagLeft--; source = w.snapshot; }
        return Object.values(source)
          .filter((i) => (p.state === 'all' || i.state === p.state) && has(i, p.labels))
          .sort((a, b) => a.created_at.localeCompare(b.created_at));
      }
      if (fn === api.issues.listEvents) return w.events[p.issue_number] || [];
      if (fn === api.pulls.list) return w.pulls;
      throw new Error('unexpected paginate');
    },
  };
  return github;
}

async function runQueue(w, envs) {
  Object.assign(process.env, {
    ISSUE_NUMBER: '', ISSUE_AUTHOR: '', PR_BODY: '', PR_HEAD_REF: '', PR_HEAD_REPO: '', PR_MERGED: '',
  }, envs);
  const start = w.log.length;
  const core = { info: () => {}, warning: (m) => w.log.push(`warn ${m}`) };
  w.slept = 0;
  const sleep = async (ms) => { w.slept += ms; };
  await run({ github: client(w), context: { repo: { owner: 'WaffiAltaher', repo: 'candidates_database' } }, core, sleep });
  return w.log.slice(start);
}

const inProgressAt = (ago) => [{ event: 'labeled', label: { name: 'claude:in-progress' }, created_at: iso(NOW - ago) }];
const opened = (n, author = 'WaffiAltaher') => ({ QUEUE_MODE: 'intake', ISSUE_NUMBER: String(n), ISSUE_AUTHOR: author });
const closed = (n, merged, extra = {}) => ({
  QUEUE_MODE: 'pr-closed', PR_BODY: `Closes #${n}`, PR_HEAD_REF: `claude/issue-${n}`,
  PR_HEAD_REPO: REPO, PR_MERGED: String(merged), ...extra,
});

// Busy queue: #2 in progress for 1h (already closed by "Closes #2"), #3 and #4 queued, #3 older.
const busy = (opts = {}) => world({
  issues: [
    issue(2, ['claude:in-progress'], 9 * H, 'closed'),
    issue(4, ['claude:queued'], 5 * H),
    issue(3, ['claude:queued'], 6 * H),
  ],
  events: { 2: inProgressAt(H) },
  ...opts,
});

for (const lag of [0, 3]) {
  const tag = lag ? ` (list lags ${lag} calls)` : '';

  test(`intake while idle creates labels, queues and dispatches${tag}`, async () => {
    const w = world({ labels: [], issues: [issue(5, [], 0)], lag });
    assert.deepEqual(await runQueue(w, opened(5)), [
      ...ALL.map((l) => `create ${l}`),
      '+claude:queued #5', '-claude:queued #5', '+claude:in-progress #5',
    ]);
  });

  test(`intake while busy only queues${tag}`, async () => {
    const w = busy({ lag });
    w.issues[5] = issue(5, [], 0);
    assert.deepEqual(await runQueue(w, opened(5)), ['+claude:queued #5']);
  });

  test(`merge finishes once and dispatches the oldest queued issue${tag}`, async () => {
    const w = busy({ lag });
    w.pulls = [pr(2, { state: 'closed', createdAgo: 0.5 * H, closedAgo: 0, merged: true })];
    assert.deepEqual(await runQueue(w, closed(2, true)), [
      '-claude:in-progress #2', '+claude:done #2', '-claude:queued #3', '+claude:in-progress #3',
    ]);
  });

  test(`two issues opened back to back dispatch only the first${tag}`, async () => {
    const w = world({ issues: [issue(8, [], 2), issue(9, [], 1)], lag });
    const first = await runQueue(w, opened(8));
    const second = await runQueue(w, opened(9));
    assert.deepEqual(first, ['+claude:queued #8', '-claude:queued #8', '+claude:in-progress #8']);
    assert.deepEqual(second, ['+claude:queued #9']);
  });

  test(`merge, then the next issue is dispatched and later finished${tag}`, async () => {
    const w = world({ issues: [issue(5, [], 2), issue(6, [], 1)], lag });
    await runQueue(w, opened(5));
    await runQueue(w, opened(6));
    w.pulls = [pr(5, { state: 'closed', createdAgo: 0.1 * H, closedAgo: 0, merged: true })];
    assert.deepEqual(await runQueue(w, closed(5, true)), [
      '-claude:in-progress #5', '+claude:done #5', '-claude:queued #6', '+claude:in-progress #6',
    ]);
    w.pulls.push(pr(6, { state: 'closed', createdAgo: 0, closedAgo: 0, merged: false }));
    assert.deepEqual(await runQueue(w, closed(6, false)), ['-claude:in-progress #6', '+claude:failed #6']);
    assert.equal(w.log.filter((l) => l.startsWith('VIOLATION')).length, 0);
  });
}

test('a list that never catches up warns after about 90s and still dispatches correctly', async () => {
  const w = world({ issues: [issue(5, [], 0)], lag: 1e6 });
  const log = await runQueue(w, opened(5));
  assert.deepEqual(log.filter((l) => !l.startsWith('warn')), [
    '+claude:queued #5', '-claude:queued #5', '+claude:in-progress #5',
  ]);
  // The frozen list never showed claude:queued on #5, so only the two adds wait it out.
  assert.equal(log.filter((l) => l.startsWith('warn')).length, 2);
  assert.ok(w.slept >= 2 * 90e3 && w.slept < 2 * 110e3, `slept ${w.slept}ms`);
});

test('issue opened by someone else is ignored', async () => {
  const w = world({ issues: [issue(5, [], 0)] });
  assert.deepEqual(await runQueue(w, opened(5, 'bob')), []);
});

test('PR rejected, linked only by branch name, fails the issue', async () => {
  const w = busy();
  assert.deepEqual(await runQueue(w, closed(2, false, { PR_BODY: '' })), [
    '-claude:in-progress #2', '+claude:failed #2', '-claude:queued #3', '+claude:in-progress #3',
  ]);
});

test('PR without a linked issue changes nothing', async () => {
  const w = busy();
  assert.deepEqual(await runQueue(w, closed(2, true, { PR_BODY: 'queue fix', PR_HEAD_REF: 'claude/fix-queue' })), []);
});

test('PR from a fork changes nothing', async () => {
  const w = busy();
  assert.deepEqual(await runQueue(w, closed(2, false, { PR_HEAD_REPO: 'evil/fork' })), []);
});

test('stale issue without a PR is failed with a comment', async () => {
  const w = busy({ events: { 2: inProgressAt(4 * H) } });
  assert.deepEqual(await runQueue(w, { QUEUE_MODE: 'stale' }), [
    '-claude:in-progress #2', '+claude:failed #2', 'comment #2', '-claude:queued #3', '+claude:in-progress #3',
  ]);
});

test('stale issue with an open PR is left alone', async () => {
  const w = busy({ events: { 2: inProgressAt(4 * H) }, pulls: [pr(2, { state: 'open', createdAgo: 2 * H })] });
  assert.deepEqual(await runQueue(w, { QUEUE_MODE: 'stale' }), []);
});

test('retry is not failed by a PR closed in an earlier attempt', async () => {
  const w = busy({ pulls: [pr(2, { state: 'closed', createdAgo: 50 * H, closedAgo: 40 * H })] });
  assert.deepEqual(await runQueue(w, { QUEUE_MODE: 'dispatch' }), []);
});

test('reconcile finishes an issue whose close event was missed', async () => {
  const w = busy({ pulls: [pr(2, { state: 'closed', createdAgo: 0.5 * H, closedAgo: 0.1 * H, merged: true, body: 'Fixes #2' })] });
  assert.deepEqual(await runQueue(w, { QUEUE_MODE: 'dispatch' }), [
    '-claude:in-progress #2', '+claude:done #2', '-claude:queued #3', '+claude:in-progress #3',
  ]);
});

test('linkedIssueNumber reads the body first, then the branch', () => {
  assert.equal(run.linkedIssueNumber('Closes #12', 'claude/issue-3'), 12);
  assert.equal(run.linkedIssueNumber('resolves: #7', ''), 7);
  assert.equal(run.linkedIssueNumber('', 'claude/issue-3'), 3);
  assert.equal(run.linkedIssueNumber('see #4', 'claude/intelligent-edison'), null);
});
