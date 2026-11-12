# Azure DevOps

Other skills point here for the shared Azure DevOps (ADO) basics.

## Basics

Resolve the repo from the checkout. Find the remote whose URL contains
`dev.azure.com` (or `visualstudio.com`) with `git remote -v`. Parse
`<org>/<project>/_git/<repo>` from it. Use that remote's name everywhere, and
never assume `origin` or `main`. Auth comes from `az login`. Never ask for a
PAT.

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
- `targetRefName` is the base branch, often not the default branch.
- `lastMergeSourceCommit.commitId` is the PR head.
- `autoCompleteSetBy` is set when the PR will complete on its own.
- `reviewers[].vote`: 10 approved, 5 approved with suggestions, 0 no vote,
  -5 waiting for author, -10 rejected.
- Policy evaluation `status`: `queued`, `running`, `approved`, `rejected`,
  `broken`, or `notApplicable`. Only `configuration.isBlocking` policies gate.
- Threads with `comments[0].commentType == "system"` are ADO's own activity
  log. Only `text` threads are review comments. An `active` or `pending` text
  thread is unresolved.

ADO caps PR descriptions at 4000 characters.

## Waiting

`scripts/pr-wait-ado.py` needs the Azure CLI. Run it with `python` (not
`python3`, which can be a different install on Windows):

```bash
python "<skill dir>/scripts/pr-wait-ado.py" <pr id or url> [--until ready|green|any-change]
```

It reads the org, project, and repo from the PR URL or from the checkout's
ADO remote. Exit 1 also covers a reviewer rejection, the branch being behind
its target, a draft or abandoned PR, and ADO being unreachable.

- `ready` (default): every blocking policy is approved, including required
  reviewers. The merge status is `succeeded`, no text thread is active, and
  the branch is not behind its target. While only approval is missing, it
  prints `waiting for required approval` once and keeps waiting.
- `green`: blocking non-reviewer policies only (builds, status checks,
  branch-source checks).
- `any-change`: exit on the first event.

In Claude Code, run it with the Monitor tool (`timeout_ms: 1800000`, the
maximum). Re-arm it when the monitor expires.

## Reviews

Open the build link that `pr-wait` prints, or run
`az pipelines runs show --id <buildId> --org $ORG --project <project>`, to
tell repository failures from infrastructure flakes.

Resolve a thread with status `fixed` after you push a fix, and `wontFix` or
`byDesign` after a written reason. See `leaving-pr-comments`.

## Merge gate

- The PR is `active`, not a draft, and `mergeStatus` is `succeeded`.
- The branch is not behind its target.
- Every blocking policy evaluation is `approved` or `notApplicable`. That
  includes "Minimum number of reviewers": the creator's own vote usually does
  not count, so a required human approval is a real blocker. Ask the user for
  a reviewer. Never approve your own PR to satisfy it.

Complete with the repo's usual options. Read `completionOptions` on recent
completed PRs (for example, `noFastForward` and `deleteSourceBranch`):

```bash
az repos pr update --id <n> --org $ORG --status completed --delete-source-branch true
```

Add `--squash true` only if the repo squashes. If you set
`--auto-complete true`, stay until ADO reports the PR as `completed`. Never
use `--bypass-policy`.
