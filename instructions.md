## Working rules

These come from a review of the user's agent sessions (Nov 2026). Each one fixes
a place where past sessions got stuck.

### Running a project locally

- When the user asks how to run something, look for a "How to run" section in
  the repo's README or AGENTS.md first. If there isn't one, write it, along with
  a single start script (e.g. `bin/dev`) and a `.env.example` listing every
  variable the project needs, with no values.
- Run commands and read the logs yourself rather than asking the user to paste
  terminal output back. Give them the commands only if they ask for them.
- For a 403 or CORS error in local dev, check these first: the frontend and API
  ports, the allowed CORS origins, and whether the request is sending the auth
  token.
- Never read `.env` files. Ask for variable names, not values.

### Database migrations

- Never hand-write or hand-edit EF Core migrations. Use `dotnet ef migrations
  add`, `dotnet ef migrations remove` and `dotnet ef database update`. The same
  goes for other ORMs: Prisma uses `prisma migrate dev`.

### Git

- Before switching branches, run `git worktree list`. Never check out a branch
  that is open in another worktree, including agent worktrees under
  `.claude/worktrees/`.
- `.claude/` and `.codex/` folders are local and stay untracked, except a
  `settings.json` or skills the project deliberately shares.
- When the user asks for commands to commit or push, give them the commands and
  a commit message. Offer to run them yourself.

### UI and visual work

- Before saying a visual change is done, look at it yourself in the browser,
  simulator or a screenshot, and send the user the screenshot.
- Ask for or use a reference (a screenshot, a link, an existing screen in the
  app) rather than guessing at the look.
- If three small tweaks haven't fixed a layout, stop tweaking. Rebuild a minimal
  version from a working reference screen, then add details back.
- Keep checks quick. Don't run full test tours or benchmarks for a visual
  change, and tell the user what you're waiting on while anything runs.

### Expo / React Native

- Before scaffolding or upgrading, check which SDK the current Expo Go app
  supports, and match it (or use a development build). Install native packages
  with `npx expo install`, not `npm install`.

### Project state

- In multi-session projects, keep a `STATUS.md` in the repo root: what's done,
  what's next, how to run it, and key decisions. Read it at the start of a
  session and update it after each slice of work, so "where are we?" never
  needs reconstructing.
