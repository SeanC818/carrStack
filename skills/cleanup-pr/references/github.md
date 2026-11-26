# GitHub

Use an authenticated `gh`. The remote is usually `origin`.

## Verify PR state

```bash
gh pr view <n> --json state,headRefName,headRefOid,baseRefName,headRepositoryOwner,isCrossRepository,url
```

- `state == "MERGED"` confirms the PR landed (including squash and rebase merges).
- If `isCrossRepository` is `true`, the branch lives on a fork (`headRepositoryOwner.login`); do not delete the remote branch on someone else's fork unless explicitly authorized.

## Check for dependent open PRs

Before deleting the remote branch, make sure no open PR uses it as head or base (for example, a stacked child PR):

```bash
gh pr list --state open --base <branch> --json number,url
gh pr list --state open --head <branch> --json number,url
```

If either returns an open PR, skip remote deletion and report it.

## Delete remote branch

Check whether GitHub already auto-deleted it:

```bash
git ls-remote --heads <remote> <branch>
```

If present and its SHA matches `headRefOid`:

```bash
git push <remote> --delete <branch>
```

## Bulk lookup for squash-merged branches

When checking local branches that `git branch -d` rejects, verify whether each branch has a merged PR before using `git branch -D`:

```bash
gh pr list --state merged --head <branch> --limit 5 --json number,state,headRefOid,mergedAt,url
```

Confirm local `git rev-parse <branch>` matches `headRefOid` (no extra local commits) before force-deleting locally.
