---
name: hillclimb
description: Set up a hill climb (eval-driven improvement loop) for any feature in any repo. Use when the user says "hillclimb", "hill climb", "set up evals so an agent can improve X", or wants an agent to iterate on a feature against a score. Interviews for the feature, the evals and the target result, scaffolds a frozen grader with a dev/holdout split, a guard hook, a ledger and the loop rules, scores a baseline, then offers to start climbing.
---

# hillclimb

A hill climb: an agent makes one change at a time, a frozen grader scores it,
and the change is kept only if it beats the noise without breaking a guard.
This skill sets that up for any stack. The runner is Python stdlib only; it
reaches the feature through a command or an HTTP endpoint.

Templates are in this skill's `templates/` folder. Copy them; don't rewrite them.

## 0. Preconditions

- The repo is a git repo with a clean working tree (`git status --short`). If
  not, stop and ask. The loop reverts with `git checkout`.
- `python --version` works (3.9+).
- If `hillclimb/` already exists, run `python hillclimb/hc.py status` and ask
  whether to resume, extend the evals, or start over. Never overwrite it silently.

## 1. Interview

Ask one topic at a time. Use AskUserQuestion when you can offer options, and
plain questions otherwise. Read the code before asking anything the repo
already answers, and propose answers from it.

**A. Feature**
1. What should get better, in one sentence? This becomes `goal`.
2. Where is it in the code? Find the entry point yourself and confirm.
3. How do we run one case? Pick one:
   - `command`: a CLI/script that reads JSON on stdin and prints JSON (or text) on stdout.
   - `http`: a running endpoint taking a JSON POST. Auth headers come only from env vars (`headers_env`), never values in config.
   - Neither exists: write `hillclimb/adapter.py`, a thin script that imports
     or calls the feature. It becomes frozen.
4. Which files may the agent change (`editable`)? Keep it narrow: the prompt,
   the logic module, the config. Everything else is off limits.
5. Anything else that must stay fixed (spec docs, reference data)? Add to `frozen`.
6. Must the output use only the provided data (no outside model knowledge)?
   If yes, add that as a constraint and give at least a few cases a check
   that catches invented facts.

**B. Evals**
1. Do labelled cases already exist? If yes, convert them to the case format.
2. If not, draft them together:
   - Ask for 3–5 real examples of input and the right output, and for the
     failures they've already seen.
   - Draft 20–40 cases: happy paths, edge cases and each known failure.
     Prefer real inputs; mark any invented ones.
   - Show the user the draft (a table of id, input summary, checks). Get
     approval before going on. They own the answer key.
3. How is a case judged? Map each expectation to a check type (below). Use
   `command` with `hillclimb/judge.py` only when a plain check can't express
   it, and tell the user that an LLM judge adds noise.
4. Split about 2:1 into dev and holdout, spread across case types. Holdout
   needs at least 8 cases.

**C. Results**
1. Primary metric: `check_rate` (share of checks passed, the default) or
   `case_rate` (share of cases fully right). Or `errors` / `latency_p50_ms` /
   `latency_p95_ms` for speed or reliability climbs.
2. Target value, for example check_rate ≥ 0.95.
3. Guards that must not get worse: errors (default `max_worse: 0`), latency
   (for example `max_worse_pct: 25`), or another metric.
4. Budget: max attempts (default 10), repeats per run for noise (default 3,
   or 1 if the feature is deterministic), stop after N rejects in a row (default 3).

Finish with a one-screen summary of A–C and get a yes before writing files.

## 2. Case format

`hillclimb/data/dev.jsonl` and the holdout file, one JSON object per line:

```json
{"id": "refund-01", "input": {"ticket": "..."}, "checks": [
  {"type": "equals", "path": "team", "value": "billing"},
  {"type": "contains", "path": "reply", "value": "refund", "ignore_case": true}
]}
```

`input` is sent as-is (JSON on stdin, or the POST body). `path` is a dot path
into the JSON output (`items.0.name`); leave it out to check the whole output.

| type | fields | passes when |
| --- | --- | --- |
| `equals` | path, value | the value is equal |
| `one_of` | path, values | the value is in the list |
| `contains` / `not_contains` | path?, value, ignore_case? | the substring is (not) present |
| `regex` | path?, pattern, ignore_case? | the pattern matches |
| `number_between` | path, min?, max? | the number is in range |
| `max_latency_ms` | value | the call was fast enough |
| `command` | run (argv), timeout_s? | the script gets `{case, output, latency_ms}` on stdin and prints `{"pass": bool, "reason": "..."}` |

## 3. Scaffold

In the target repo:

1. `hillclimb/hc.py`: copy `templates/hc.py`.
2. `hillclimb/config.json`: follow `templates/config.example.json`. `name` is a
   kebab-case slug. Leave out `holdout_path` unless the user wants a
   different place; the default is `~/.hillclimb/<name>/holdout.jsonl`.
3. `hillclimb/data/dev.jsonl`: the dev cases.
4. Holdout cases go to `~/.hillclimb/<name>/holdout.jsonl`, outside the repo,
   so no search or git history can show them to the agent. Tell the user that
   teammates need the file shared separately, or `HC_HOLDOUT` pointing at it.
5. `hillclimb/adapter.py` and `hillclimb/judge.py` if needed. Secrets come from
   env vars only; add the var names to `.env.example` if the repo has one.
6. `hillclimb/HILLCLIMB.md`: fill in `templates/HILLCLIMB.md`. Replace every
   `{{...}}` and delete lines that don't apply.
7. `hillclimb/LEDGER.md`:
   ```
   # Ledger: <name>

   | Attempt | What changed | <metric> per run | Errors | Decision | Reason |
   | --- | --- | --- | --- | --- | --- |
   ```
8. Add `hillclimb/runs/` to `.gitignore`. Keep `runs.csv`, `decisions.json`
   and `LEDGER.md` tracked; they are the climb's history.
9. Point to the rules from the agent instructions: append
   `See hillclimb/HILLCLIMB.md before changing <feature>.` to `AGENTS.md`
   (create it if missing), and make sure `CLAUDE.md` includes `@AGENTS.md`.
   Edit these files; don't overwrite them.

## 4. Baseline (before the guard is installed)

1. Smoke test: `python hillclimb/hc.py run --label smoke --limit 2`. Fix the
   adapter or config until both cases run without errors. Failing checks are
   fine; errors are not.
2. Dev baseline: `python hillclimb/hc.py run --label baseline`.
3. Holdout baseline: `python hillclimb/hc.py run --set holdout --label holdout-baseline`.
   It records totals only, no per-case output.
4. If the baseline already meets the target, or scores 0, stop and review the
   cases with the user. The evals are too easy or broken.
5. `python hillclimb/hc.py record --label baseline --decision baseline --title "Baseline" --reason "Starting point."`
6. `python hillclimb/hc.py freeze`, then `python hillclimb/hc.py verify`.

## 5. Guard (Claude Code)

1. Copy `templates/hillclimb_guard.py` to `.claude/hooks/hillclimb_guard.py`.
2. Merge this into `.claude/settings.json`, keeping existing keys:
   ```json
   {
     "permissions": { "deny": ["Edit(./hillclimb/hc.py)", "Edit(./hillclimb/config.json)", "Edit(./hillclimb/data/**)", "Edit(./.claude/**)"] },
     "hooks": { "PreToolUse": [ { "matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob|Bash|PowerShell",
       "hooks": [ { "type": "command", "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/hillclimb_guard.py\"", "timeout": 10 } ] } ] }
   }
   ```
3. Test the hook by piping fake events into it. Each must print a deny:
   - Read the holdout path.
   - Edit `hillclimb/data/dev.jsonl`.
   - Bash `python hillclimb/hc.py run --set holdout --label x`.
   - Bash `python hillclimb/hc.py freeze`.

   And each must stay silent: Edit an editable file, and Bash `python hillclimb/hc.py run --label x`.
4. Codex and other agents don't run Claude hooks. For them, the protection is
   the rules in `HILLCLIMB.md` plus the `hc.py verify` check before every
   scored run. Say so.

Commit the scaffold: `git add hillclimb .claude AGENTS.md CLAUDE.md .gitignore && git commit -m "hillclimb: set up <name>"`.

## 6. Hand over and offer to climb

Tell the user:
- the baseline numbers (dev mean ± spread, holdout), the target and the budget
- the files created
- the commands: `run`, `status`, `record`, plus the holdout run that only they do
- the step prompt, in a code block:
  ```
  Read hillclimb/HILLCLIMB.md and follow the loop. Make one focused change per attempt, record every attempt, and stop at the target, the budget, or STAGNATION. Then report what was kept, the score path and what still fails.
  ```

Then ask whether to start climbing now. This session has seen the holdout
cases, so it must not climb itself. If yes, start a fresh subagent (Agent tool,
foreground) with the step prompt and the repo path, and relay its report. When
it stops, offer to run the holdout on the final candidate:
`python hillclimb/hc.py run --set holdout --label holdout-<best>`.
If holdout drops well below dev, say the climb overfit the dev set.

## Rules

- Never weaken a check, edit cases or re-freeze to make a change pass. Changing
  the evals is a user decision, recorded in the ledger with a new baseline.
- A KEEP verdict needs a gain larger than the measured noise (spread between
  repeats, at least one check). Don't argue a REJECT into a KEEP.
- No secrets in `config.json`, cases or the ledger.
- Comments are not allowed in generated code.
