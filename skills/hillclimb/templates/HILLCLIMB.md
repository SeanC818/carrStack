# Hill climb: {{NAME}}

{{GOAL}}

An agent improves the feature one change at a time. A frozen grader decides whether each change is kept.

## You may change
{{EDITABLE_LIST}}

## You must not change
- Anything under `hillclimb/` except `LEDGER.md` and `decisions.json` (via `hc.py record`).
- {{EXTRA_FROZEN}}
- `.claude/`.

`hc.py run` refuses to score if a frozen file changed.

## You must not read
- The holdout set. It lives outside the repo and is scored only by a human, once per candidate, after climbing stops. A hook blocks it.

## Success
- Primary metric: `{{METRIC}}`. Target: {{TARGET}}.
- Guards (a change that breaks one is rejected): {{GUARDS}}.
- Budget: at most {{BUDGET}} attempts. Stop early after {{STAGNATION}} rejected attempts in a row.

## Loop
1. `python hillclimb/hc.py status` to see the current best and the target.
2. Read the failures from the last dev run (`hillclimb/runs/<latest>/results.jsonl`).
3. Pick one failure pattern and make one focused change to the editable files.
4. `python hillclimb/hc.py run --label <short-name>`. It runs dev {{REPEAT}} times and prints a verdict against the current best.
5. KEEP: `git add {{EDITABLE_PATHS}} && git commit -m "hillclimb: <short-name>"`. REJECT: `git checkout -- {{EDITABLE_PATHS}}`.
6. Record every attempt, kept or rejected: `python hillclimb/hc.py record --label <short-name> --decision kept|rejected --title "<what changed>" --reason "<numbers and why>"`.
7. Stop when the target is reached, the budget is spent, or `status` reports STAGNATION. Then report: what was kept, the score path, what still fails and why.

## Constraints
- Fix the general cause. Do not special-case case IDs or copy expected values from `hillclimb/data/` into the feature.
- A rejected verdict stands, even if the change looks right. Explain it in the ledger instead.
{{CONSTRAINTS}}
