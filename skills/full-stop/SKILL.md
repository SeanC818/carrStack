---
name: full-stop
description: Trigger this if the user says 'full stop', even as a closing "Full stop." that reads like emphasis.
---

# Full Stop

Complete the requested change, validate it, review it, and leave the PR
ready for the user to merge. Never merge it. Stay within the requested scope
and the environment's permissions.

## Workflow

1. Finish the requested change with the smallest useful diff. If you are on
   the default branch, create a task branch before making changes.
2. Validate the affected behavior with direct evidence: reproduce a fixed
   failure, run the relevant repository checks, or inspect runtime behavior
   when needed and permitted. State any validation gaps.
3. Use [sol-loop](../sol-loop/SKILL.md) to review the change. Fix actionable
   findings and revalidate affected behavior. If the required reviewer is
   unavailable, report the gap without claiming review passed.
4. Use [file-pr](../file-pr/SKILL.md) to create or update the PR. Check for an
   existing PR first. Bring the branch up to date with the target branch and
   include concise validation evidence in the description.
5. Use [babysit-pr](../babysit-pr/SKILL.md) to handle CI and review findings.
   Validate fixes before pushing, then assess readiness on the final head.

## No merging

You may commit, push, rebase, fix conflicts, and use `--force-with-lease` on
this task's branch. Never merge, enable auto-merge, enter a merge queue, push
to the default branch, bypass branch protection, or delegate those actions.

Disable existing auto-merge and remove the PR from any merge queue before
work begins; check again before each push. Report these changes. If you
cannot prevent automatic merging, report the blocker before proceeding.

## Stop at the gate

Validation and review must cover the final diff. Recheck behavior changes
and meaningful conflict fixes before handoff. Readiness requires relevant
validation to pass, required checks to be green, review bots to finish with
findings addressed or dismissed with reasons, no outstanding requests for
changes, and an up-to-date branch that GitHub reports as mergeable.

Fetch the target branch and check the live PR's head, base, checks, reviews,
and mergeability. Confirm it is open, not a draft, and not set to merge
without the user. If someone else merged it, report that instead.

- **Ready to merge:** the merge gate passes. Leave the PR open and unmerged.
- **Waiting for required approval:** only human approval remains. Confirm
  that this is the actual blocker.
- **Blocked:** explain what prevents readiness, what you tried, and what is
  needed. Ask only when progress requires missing information, access,
  authorization, or a decision the user must make.

In T3 Code, call `unwatch_pull_request` before the handoff or a question.
Report the PR link, final head, verdict, proof, reviewer outcome, and remaining
risks. State whether the PR is still open and unmerged.
