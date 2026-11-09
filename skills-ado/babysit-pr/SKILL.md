---
name: babysit-pr
description: Monitor an Azure DevOps pull request through policies, builds, and review. Use when the user asks to monitor, watch, or babysit a PR.
---

# Babysit PR

Babysit an Azure DevOps (ADO) pull request until its policies pass and its
reviewers are satisfied. Reviewers and build bots are helpful, even if they are
not always right.

## Azure DevOps basics

Resolve the repo from the checkout. Find the remote whose URL contains
`dev.azure.com` (or `visualstudio.com`) with `git remote -v`. Parse
`<org>/<project>/_git/<repo>` from it. Use that remote's name everywhere, and
never assume `origin`. Auth comes from `az login`. Never ask for a PAT.

```bash
ORG=https://dev.azure.com/<org>
az repos pr show --id <n> --org $ORG
az repos pr policy list --id <n> --org $ORG
az devops invoke --org $ORG --area git --resource pullRequestThreads \
  --route-parameters project=<project> repositoryId=<repo> pullRequestId=<n> --api-version 7.1
```

`pr show` and `pr policy list` reject `--project`. `pr list` and `pr create`
need `--project` and `--repository`.

Useful fields:

- `status`: `active`, `completed` (merged), or `abandoned`.
- `mergeStatus`: `succeeded`, `conflicts`, `queued`, `rejectedByPolicy`, or `failure`.
- `lastMergeSourceCommit.commitId` is the PR head.
- `reviewers[].vote`: 10 approved, 5 approved with suggestions, 0 no vote,
  -5 waiting for author, -10 rejected.
- Policy evaluation `status`: `queued`, `running`, `approved`, `rejected`,
  `broken`, or `notApplicable`. Only `configuration.isBlocking` policies gate.
- Threads with `comments[0].commentType == "system"` are ADO's own activity
  log. Only `text` threads are review comments. An `active` or `pending` text
  thread is unresolved.

## Waiting

Never write your own watcher, polling loop, or `sleep` loop. Use one watcher
per PR.

### In T3 Code

If `watch_pull_request` is available, try it with the full ADO PR URL. If it
refuses the host, use `pr-wait`. Never run both on the same PR.

- **Only the thread that owns the PR watches it.** A delegated child task
  never watches.
- **A wake is news, not a merge decision.** Check the merge gate yourself.
- **Unwatch when you hand off.** Call `unwatch_pull_request` before you stop
  or ask the user a question.

### `pr-wait`

Wait with `scripts/pr-wait.py` from this skill's directory. Use its absolute
path, and run it with `python` (not `python3`, which can be a different
install on Windows).

```bash
python "<skill dir>/scripts/pr-wait.py" <pr id or url> [--until ready|green|any-change]
```

It reads the org, project, and repo from the PR URL or from the current
checkout's ADO remote. It prints one line per real event. Exit codes:

- **0**: the `--until` condition is met, or the PR merged.
- **1**: it needs you. A blocking policy failed, the branch conflicts, a
  reviewer rejected, threads are unresolved, the branch is behind its target,
  the PR is a draft or abandoned, or ADO is unreachable.
- **2**: bad input, an unknown PR, or another watcher already holds the PR.

The `--until` modes:

- `ready` (default): every blocking policy is approved, including required
  reviewers. The merge status is `succeeded`, no text thread is active, and
  the branch is not behind its target. While only approval is missing, it
  prints `waiting for required approval` once and keeps waiting.
- `green`: blocking non-reviewer policies only (builds, status checks,
  branch-source checks).
- `any-change`: exit on the first event.

In Claude Code, run it with the Monitor tool (`timeout_ms: 1800000`, the
maximum), so each line wakes you. Re-arm it when the monitor expires. Start it
again after you push, after you handle an exit 1, and after a resume. It
remembers what it already reported. If it says another pid already watches the
PR, do not start a second one.

With either watcher, when an event needs no action, end your turn without a
message. Never post or say "still waiting".

## Reviews

Only act on policies and comments newer than the latest push. Verify every
finding against the source before changing code. Fix real findings and build
failures. Tell repository failures apart from infrastructure flakes: open the
build link that `pr-wait` prints, or run `az pipelines runs show --id <buildId>
--org $ORG --project <project>`.

If a comment is not worth addressing, reply with a written reason and set the
thread status to `wontFix` or `byDesign`. Set it to `fixed` after you push a
fix. Use the `leaving-pr-comments` skill for every comment posted on the
user's behalf.

Keep the PR at the size the user's goal needs. Review loops tend to grow a PR
one cheap-looking fix at a time. Fix real bugs in the intended case. Decline
the rest with a written reason and list them as follow-ups. Prefer the fix
that deletes or narrows code.

## Target branch and merging

Watch for changes to the PR's target branch (`targetRefName`, which is often
not the default branch). `pr-wait` reports target commits that touch this PR's
files, conflicts, and being behind. If an overlapping PR makes this one
obsolete, stop, report it, and ask before abandoning the PR.

Merge only when the user explicitly asked for it. Otherwise report that the PR
is ready. Right before a merge, `git fetch <remote>` and check the PR again.
Never merge while it conflicts, is behind, or has target commits that landed
after the last green build and touch this PR's files.

Complete with the repo's usual options. Read `completionOptions` on recent
completed PRs (for example, `noFastForward` and `deleteSourceBranch`):

```bash
az repos pr update --id <n> --org $ORG --status completed --delete-source-branch true
```

Add `--squash true` only if the repo squashes. Never use `--bypass-policy`.
