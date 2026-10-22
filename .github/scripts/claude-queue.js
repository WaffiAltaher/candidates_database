// Label-only queue that feeds issues to Claude one at a time.
//
// A Claude Code scheduled task starts a session whenever claude:in-progress is
// added to an issue. This script never calls Claude. It only moves labels.
// See docs/claude-queue.md for the flow.
//
// Entry point for actions/github-script. QUEUE_MODE selects the event step:
//   intake    issues.opened: queue the new issue
//   pr-closed pull_request.closed: finish the linked issue
//   stale     schedule: fail issues stuck in progress without a PR
//   dispatch  workflow_dispatch: only reconcile and dispatch
// Every mode then reconciles and runs the dispatcher.

const QUEUED = 'claude:queued';
const IN_PROGRESS = 'claude:in-progress';
const DONE = 'claude:done';
const FAILED = 'claude:failed';

const OWNER_LOGIN = 'WaffiAltaher';
const STALE_MS = 3 * 60 * 60 * 1000;

const LABELS = {
  [QUEUED]: { color: 'c5def5', description: 'Waiting in the Claude queue' },
  [IN_PROGRESS]: { color: 'fbca04', description: 'Claude is working on this issue. Do not add labels.' },
  [DONE]: { color: '0e8a16', description: 'Claude PR merged' },
  [FAILED]: { color: 'd93f0b', description: 'Claude PR closed without merge, or timed out' },
};

const CLOSES_RE = /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b/i;
const BRANCH_RE = /^claude\/issue-(\d+)(?:$|[-_/])/;

function linkedIssueNumber(body, headRef) {
  const fromBody = CLOSES_RE.exec(body || '');
  if (fromBody) return Number(fromBody[1]);
  const fromBranch = BRANCH_RE.exec(headRef || '');
  if (fromBranch) return Number(fromBranch[1]);
  return null;
}

module.exports = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const env = process.env;
  const mode = env.QUEUE_MODE;

  const labelNames = (issue) => issue.labels.map((l) => (typeof l === 'string' ? l : l.name));

  async function getIssue(number) {
    try {
      const { data } = await github.rest.issues.get({ owner, repo, issue_number: number });
      return data;
    } catch (err) {
      if (err.status === 404 || err.status === 410) return null;
      throw err;
    }
  }

  async function removeLabel(number, name) {
    try {
      await github.rest.issues.removeLabel({ owner, repo, issue_number: number, name });
    } catch (err) {
      if (err.status !== 404) throw err;
    }
  }

  // Every label added to an issue that has claude:in-progress can start
  // another Claude session, so re-read the labels and refuse in that case.
  // The only exception is the dispatcher adding claude:in-progress itself.
  async function addLabel(number, name) {
    const issue = await getIssue(number);
    if (!issue) throw new Error(`Issue #${number} not found`);
    const current = labelNames(issue);
    if (current.includes(name)) return;
    if (current.includes(IN_PROGRESS)) {
      throw new Error(`Refusing to add ${name} to #${number}: it still has ${IN_PROGRESS}`);
    }
    await github.rest.issues.addLabels({ owner, repo, issue_number: number, labels: [name] });
  }

  async function ensureLabels() {
    for (const [name, spec] of Object.entries(LABELS)) {
      try {
        await github.rest.issues.getLabel({ owner, repo, name });
      } catch (err) {
        if (err.status !== 404) throw err;
        core.info(`Creating label ${name}`);
        await github.rest.issues.createLabel({ owner, repo, name, ...spec });
      }
    }
  }

  // Issues (not PRs) carrying a label, oldest first.
  async function issuesWithLabel(label, state) {
    const items = await github.paginate(github.rest.issues.listForRepo, {
      owner, repo, labels: label, state, sort: 'created', direction: 'asc', per_page: 100,
    });
    return items.filter((i) => !i.pull_request);
  }

  // When claude:in-progress was most recently added to the issue.
  async function inProgressSince(number) {
    const events = await github.paginate(github.rest.issues.listEvents, {
      owner, repo, issue_number: number, per_page: 100,
    });
    const labeled = events.filter((e) => e.event === 'labeled' && e.label && e.label.name === IN_PROGRESS);
    if (labeled.length === 0) return null;
    return new Date(labeled[labeled.length - 1].created_at);
  }

  let allPulls = null;
  async function linkedPulls(number) {
    if (!allPulls) {
      allPulls = await github.paginate(github.rest.pulls.list, {
        owner, repo, state: 'all', per_page: 100,
      });
    }
    return allPulls.filter((pr) =>
      pr.head && pr.head.ref.startsWith('claude/') &&
      pr.head.repo && pr.head.repo.full_name === `${owner}/${repo}` &&
      linkedIssueNumber(pr.body, pr.head.ref) === number);
  }

  // Remove claude:in-progress FIRST, then add the outcome label.
  async function finish(number, outcome) {
    await removeLabel(number, IN_PROGRESS);
    await addLabel(number, outcome);
    core.info(`#${number}: ${IN_PROGRESS} -> ${outcome}`);
  }

  // --- event steps -------------------------------------------------------

  async function intake() {
    const number = Number(env.ISSUE_NUMBER);
    if (env.ISSUE_AUTHOR !== OWNER_LOGIN) {
      core.info(`Ignoring #${number} opened by ${env.ISSUE_AUTHOR}`);
      return;
    }
    const issue = await getIssue(number);
    if (!issue || issue.state !== 'open') return;
    const current = labelNames(issue);
    if ([IN_PROGRESS, QUEUED, DONE, FAILED].some((l) => current.includes(l))) {
      core.info(`#${number} already has a queue label, leaving it alone`);
      return;
    }
    await addLabel(number, QUEUED);
    core.info(`#${number} queued`);
  }

  async function prClosed() {
    const headRef = env.PR_HEAD_REF || '';
    if (!headRef.startsWith('claude/')) {
      core.info(`Head branch ${headRef} is not a claude/ branch, nothing to do`);
      return;
    }
    if (env.PR_HEAD_REPO !== `${owner}/${repo}`) {
      core.info(`PR comes from ${env.PR_HEAD_REPO}, not this repository, nothing to do`);
      return;
    }
    const number = linkedIssueNumber(env.PR_BODY, headRef);
    if (!number) {
      core.info('No linked issue in the PR body or branch name, nothing to do');
      return;
    }
    const issue = await getIssue(number);
    if (!issue || issue.pull_request) {
      core.info(`#${number} is not an issue, nothing to do`);
      return;
    }
    if (!labelNames(issue).includes(IN_PROGRESS)) {
      core.info(`#${number} does not have ${IN_PROGRESS}, nothing to do`);
      return;
    }
    await finish(number, env.PR_MERGED === 'true' ? DONE : FAILED);
  }

  async function stale() {
    const now = Date.now();
    for (const issue of await issuesWithLabel(IN_PROGRESS, 'all')) {
      const since = await inProgressSince(issue.number);
      if (!since) {
        core.warning(`#${issue.number} has ${IN_PROGRESS} but no labeled event was found`);
        continue;
      }
      if (now - since.getTime() <= STALE_MS) continue;
      // A PR from an earlier attempt that is already closed does not count.
      const pulls = (await linkedPulls(issue.number))
        .filter((pr) => pr.state === 'open' || new Date(pr.created_at) >= since);
      if (pulls.length > 0) continue;
      await finish(issue.number, FAILED);
      await github.rest.issues.createComment({
        owner, repo, issue_number: issue.number,
        body: `Claude queue: this issue had \`${IN_PROGRESS}\` since ${since.toISOString()} ` +
          `(more than 3 hours) without a linked pull request, so it is marked \`${FAILED}\` ` +
          `and the next queued issue will start.\n\n` +
          `To retry, remove \`${FAILED}\` and add \`${QUEUED}\`.`,
      });
    }
  }

  // A pending run in the concurrency group can be replaced by a newer one,
  // so a pull_request.closed run may never execute. Catch up here: an issue in
  // progress whose linked PRs (opened during this attempt) are all closed is
  // finished, done if any of them merged.
  async function reconcile() {
    for (const issue of await issuesWithLabel(IN_PROGRESS, 'all')) {
      const since = await inProgressSince(issue.number);
      if (!since) continue;
      const pulls = (await linkedPulls(issue.number))
        .filter((pr) => pr.state === 'open' || (pr.closed_at && new Date(pr.closed_at) >= since));
      if (pulls.length === 0 || pulls.some((pr) => pr.state === 'open')) continue;
      core.info(`Reconciling #${issue.number}: its linked PRs are closed`);
      await finish(issue.number, pulls.some((pr) => pr.merged_at) ? DONE : FAILED);
    }
  }

  // If no issue has claude:in-progress, move the oldest open queued issue to
  // claude:in-progress. Closed issues count too: an issue closed by hand
  // while in progress still blocks until the PR closes or the stale check runs.
  async function dispatch() {
    const active = await issuesWithLabel(IN_PROGRESS, 'all');
    if (active.length > 0) {
      core.info(`In progress: ${active.map((i) => `#${i.number}`).join(', ')}. Not dispatching.`);
      return;
    }
    const queued = await issuesWithLabel(QUEUED, 'open');
    if (queued.length === 0) {
      core.info('Queue is empty');
      return;
    }
    const next = queued[0];
    await removeLabel(next.number, QUEUED);
    await github.rest.issues.addLabels({ owner, repo, issue_number: next.number, labels: [IN_PROGRESS] });
    core.info(`Dispatched #${next.number}`);
  }

  // --- main --------------------------------------------------------------

  await ensureLabels();
  switch (mode) {
    case 'intake': await intake(); break;
    case 'pr-closed': await prClosed(); break;
    case 'stale': await stale(); break;
    case 'dispatch': break;
    default: throw new Error(`Unknown QUEUE_MODE ${mode}`);
  }
  await reconcile();
  await dispatch();
};

module.exports.linkedIssueNumber = linkedIssueNumber;
