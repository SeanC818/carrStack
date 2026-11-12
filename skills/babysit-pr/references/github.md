# GitHub

Use an authenticated `gh`. The remote is usually `origin`.

## Waiting

`scripts/pr-wait` needs `python3`:

```bash
pr-wait <pr> [--repo owner/name] [--until ready|green|any-change]
```

- `ready` (default): required checks green, Greptile or Macroscope reviewed
  the head, and no unresolved threads. Use this to babysit.
- `green`: required checks only. Use it when the repo has no Greptile or
  Macroscope.
- `any-change`: exit on the first event.

In Claude Code, run it with the Monitor tool (`timeout_ms: 3600000`).

## Rate limits

Every watcher on a GitHub account shares one rate limit.
`gh pr create`, `gh pr view`, and `gh pr checks` use GraphQL. When GraphQL is
used up, the REST limit is separate and usually still has room. Use
`gh api repos/<owner>/<repo>/pulls/<n>` to read a PR, and
`gh api repos/<owner>/<repo>/commits/<sha>/check-runs` for checks.

If `watch_pull_request` says "stopped watching, could not read it", GitHub's
rate limit is usually used up. Run `gh api rate_limit --jq .resources.graphql`
before you watch again. If `remaining` is near 0, wait for `reset` with one
background command, then watch again. Never watch again in a tight loop.

## Merge gate

The PR is open, not a draft, required checks are green, no review requests
changes, and GitHub reports it mergeable and not BEHIND or DIRTY. Merge with
the repo's usual method. Check recent merged PRs for squash or merge commits.
