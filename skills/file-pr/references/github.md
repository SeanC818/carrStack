# GitHub

Use an authenticated `gh`. The base branch is usually `origin/main`; review
`git diff origin/<base>...HEAD`.

Check for an existing PR with `gh pr view --json url,state` on the branch.

Create the PR with `gh pr create --title "<title>" --body-file <file>`. If it
fails because the GraphQL rate limit is used up, open it through REST:

```bash
gh api repos/<owner>/<repo>/pulls -f title=... -f head=... -f base=... -F body=@<file>
```
