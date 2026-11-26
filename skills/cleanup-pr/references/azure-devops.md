# Azure DevOps

Resolve the remote whose URL contains `dev.azure.com` or `visualstudio.com`
with `git remote -v`. Parse `<org>/<project>/_git/<repo>` and use that remote
name everywhere; never assume `origin` or `main`. Auth comes from `az login`.

```bash
ORG=https://dev.azure.com/<org>
```

## Verify PR state

```bash
az repos pr show --id <n> --org $ORG \
  --query "{status:status,source:sourceRefName,target:targetRefName,head:lastMergeSourceCommit.commitId,deleteSource:completionOptions.deleteSourceBranch}"
```

- `status == "completed"` confirms the PR merged (including squash merges).
- `status == "abandoned"` means unmerged — do not delete unless the user explicitly authorized discarding it.
- Strip `refs/heads/` from `source` to get `<branch>`.

## Check for dependent active PRs

Before deleting the remote branch, verify no active PR uses it as source or target (for example, stacked PRs or release branches):

```bash
az repos pr list --org $ORG --project <project> --repository <repo> --status active \
  --target-branch <branch> --query "[].{id:pullRequestId,title:title}"
az repos pr list --org $ORG --project <project> --repository <repo> --status active \
  --source-branch <branch> --query "[].{id:pullRequestId,title:title}"
```

If either returns an active PR, skip remote deletion and report it.

## Delete remote branch

Check whether Azure DevOps already deleted the source branch on completion:

```bash
git ls-remote --heads <remote> <branch>
```

If present and its SHA matches `lastMergeSourceCommit.commitId`:

```bash
git push <remote> --delete <branch>
```

## Bulk lookup for squash-merged branches

When checking local branches that `git branch -d` rejects, verify whether each branch has a completed PR before using `git branch -D`:

```bash
az repos pr list --org $ORG --project <project> --repository <repo> \
  --status completed --source-branch <branch> \
  --query "[].{id:pullRequestId,status:status,head:lastMergeSourceCommit.commitId}"
```

Confirm local `git rev-parse <branch>` matches `head` (no extra local commits) before force-deleting locally.
