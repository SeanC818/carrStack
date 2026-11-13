---
name: lifeboard
description: Use when the user mentions their board, Lifeboard, to-dos, tasks, reminders, deadlines, "add this to my list", "what's on today", their day or week, or pastes a message to track. Reads and updates the user's personal kanban board through its MCP server.
---

# Lifeboard

Lifeboard is the user's personal life dashboard: one kanban board with work
and personal lanes, dated events, quick notes, and a daily "Today" brief.
It lives at https://lifeboard.seancarr818.workers.dev, and any agent can use it
through MCP at `https://lifeboard.seancarr818.workers.dev/mcp`.

## Connect

Use the `lifeboard` MCP tools if they are already loaded. In some harnesses
they are deferred, so search for them by name first.

If the tools are not available, say so and offer the one-time setup. Don't
work around it with curl.

- Claude Code: `claude mcp add --transport http --scope user lifeboard https://lifeboard.seancarr818.workers.dev/mcp`,
  then the user runs `/mcp` to sign in.
- Codex: `codex mcp add lifeboard --url https://lifeboard.seancarr818.workers.dev/mcp`,
  then `codex mcp login lifeboard`.
- claude.ai and ChatGPT: add a custom connector with the MCP URL in their settings.

Sign-in uses the user's passkey in the browser, so the user must do it. The
API token for scripts is in 1Password (Dev → Lifeboard → API_TOKEN). Never
print it, and never write it to a file or config.

## Model

| Thing | Use for | Fields |
|---|---|---|
| Card | Anything to do | `title`, `notes`, `status` (todo, doing, waiting, done), `lane` (work, personal), `priority` (low, normal, high), `due`, `snoozed_until`, `link` |
| Event | Something on a date that isn't a task: a meeting, birthday, renewal or deadline | `title`, `date`, `time`, `kind`, `lane` |
| Note | An idea or thing to remember with no action | `body`, `pinned` |
| Brief | Today's short markdown summary at the top of the board | `body`, up to 3 `focus` card ids |

Dates are `YYYY-MM-DD` in the user's timezone. `get_today` returns the
timezone and today's date, so work out "Friday" or "next week" from that.

## How to use it

- **Overview:** start with `get_today`. It returns what's overdue, due today or
  tomorrow, in progress, waiting on someone, and this week's events.
- **Adding:** search before you add (`search_cards`), so you update an existing
  card instead of creating a duplicate.
  - Pick the lane from context, and ask if it's unclear.
  - Only set a due date or high priority when the user gave one or clearly implied it.
- **Pasted messages** (Slack, email, Teams): make a card with a short summary
  title and the key ask in `notes`. Put a link in `link` if the user gave one.
- **Status:**
  - When the user says they've done something, `update_card` with `status: done`.
  - When they're blocked on someone, use `waiting`.
  - To push something later, use `snoozed_until` instead of changing the due date.
- **Removing:** `archive_card` is for cancelled items. Finished items are marked
  done instead.
- **Daily brief** (`set_today_brief`): short markdown with `## Focus` (at most 3
  items) and `## Heads-up`. It replaces today's brief, so read the current one first.
- **Confirming:** after changes, confirm in one line, e.g. "Added *Send Q4
  budget to Mark* (work, due Fri)." Don't dump JSON.

## Rules

- **Work content:** keep it to short summaries. Never copy confidential work
  content, customer data, credentials or secrets into cards or notes.
- **Bulk changes:** don't invent tasks. Don't bulk-change due dates, priorities
  or statuses unless asked.
- **Destructive actions:** confirm before archiving or deleting more than one
  item at once.
- **Your own changes:** everything you do is logged under your client's name
  (`recent_activity`), and the user can see it in Settings.
