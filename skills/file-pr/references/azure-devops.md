# Azure DevOps

Resolve `$ORG`, the project, repo, and remote name from the checkout's ADO
remote, as described in
[babysit-pr's Azure DevOps reference](../../babysit-pr/references/azure-devops.md).
Never assume `origin` or `main`.

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

Fetch with `git fetch <remote>` and review `git diff <remote>/<target>...HEAD`.
Push the branch with `git push -u <remote> <branch>`.

## Title and description

PR titles become merge commit messages (`Merged PR <n>: <title>`). ADO caps
PR descriptions at 4000 characters. Keep it well under that, so the review
tables from council or sol-loop still fit.

## Create

```bash
az repos pr create --org $ORG --project <project> --repository <repo> \
  --source-branch <branch> --target-branch <target> \
  --title "<title>" --description @<file> -o json --query "{id:pullRequestId,status:status}"
```

Link work items with `--work-items <ids>` when the user names them. The PR URL
is `https://dev.azure.com/<org>/<project>/_git/<repo>/pullrequest/<id>`.
