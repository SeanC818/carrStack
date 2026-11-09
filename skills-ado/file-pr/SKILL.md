---
name: file-pr
description: File a concise Azure DevOps pull request. Use when the user asks to file, open, or create a PR.
---

# File PR

Resolve the org, project, repo, and remote name from the checkout's ADO remote,
as described in the `babysit-pr` skill. Never assume `origin` or `main`.

## Pick the target branch

The target is often not the default branch. Many repos flow
`feature/* → sprint/*`, or only accept `main` from `staging` or `hotfix/*`.
Branch policies reject the wrong source. Infer the target from the user's
request, then from recent completed PRs whose source branches look like this
one:

```bash
az repos pr list --org $ORG --project <project> --repository <repo> --status completed --top 20 \
  --query "[].[sourceRefName,targetRefName,title]" -o tsv
```

If two targets are plausible, ask.

## Before filing

Check whether an active PR for this branch already exists:

```bash
az repos pr list --org $ORG --project <project> --repository <repo> --source-branch <branch> --status active
```

Fetch with `git fetch <remote>` and review `git diff <remote>/<target>...HEAD`
to make sure its contents match the goal. Push the branch with
`git push -u <remote> <branch>`.

## Title

PR titles become merge commit messages (`Merged PR <n>: <title>`). Follow the
repo's conventions from recent PRs and git history. Prefer a concise,
human-readable title that explains why the change matters:

BAD

> ❌ perf(server): negotiate permessage-deflate on the websocket

GOOD

> ✅ perf(server): cut websocket frame size by 70%+ with gzipping

## Description

Open with a simple explanation of the problem, based on the user's original
prompt. Then briefly explain the solution. Do not lead with an implementation
inventory:

BAD

> ❌ Removed implicit workspace carry-over from every "new thread" entry point (cmd+n / cmd+shift+o, sidebar v1/v2 buttons, command palette). Deleted buildContextualThreadOptions and startNewThreadInProjectFromContext.

GOOD

> ✅ My "new worktree" default was ignored when starting new threads on existing worktrees. Now your preferences always apply.

End the description with the public model name and harness that made the
changes, for example `Created with <model> in <harness>.` Include subagent
models that wrote part of the change. If the model's identity is unavailable,
name the harness without guessing a model.

ADO caps PR descriptions at 4000 characters. Keep it well under that, so the
review tables from council or sol-loop still fit.

Before submission, check the title and description for secrets and private
details.

## Create

Write the description to a temp file and pass it with `@file`, so quotes and
newlines survive the shell:

```bash
az repos pr create --org $ORG --project <project> --repository <repo> \
  --source-branch <branch> --target-branch <target> \
  --title "<title>" --description @<file> -o json --query "{id:pullRequestId,status:status}"
```

Open a real PR, not a draft, so build policies run. Link work items with
`--work-items <ids>` when the user names them. Report the PR URL:
`https://dev.azure.com/<org>/<project>/_git/<repo>/pullrequest/<id>`.

If the user also asked to babysit it, continue with the `babysit-pr` skill. Do
not post a follow-up PR comment unless it serves the user's request. When a
comment is needed, use the `leaving-pr-comments` skill.
