# CarrStack

Sean Carr's private collection of agent skills

## How syncing works

GitHub is the source of truth. Each machine has a clone, and every skill in
`~/.claude/skills/` and `~/.codex/skills/` is a link into the clone's
`skills/` folder (a directory junction on Windows, a symlink on macOS). Editing
a skill in either place edits the repo.

A background watcher on each machine:

- commits and pushes edits a few seconds after they settle,
- pulls edits from other machines every 5 minutes,
- links new skills and removes links to deleted ones.

It never merges. If two machines edit the same lines, it stops and
`node sync.mjs --status` says so. Resolve with `git pull --rebase`, then
`node sync.mjs --restart`.

Skills that are not in this repository are left alone. Skill folders listed
under `retired` in `carrstack.json` are backed up to `.state/backups/` and
removed.

| Machine | Clone |
|---|---|
| Mac | `/Users/seancarr/projects/carrStack` |
| Windows (work) | `C:\Users\Sean Carr\carrStack` |
| Windows (second PC) | wherever you clone it |

## Setup on a machine

Needs `node` and `git` with push access to this repo.

```bash
git clone https://github.com/SeanC818/carrStack
node carrStack/sync.mjs --install
```

`--install` links the skills, backing up any existing skill folder with the
same name to `.state/backups/`. It adds a marked section to `~/.claude/CLAUDE.md`
and `~/.codex/AGENTS.md` that tells agents how the sync works, and starts the
watcher at login: a hidden Startup-folder launcher on Windows, a LaunchAgent on
macOS. Re-run it after moving the clone.

## Commands

```bash
node sync.mjs              # commit, pull, push and link now
node sync.mjs --status     # watcher health, repo state, broken links
node sync.mjs --restart    # restart the watcher, e.g. after resolving a conflict
node sync.mjs --stop
node sync.mjs --uninstall  # stop the watcher and remove it from login
```

Start a new Claude Code session to load skill changes. Codex picks them up on
the next turn.

## Skills

Every skill works with GitHub and Azure DevOps. Skills that differ by platform
check `git remote -v` and read `references/github.md` or
`references/azure-devops.md`.

| Skill | Say | What it does |
|---|---|---|
| `full-stop` | "full stop" | Completes, validates, reviews, and prepares a PR for you to merge. |
| `council` | "council" | Gets review from three models from different providers, and loops until they agree. |
| `sol-loop` | "sol loop" | Reviews a change with GPT Sol in a loop until both agents agree. |
| `file-pr` | "file a PR" | Files a short PR that leads with the problem, not an inventory of changes. |
| `takeover` | "take over" | Finishes someone else's PR, branch, or agent thread, and keeps their credit. |
| `babysit-pr` | "babysit" | Watches a PR through CI and review bots, and fixes the real findings. |
| `modernize` | "modernize" | Rebases an old PR and decides if it should still exist. |
| `leaving-pr-comments` | (automatic) | Formats comments that an agent posts on your behalf. |

Some skills call others:

- `full-stop` uses `sol-loop`, `file-pr`, and `babysit-pr`.
- `takeover` uses `modernize`, `file-pr`, `babysit-pr`, and `leaving-pr-comments`.
- `file-pr`, `babysit-pr`, and `modernize` use `leaving-pr-comments`.

Keep personal model preferences in project `AGENTS.md` or `CLAUDE.md` files.
Cross-provider reviews need the relevant providers configured in T3 Code.

## Requirements

- GitHub: an authenticated [GitHub CLI](https://cli.github.com) (`gh`), and
  `python3` for `babysit-pr`'s `scripts/pr-wait`.
- Azure DevOps: the Azure CLI with the `azure-devops` extension, signed in with
  `az login`, and `python` for `babysit-pr`'s `scripts/pr-wait-ado.py`.
- `council` and `sol-loop` need subagents on other providers' models. T3 Code
  does this with `delegate_task`.

## License

[MIT](LICENSE)
