# Issue tracker: GitHub

Tickets, specs and decisions for this repo live as GitHub issues in
`WaffiAltaher/candidates_database`. Use the `gh` CLI for all operations, run
from the repository directory (direnv there selects the `WaffiAltaher`
account; check with `gh api user --jq .login` before the first write).

## Ticket types

Every ticket gets exactly one of these labels when it is published. Specs,
parent issues and wayfinder issues get none of them.

| Label | Ticket type | Who carries it out |
|---|---|---|
| `ready-for-agent` | Agent ticket | A cloud Claude session, through the queue (`docs/claude-queue.md`). Code-only work that needs no account access |
| `ready-for-orchestrator` | Orchestrator ticket | The local orchestrator session: steps that need account access or local tools (Scaleway, AWS, Cockpit tokens, GitHub settings and secrets, releases) |
| `ready-for-human` | Human ticket | The owner only: approvals the orchestrator may not give, phone or password steps, judgement calls |

**`ready-for-agent` starts a cloud session.** Adding it (or opening an issue
with it) queues the issue; the queue starts it once it has no open blockers
and no other issue is in progress. Never put it on a ticket that needs
account access. Never add any label to an issue that has
`claude:in-progress`.

When a skill says "apply the AFK-ready triage label", use `ready-for-agent`.
When it says "requires human implementation", decide between
`ready-for-orchestrator` and `ready-for-human`.

## Agent ticket format

Agent tickets are read by Sonnet, so they are more specific than the
`to-tickets` template suggests. Use the template (Parent, What to build,
Acceptance criteria, Blocked by), then add:

```markdown
## Implementation notes

- Files to change or add, and the shape of the change (functions, classes,
  config keys). Code snippets where they remove ambiguity.
- Tests to add or update, by file and test name.
- Checks to run before opening the PR: `poetry run pytest`;
  `node --test .github/scripts/claude-queue.test.js` if `.github/scripts/`
  changed; `actionlint` if `.github/workflows/` changed.
- Work on the branch `claude/issue-<N>` and open a PR whose body contains
  `Closes #<N>`.
```

File paths can go in these notes: an agent ticket is picked up within hours,
so they do not go stale.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..." --label <type>`. Use a heredoc for multi-line bodies. Add the blocking edges (below) right after creating it; the queue re-checks blockers on every run.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: `gh api --method POST repos/WaffiAltaher/candidates_database/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`, where `<child-db-id>` is the numeric database id (`gh api repos/WaffiAltaher/candidates_database/issues/<n> --jq .id`). With `gh` 2.94+ you can use `gh issue create --parent <parent>` instead.
- **Blocking**: GitHub's native issue dependencies. Add an edge with `gh api --method POST repos/WaffiAltaher/candidates_database/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` (database id as above, not the `#number`). With `gh` 2.94+: `gh issue edit <child> --add-blocked-by <blocker>`. A ticket is unblocked when every blocker is closed.
- **Count open blockers**: `gh api repos/WaffiAltaher/candidates_database/issues/<n> --jq .issue_dependencies_summary.blocked_by` (0 means startable).
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: post the explanation with `gh issue comment <number> --body "..."`, then `gh issue close <number>`. An agent ticket is closed by its merged PR (`Closes #N`); orchestrator and human tickets are closed by hand when done, which can release blocked agent tickets.

File issues only into `WaffiAltaher/candidates_database`. Never file into
`mattpocock/skills`.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

## When a skill says "publish to the issue tracker"

Create a GitHub issue, with a ticket-type label if it is a ticket.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets. Map and children carry only `wayfinder:*` labels, never a ticket-type label, so the queue never picks them up.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (see **Make an issue a sub-issue of a parent**). Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: see **Blocking** under Conventions.
- **Frontier query**: list the map's open sub-issues, drop any with an open blocker (see **Count open blockers**) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
