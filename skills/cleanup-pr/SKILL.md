---
name: cleanup-pr
description: Clean up local and remote branches, stale worktrees, and PR watches after a PR merges or closes on GitHub or Azure DevOps. Use after merging or closing a PR, or when the user asks to clean up branches or run post-merge cleanup.
---

# Cleanup PR

Remove finished local and remote branches, stale worktrees, and leftover PR
watches without risking unmerged work or protected branches.

## Platform

Run `git remote -v` in the checkout, or read the PR URL. Then read the
matching reference before deleting anything:

- `github.com`: [references/github.md](references/github.md)
- `dev.azure.com` or `visualstudio.com`: [references/azure-devops.md](references/azure-devops.md)

## Guardrails

- **Never delete protected or long-lived branches:** default branch (`main`,
  `master`, `develop`), `sprint/*`, `release/*`, `hotfix/*`, or any branch
  referenced as head or base by an open PR (including stacked child PRs).
- **Never delete unmerged work silently.** Only delete a branch automatically
  when the live platform confirms its PR is merged (`MERGED` on GitHub,
  `completed` on Azure DevOps). For closed/abandoned PRs or local branches with
  unmerged commits, stop and ask before deleting unless the user explicitly
  authorized discarding them.
- **Check remote head before remote delete.** Only delete the remote branch if
  its current ref SHA matches the merged/closed PR head (so you do not delete
  newer commits pushed later) and the branch lives in a repo you own/control
  (never delete branches on another contributor's fork without authorization).
- **Protect uncommitted changes.** Check `git status --short` in the target
  checkout or worktree before switching branches or removing a worktree. If it
  is dirty, stop and report instead of forcing removal.

## Single-PR post-merge cleanup

1. **Fetch and prune:** Run `git fetch --prune <remote>` using the platform's
   remote (never assume `origin` on Azure DevOps).
2. **Verify PR state:** Confirm on the platform that the PR is merged (or
   closed/abandoned with explicit permission to discard), record its source
   branch name and head SHA, and confirm no open PR depends on that branch.
3. **Delete remote branch (if still present):** Check
   `git ls-remote --heads <remote> <branch>`. If the platform already
   auto-deleted it, note that as already clean. Otherwise verify the remote SHA
   matches the PR head and run `git push <remote> --delete <branch>`.
4. **Handle worktrees and checkout:**
   - Check `git worktree list` to see if `<branch>` is checked out anywhere.
   - If it is checked out in a clean, disposable linked worktree that is **not**
     your active shell directory, remove it with `git worktree remove <path>`
     and run `git worktree prune`.
   - If it is checked out in the main checkout and the working tree is clean,
     switch to the default or target branch (`git checkout <base>`) and
     fast-forward (`git pull --ff-only <remote> <base>`).
   - If the active thread/shell is inside a worktree bound to `<branch>`, do
     not delete your own working directory out from under the session; note it
     for removal once the thread ends or hands off.
5. **Delete local branch:**
   - Use `git branch -d <branch>` first.
   - If the PR was **squash-merged** or **rebase-merged** and you verified the
     merged state on the platform in step 2 (and confirmed no local commits
     exist beyond the merged PR head), use `git branch -D <branch>`.
   - Delete the stale remote-tracking ref if it lingers (`git remote prune <remote>`).
6. **Stop leftover watches:** In T3 Code, call `unwatch_pull_request` if the PR
   is still watched.

## Bulk branch cleanup

When the user asks to clean up stale or merged branches across a repo rather
than a single PR:

1. Run `git fetch --prune <remote>` and `git worktree prune`.
2. List local branches (`git branch -vv`) and worktrees (`git worktree list`),
   skipping protected branches and dirty checkouts.
3. Cross-check each candidate against merged/closed PRs on GitHub or Azure
   DevOps (do not rely on `git branch --merged` alone, since squash merges will
   not show as merged).
4. Delete confirmed-merged local branches and confirmed-merged remote branches
   that have no open dependent PRs.
5. List any remaining unmerged, abandoned, or dirty branches and ask before
   touching them.

## Report

Summarize briefly:
- PR checked and its verified state (`merged` / `completed` / `closed`);
- remote branch: deleted, already deleted, or skipped (with reason);
- local branch and worktree: deleted/pruned or skipped (with reason);
- any remaining branches that need user confirmation.
