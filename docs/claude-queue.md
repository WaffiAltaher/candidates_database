# Claude issue queue

Issues are handed to Claude one at a time, using only labels. The workflow is
`.github/workflows/claude-queue.yml`. The logic lives in
`.github/scripts/claude-queue.js`.

The workflow never calls Claude. A Claude Code scheduled task watches this
repository with the trigger "Issue: Labeled", filtered to the label
`claude:in-progress` and the author `WaffiAltaher`. When the workflow adds
`claude:in-progress` to an issue, that task starts a Claude session. The
session works on the branch `claude/issue-<N>` and opens a PR whose body
contains `Closes #<N>`.

## Labels

| Label | Meaning |
|---|---|
| `claude:queued` | Waiting for its turn |
| `claude:in-progress` | Claude is working on it. Only one issue has this label at a time |
| `claude:done` | The Claude PR was merged |
| `claude:failed` | The Claude PR was closed without merging, or no PR appeared within 3 hours |

The workflow creates any of these labels that are missing on each run.

## Flow

1. **New issue.** When `WaffiAltaher` opens an issue, it gets `claude:queued`.
   Issues opened by anyone else are ignored.
2. **Dispatcher.** If no issue has `claude:in-progress`, the oldest open issue
   with `claude:queued` loses `claude:queued` and gets `claude:in-progress`.
   That starts the Claude session. If an issue is already in progress, the
   dispatcher does nothing. A closed issue that still has
   `claude:in-progress` also blocks the queue.
3. **PR closed.** When a PR from a `claude/` branch in this repository is
   closed, the workflow finds the linked issue from `Closes #N` (also
   `Fixes`/`Resolves`) in the PR body, or else from the branch name
   `claude/issue-N`. If that issue has `claude:in-progress`, the workflow
   removes `claude:in-progress` first, then adds `claude:done` (merged) or
   `claude:failed` (closed without merging). This happens even if GitHub has
   already closed the issue through `Closes #N`. A PR with no linked issue is
   ignored.
4. **Timeout.** Every 3 hours, any issue that has had `claude:in-progress` for
   more than 3 hours with no linked PR from this attempt loses
   `claude:in-progress`, gets `claude:failed` and a comment.

Every run (new issue, PR closed, schedule, manual) ends by running the
dispatcher in the same job. Label changes made by the workflow's
`GITHUB_TOKEN` do not start other workflow runs, so nothing relies on label
events to chain steps.

**The queue waits for the PR to be merged or closed, not opened.** While the
PR is open for review, its issue keeps `claude:in-progress` and no other
issue starts. The timeout does not fire while an open linked PR exists.

All runs share the concurrency group `claude-queue` with
`cancel-in-progress: false`, so two runs never dispatch at the same time.
GitHub keeps only one pending run per group, and a newer pending run replaces
an older one. To cover a lost "PR closed" run, every run also checks each
in-progress issue: if all its linked PRs from this attempt are closed, it is
marked `claude:done` (any merged) or `claude:failed`. A lost "issue opened"
run is not recovered. Add `claude:queued` to that issue by hand.

## Start the queue by hand

Run the workflow from the Actions tab (**Claude queue** → **Run workflow**),
or:

```bash
gh workflow run claude-queue.yml --repo WaffiAltaher/candidates_database
```

This runs the dispatcher. Use it after you queue issues by hand.

## Queue an existing issue

Add `claude:queued` to the issue, then run the workflow by hand. Adding the
label alone does not start anything.

## Retry a failed issue

1. Remove `claude:failed`.
2. Add `claude:queued`.
3. Run the workflow by hand.

A closed PR from the earlier attempt does not count against the retry.

## Start a specific issue now

Make sure no issue has `claude:in-progress`. Then remove `claude:queued` from
the issue, if it has it, and add `claude:in-progress`. That starts the Claude
session directly, bypassing the queue order.

## Warning: do not add labels to an in-progress issue

Do not add any label to an issue while it has `claude:in-progress`. The
scheduled task reacts to label events on such issues, and each label added
can start another Claude session on the same issue. Remove
`claude:in-progress` first if you need to relabel. The workflow follows the
same rule: it always removes `claude:in-progress` before adding
`claude:done` or `claude:failed`.

## Stop an issue

Remove `claude:in-progress`, add `claude:failed`, then run the workflow by
hand to start the next issue.
