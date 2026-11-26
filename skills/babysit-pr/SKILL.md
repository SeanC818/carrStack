---
name: babysit-pr
description: Monitor a pull request through review and CI on GitHub or Azure DevOps. Use when the user asks to monitor, watch, or babysit a PR.
---

# Babysit PR

Many repos have AI review bots and build policies. They're helpful, even if
they are not always right.

## Platform

Run `git remote -v` in the checkout, or read the PR URL. Then read the
matching reference before doing anything else:

- `github.com`: [references/github.md](references/github.md)
- `dev.azure.com` or `visualstudio.com`: [references/azure-devops.md](references/azure-devops.md)

The reference covers the CLI, the watcher script, platform rate limits or
quirks, and how to merge. The rules below apply on both.

## Waiting

Never write your own watcher, polling loop, or `sleep` loop. Use one watcher
per PR: `watch_pull_request` in T3 Code when it accepts the PR, the platform's
`pr-wait` script everywhere else. Never run both on the same PR.

### In T3 Code: `watch_pull_request`

Handle the existing checks and comments first. Then call
`watch_pull_request` and end your turn. T3 Code wakes you when a check fails,
the required checks pass, someone comments or reviews, or the branch
conflicts. If it refuses the PR's host, use `pr-wait`.

- **Only the thread that owns the PR watches it.** If you are a delegated
  child task (a reviewer, a Sol round, any `delegate_task` child), never call
  `watch_pull_request`. The parent owns the PR. Do not watch PRs you are not
  working on.
- **A wake is news, not a merge decision.** Check the merge gate yourself.
- **Unwatch when you hand off.** A watched thread stays in Working and out of
  the user's inbox. When you stop (ready, blocked, or asking the user a
  question), call `unwatch_pull_request` first. A merge or close ends the
  watch on its own.

### Everywhere else: `pr-wait`

Use the script the platform reference names, by its absolute path in this
skill's `scripts` directory. Every variant takes
`--until ready|green|any-change`, prints one line per real event, and exits:

- **0**: the `--until` condition is met, or the PR merged.
- **1**: it needs you. A required check or policy failed, the branch
  conflicts, threads are unresolved, or the PR was closed.
- **2**: bad input, or another watcher already holds the PR.

In Claude Code, run it with the Monitor tool, so each line wakes you. Without
a monitor, run it as one long command. It ends on its own.

Start it again after you push, after you handle an exit 1, and after a resume.
It remembers what it already reported, so nothing that arrived in between is
lost. If it says another pid already watches the PR, do not start a second
one. Kill the old one only if its events do not reach you.

With either watcher: when an event needs no action, end your turn without a
message. Never post or say "still waiting".

## Reviews

Only act on checks and comments newer than the latest push. Verify every
finding against the source before changing code. Fix real findings and CI
failures, distinguish repository failures from infrastructure flakes, and
reply with a written reason when dismissing false positives.

If the repo has `.macroscope/check-run-agents/*.md`, read those rules before
you reply to a Macroscope finding. Its findings cite them.

CodeRabbit is advisory. Treat its findings like any other finding, but never
wait for it and never hold a merge for it.

If feedback is not worth addressing, reply with a written reason and resolve
the thread. Use the `leaving-pr-comments` skill for every comment posted on
the user's behalf.

Screenshots and videos help as well, when you have a way to upload them.

Keep the PR at the size the user's goal needs. Review loops tend to grow a
PR one cheap-looking fix at a time. Fix real bugs in the intended case.
Decline the rest with a written reason, and list them as follow-ups:
unneeded tests, guards for edge cases that do not matter, extra integration
or compatibility, and small performance costs. Prefer the fix that deletes or
narrows code.

## Base branch and merging

Keep an eye on changes to the PR's base branch and rebase when needed. On
Azure DevOps the target is often a sprint or release branch, not the default
branch. `pr-wait` reports new base commits that touch this PR's files, and
when the PR falls behind or conflicts. `watch_pull_request` reports conflicts
only, so check for being behind yourself before you call the PR ready.

If an overlapping PR makes this one obsolete, stop monitoring, report it to
the user, and ask before closing or abandoning the PR unless that was
explicitly authorized.

If nothing has changed, stay quiet rather than posting filler comments. Stop
when `pr-wait` exits 0, or in T3 Code when the merge gate passes on the latest
head. Merge only when the user explicitly requested it; otherwise report that
the PR is ready. Right before a merge, fetch and check the PR again. Never
merge while it is behind or conflicting, or when base commits that landed
after the last green run touch this PR's files. Rebase, push, and wait for
green again.

Once the PR is merged (either by you on explicit request or observed merged by
the watcher), use [cleanup-pr](../cleanup-pr/SKILL.md) to clean up the local
and remote branches and any disposable worktree.
