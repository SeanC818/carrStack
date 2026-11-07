# CarrStack

Sean Carr's private collection of agent skills, based on
[Theo Browne's tstack](https://github.com/t3dotgg/tstack).
Original MIT license and upstream history are preserved.

## This computer

- Source and T3 Code project: `/Users/seancarr/projects/carrStack`
- Private GitHub repository: `https://github.com/SeanC818/carrStack`
- Codex installation: `~/.codex/skills/`
- Claude Code installation: `~/.claude/skills/`
- `origin` points to CarrStack; `upstream` points to `t3dotgg/tstack`.

All nine skills are installed globally, so they can be used across projects.
They are copies: after editing a skill in this repository, copy it into both
installation directories to activate the change. From this repository:

```bash
cp -R skills/. ~/.codex/skills/
cp -R skills/. ~/.claude/skills/
```

Codex will discover newly installed skills on the next turn. Start a new
Claude Code session to load its skills. Examples: `full stop`, `file a PR`,
`sol loop`, or `council`. `full send` includes merging a PR; `full stop`
leaves the merge for you.

To bring in upstream updates, start with a clean working tree, run
`git fetch upstream`, then `git merge upstream/main`. Review and resolve
any conflicts, copy the updated skills into both installations, and push
your changes to `origin`.

Keep personal model preferences in project `AGENTS.md` or `CLAUDE.md` files,
as upstream recommends. Cross-provider reviews need the relevant providers
configured in T3 Code.

## Upstream documentation

The agent skills I use every day, cleaned up so anyone can use them. They work
in Claude Code and Codex. Some use [T3 Code](https://github.com/pingdotgg/t3code)
features when they are available and fall back to native tools when they are
not.

## Skills

| Skill | Say | What it does |
|---|---|---|
| `full-send` | "full send" | Takes a change to a merged PR with nobody watching: proves it, reviews it, files it, babysits it, merges it. |
| `full-stop` | "full stop" | Same as `full-send`, but stops when the PR is ready for you to merge. |
| `council` | "council" | Gets review from three models from different providers, and loops until they agree. |
| `sol-loop` | "sol loop" | Reviews a change with GPT Sol in a loop until both agents agree. |
| `file-pr` | "file a PR" | Files a short PR that leads with the problem, not an inventory of changes. |
| `takeover` | "take over" | Finishes someone else's PR, branch, or agent thread, and keeps their credit. |
| `babysit-pr` | "babysit" | Watches a PR through CI and review bots, and fixes the real findings. |
| `modernize` | "modernize" | Rebases an old PR and decides if it should still exist. |
| `leaving-pr-comments` | (automatic) | Formats comments that an agent posts on your behalf. |

Some skills call others. Install the ones they need too:

- `full-send` uses `sol-loop`, `file-pr`, and `babysit-pr`.
- `full-stop` uses `full-send`.
- `takeover` uses `modernize`, `file-pr`, `babysit-pr`, and `leaving-pr-comments`.
- `file-pr`, `babysit-pr`, and `modernize` use `leaving-pr-comments`.

## Install

```bash
git clone https://github.com/t3dotgg/tstack
cp -R tstack/skills/* ~/.claude/skills/   # Claude Code
cp -R tstack/skills/* ~/.codex/skills/    # Codex
```

## Requirements

- An authenticated [GitHub CLI](https://cli.github.com) (`gh`).
- `python3` for `babysit-pr`'s `pr-wait` script.
- `council` and `sol-loop` need subagents on other providers' models. T3 Code
  does this with `delegate_task`. Otherwise you need a harness that can run
  those models.

## Make them yours

These are starting points. Edit them. Put personal settings, like which models
sit on your council, in your `CLAUDE.md` or `AGENTS.md`, so you can update the
skills without losing them.

## License

[MIT](LICENSE)
