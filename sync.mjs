#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const SKILLS = path.join(ROOT, 'skills');
const STATE = path.join(ROOT, '.state');
const LOG = path.join(STATE, 'watch.log');
const STATUS = path.join(STATE, 'status.json');
const HEARTBEAT = path.join(STATE, 'heartbeat.json');
const CONFIG = path.join(ROOT, 'carrstack.json');
const SELF = fileURLToPath(import.meta.url);
const IS_WIN = process.platform === 'win32';
const IS_MAC = process.platform === 'darwin';
const DEBOUNCE_MS = 3000;
const PULL_MS = 5 * 60 * 1000;
const HEARTBEAT_MS = 60 * 1000;
const STALE_MS = 3 * HEARTBEAT_MS;
const MARK_START = '<!-- carrstack:start -->';
const MARK_END = '<!-- carrstack:end -->';
const PIPE = IS_WIN ? `\\\\.\\pipe\\carrstack-sync-${os.userInfo().username}` : path.join(STATE, 'watch.sock');
const STARTUP = IS_WIN && process.env.APPDATA
  ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'carrstack-sync.vbs')
  : null;
const LAUNCH_LABEL = 'com.carrstack.sync';
const LAUNCH_AGENT = path.join(os.homedir(), 'Library', 'LaunchAgents', `${LAUNCH_LABEL}.plist`);
const GIT_ENV = { ...process.env, GIT_TERMINAL_PROMPT: '0', GCM_INTERACTIVE: 'never' };

const home = (envVar, fallback) => process.env[envVar] || path.join(os.homedir(), fallback);
const CLAUDE_DIR = home('CLAUDE_CONFIG_DIR', '.claude');
const CODEX_DIR = home('CODEX_HOME', '.codex');
const TARGETS = [path.join(CLAUDE_DIR, 'skills'), path.join(CODEX_DIR, 'skills')];
const THEMES = path.join(ROOT, 'themes');
// T3 Code publishes every <id>.json in this folder as a theme. It accepts a linked folder, not linked files.
const T3_USERDATA = process.env.T3_USERDATA_DIR || path.join(os.homedir(), '.t3', 'userdata');
const T3_THEMES = path.join(T3_USERDATA, 'themes');
const GEMINI_DIR = home('GEMINI_HOME', '.gemini'); // Gemini CLI and Antigravity read GEMINI.md here
const OPENCODE_DIR = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'opencode');
// Each file is only written when its tool's folder exists on this machine.
const INSTRUCTION_FILES = [
  path.join(CLAUDE_DIR, 'CLAUDE.md'),
  path.join(CODEX_DIR, 'AGENTS.md'),
  path.join(GEMINI_DIR, 'GEMINI.md'),
  path.join(OPENCODE_DIR, 'AGENTS.md'),
];

fs.mkdirSync(STATE, { recursive: true });

function git(...args) {
  return execFileSync('git', args, {
    cwd: ROOT,
    encoding: 'utf8',
    env: GIT_ENV,
    timeout: 60_000,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trimEnd();
}

function log(message) {
  try {
    if (fs.existsSync(LOG) && fs.statSync(LOG).size > 512 * 1024) fs.renameSync(LOG, `${LOG}.old`);
    fs.appendFileSync(LOG, `${new Date().toISOString()} ${message}\n`);
  } catch {}
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function setStatus(state, message) {
  fs.writeFileSync(STATUS, `${JSON.stringify({ time: new Date().toISOString(), state, message }, null, 2)}\n`);
  log(`${state}: ${message}`);
}

const samePath = (a, b) => (IS_WIN ? a.toLowerCase() === b.toLowerCase() : a === b);

function realOrNull(p) {
  try {
    return fs.realpathSync.native(p);
  } catch {
    return null;
  }
}

function linkTarget(p) {
  try {
    return path.resolve(path.dirname(p), fs.readlinkSync(p).replace(/^\\\\\?\\/, ''));
  } catch {
    return null;
  }
}

function isInside(child, parent) {
  const rel = path.relative(parent, child);
  return rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel);
}

function removeLink(p) {
  try {
    fs.unlinkSync(p);
  } catch {
    fs.rmdirSync(p);
  }
}

function backup(dir, label) {
  const dest = path.join(STATE, 'backups', `${label}-${path.basename(dir)}-${Date.now()}`);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  try {
    fs.renameSync(dir, dest);
  } catch {
    fs.cpSync(dir, dest, { recursive: true });
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return dest;
}

function skillNames() {
  return fs.readdirSync(SKILLS, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name);
}

function link() {
  const notes = [];
  const names = skillNames();
  const retired = readJson(CONFIG, {}).retired ?? [];
  for (const target of TARGETS) {
    fs.mkdirSync(target, { recursive: true });
    const label = path.basename(path.dirname(target)).replace(/^\./, '');
    for (const name of names) {
      const src = path.join(SKILLS, name);
      const dest = path.join(target, name);
      let stat = null;
      try {
        stat = fs.lstatSync(dest);
      } catch {}
      if (stat?.isSymbolicLink()) {
        const real = realOrNull(dest);
        if (real && samePath(real, realOrNull(src))) continue;
        removeLink(dest);
      } else if (stat) {
        notes.push(`backed up ${dest} to ${backup(dest, label)}`);
      }
      fs.symlinkSync(src, dest, IS_WIN ? 'junction' : 'dir');
      notes.push(`linked ${dest}`);
    }
    for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
      const dest = path.join(target, entry.name);
      const stat = fs.lstatSync(dest);
      if (stat.isSymbolicLink()) {
        const to = linkTarget(dest);
        if (to && isInside(to, SKILLS) && !fs.existsSync(to)) {
          removeLink(dest);
          notes.push(`removed stale link ${dest}`);
        }
      } else if (stat.isDirectory() && retired.includes(entry.name)) {
        notes.push(`retired ${dest}, backed up to ${backup(dest, label)}`);
      }
    }
  }
  return notes;
}

// Points T3 Code's themes folder at the repo. Skipped on machines without T3 Code.
function linkThemes() {
  const notes = [];
  if (!fs.existsSync(T3_USERDATA)) return notes;
  fs.mkdirSync(THEMES, { recursive: true });
  let stat = null;
  try {
    stat = fs.lstatSync(T3_THEMES);
  } catch {}
  if (stat?.isSymbolicLink()) {
    const real = realOrNull(T3_THEMES);
    if (real && samePath(real, realOrNull(THEMES))) return notes;
    removeLink(T3_THEMES);
  } else if (stat?.isDirectory()) {
    // Keep themes already published on this machine: move them into the repo unless one there has the same id.
    for (const name of fs.readdirSync(T3_THEMES)) {
      const src = path.join(T3_THEMES, name);
      const dest = path.join(THEMES, name);
      if (!name.endsWith('.json') || !fs.lstatSync(src).isFile() || fs.existsSync(dest)) continue;
      fs.copyFileSync(src, dest);
      notes.push(`moved theme ${name} into the repo`);
    }
    notes.push(`backed up ${T3_THEMES} to ${backup(T3_THEMES, 't3')}`);
  } else if (stat) {
    notes.push(`backed up ${T3_THEMES} to ${backup(T3_THEMES, 't3')}`);
  }
  fs.symlinkSync(THEMES, T3_THEMES, IS_WIN ? 'junction' : 'dir');
  notes.push(`linked ${T3_THEMES}`);
  return notes;
}

function linkProblems() {
  const problems = [];
  for (const target of TARGETS) {
    for (const name of skillNames()) {
      const dest = path.join(target, name);
      const real = realOrNull(dest);
      if (!real || !samePath(real, realOrNull(path.join(SKILLS, name)))) problems.push(`${dest} is not linked to the repo`);
    }
  }
  if (fs.existsSync(T3_USERDATA)) {
    const real = realOrNull(T3_THEMES);
    if (!real || !samePath(real, realOrNull(THEMES) ?? '')) problems.push(`${T3_THEMES} is not linked to the repo`);
  }
  return problems;
}

function commitLocal() {
  const dirty = git('status', '--porcelain');
  if (!dirty) return 0;
  const files = dirty.split('\n').map((l) => l.slice(3).replace(/^"|"$/g, ''));
  const skills = [...new Set(files.map((f) => (f.startsWith('skills/') ? f.split('/')[1] : path.basename(f))))];
  git('add', '-A');
  const list = skills.length > 3 ? `${skills.slice(0, 3).join(', ')} and ${skills.length - 3} more` : skills.join(', ');
  git('commit', '-q', '-m', `update ${list} from ${os.hostname()}`);
  return files.length;
}

let blocked = false;

function exchange(reason) {
  if (blocked) return readJson(STATUS, null);
  try {
    commitLocal();
    try {
      git('fetch', '-q');
    } catch (e) {
      setStatus('offline', `fetch failed, will retry: ${(e.stderr || e.message).trim()}`);
      return readJson(STATUS, null);
    }
    const [ahead, behind] = git('rev-list', '--left-right', '--count', 'HEAD...@{u}').split(/\s+/).map(Number);
    if (ahead && behind) {
      try {
        git('rebase', '-q', '@{u}');
      } catch {
        try {
          git('rebase', '--abort');
        } catch {}
        blocked = true;
        setStatus('error', `conflict: edits here clash with another machine. Run \`git pull --rebase\` in ${ROOT}, resolve, then \`node sync.mjs --restart\`.`);
        return readJson(STATUS, null);
      }
    } else if (behind) {
      git('merge', '-q', '--ff-only', '@{u}');
    }
    if (ahead) {
      try {
        git('push', '-q');
      } catch (e) {
        setStatus('offline', `push failed, will retry: ${(e.stderr || e.message).trim()}`);
        return readJson(STATUS, null);
      }
    }
    const notes = [...link(), ...linkThemes()];
    writeInstructions();
    for (const n of notes) log(n);
    const parts = [reason];
    if (behind) parts.push(`pulled ${behind}`);
    if (ahead) parts.push(`pushed ${ahead}`);
    if (notes.length) parts.push(`${notes.length} link change(s)`);
    setStatus('ok', parts.join(', '));
  } catch (e) {
    setStatus('error', `${reason}: ${(e.stderr || e.message).trim()}`);
  }
  return readJson(STATUS, null);
}

function askWatcher(command = 'pid') {
  return new Promise((resolve) => {
    const sock = net.connect(PIPE);
    let reply = '';
    sock.setTimeout(command === 'sync' ? 120_000 : 2000, () => sock.destroy());
    sock.on('connect', () => sock.end(command));
    sock.on('data', (d) => (reply += d));
    sock.on('close', () => resolve(reply || null));
    sock.on('error', () => resolve(null));
  });
}

function watch() {
  const server = net.createServer((sock) => {
    sock.on('error', () => {});
    sock.once('data', (d) => {
      const cmd = String(d).trim();
      if (cmd === 'stop') {
        log('stopped by request');
        sock.end('stopping', () => process.exit(0));
      } else if (cmd === 'sync') {
        sock.end(JSON.stringify(exchange('manual sync')));
      } else {
        sock.end(String(process.pid));
      }
    });
  });

  const listen = () => {
    server.once('error', async (e) => {
      if (e.code !== 'EADDRINUSE') throw e;
      if (await askWatcher()) {
        console.log('watcher already running');
        process.exit(0);
      }
      fs.rmSync(PIPE, { force: true });
      listen();
    });
    server.listen(PIPE, start);
  };

  const beat = () => {
    try {
      fs.writeFileSync(HEARTBEAT, `${JSON.stringify({ time: new Date().toISOString(), pid: process.pid })}\n`);
    } catch {}
  };

  let timer = null;
  const onEdit = (file) => {
    if (!file) return;
    const rel = file.split(path.sep).join('/');
    if (rel === '.git' || rel.startsWith('.git/') || rel === '.state' || rel.startsWith('.state/')) return;
    clearTimeout(timer);
    timer = setTimeout(() => exchange(`edit ${rel}`), DEBOUNCE_MS);
  };

  function start() {
    beat();
    setInterval(beat, HEARTBEAT_MS);
    exchange('startup');
    fs.watch(ROOT, { recursive: true }, (_event, file) => onEdit(file)).on('error', (e) => {
      setStatus('error', `file watch failed, run \`node sync.mjs --restart\`: ${e.message}`);
    });
    setInterval(() => exchange('poll'), PULL_MS);
    log(`watching ${ROOT} (pid ${process.pid})`);
  }

  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => process.exit(0));
  process.on('exit', () => fs.rmSync(HEARTBEAT, { force: true }));
  listen();
}

function startWatcher() {
  const child = spawn(process.execPath, [SELF, '--watch'], { cwd: ROOT, detached: true, stdio: 'ignore', windowsHide: true });
  child.unref();
  console.log(`started watcher (pid ${child.pid})`);
}

async function stopWatcher() {
  if ((await askWatcher('stop')) === 'stopping') console.log('stopped watcher');
}

const xml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function installAutostart() {
  if (IS_WIN) {
    const q = (s) => `""${s}""`;
    fs.writeFileSync(STARTUP, `CreateObject("WScript.Shell").Run "${q(process.execPath)} ${q(SELF)} --watch", 0, False\r\n`);
    console.log(`login launcher: ${STARTUP}`);
  } else if (IS_MAC) {
    const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LAUNCH_LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>${xml(process.execPath)}</string><string>${xml(SELF)}</string><string>--watch</string></array>
  <key>WorkingDirectory</key><string>${xml(ROOT)}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>${xml(process.env.PATH ?? '/usr/bin:/bin')}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>${xml(path.join(STATE, 'launchd.log'))}</string>
</dict>
</plist>
`;
    fs.mkdirSync(path.dirname(LAUNCH_AGENT), { recursive: true });
    fs.writeFileSync(LAUNCH_AGENT, plist);
    console.log(`login agent: ${LAUNCH_AGENT}`);
  } else {
    console.log(`Start the watcher at login yourself, e.g. crontab -e:\n  @reboot ${process.execPath} ${SELF} --watch`);
  }
}

function removeAutostart() {
  if (STARTUP && fs.existsSync(STARTUP)) fs.unlinkSync(STARTUP);
  if (IS_MAC && fs.existsSync(LAUNCH_AGENT)) {
    spawnSync('launchctl', ['bootout', `gui/${os.userInfo().uid}/${LAUNCH_LABEL}`], { stdio: 'ignore' });
    fs.unlinkSync(LAUNCH_AGENT);
  }
}

function instructionBlock() {
  const root = ROOT.split(path.sep).join('/');
  // Extra shared rules, edited as plain markdown in the repo.
  const extraFile = path.join(ROOT, 'instructions.md');
  const extra = fs.existsSync(extraFile) ? `\n${fs.readFileSync(extraFile, 'utf8').replace(/\r\n/g, '\n').trim()}\n` : '';
  return `${MARK_START}
## Skills sync (carrStack)

Personal skills live in \`${root}/skills\` (github.com/SeanC818/carrStack). Each
one in \`~/.claude/skills\` and \`~/.codex/skills\` is a link into that folder, so
editing a skill in either place edits the repo. Create new skills in
\`${root}/skills/<name>\`.

A background watcher commits and pushes edits there, pulls edits made on other
machines, and links new skills. The user cannot see its health, so after editing
a skill run \`node "${root}/sync.mjs" --status\`. If the watcher is not running,
run \`node "${root}/sync.mjs"\`, which commits, pulls, pushes and links once. If it
reports any other problem, tell the user.

## T3 Code themes

\`~/.t3/userdata/themes\` is a link to \`${root}/themes\`, so a theme published
with \`t3_theme_set\` is saved to the repo and synced to the user's other
machines, where it appears in T3 Code's Settings → Appearance. Reuse the
theme's id when changing it, so the same file updates instead of a new theme.

## Lifeboard

The user keeps their to-dos, reminders, events and daily brief on Lifeboard, a
personal board with an MCP server at https://lifeboard.seancarr818.workers.dev/mcp.
When they mention a task, reminder, deadline, their day, or ask you to "add" or
"track" something, use the \`lifeboard\` skill and its MCP tools.
${extra}${MARK_END}`;
}

function writeInstructions(remove = false) {
  for (const file of INSTRUCTION_FILES) {
    if (!fs.existsSync(path.dirname(file))) continue;
    const text = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
    const eol = text.includes('\r\n') ? '\r\n' : '\n';
    const block = remove ? '' : instructionBlock().replace(/\n/g, eol);
    const start = text.indexOf(MARK_START);
    const end = text.indexOf(MARK_END);
    let next;
    if (start >= 0 && end > start) {
      next = text.slice(0, start) + block + text.slice(end + MARK_END.length);
      if (remove) next = next.replace(/(\r?\n){3,}$/, eol).replace(/(\r?\n)+$/, eol);
    } else if (remove) {
      continue;
    } else {
      next = text ? `${text.replace(/(\r?\n)*$/, '')}${eol}${eol}${block}${eol}` : `${block}${eol}`;
    }
    if (next !== text) {
      fs.writeFileSync(file, next);
      console.log(`updated: ${file}`);
    }
  }
}

async function status() {
  const pid = await askWatcher();
  const beat = readJson(HEARTBEAT, null);
  const last = readJson(STATUS, null);
  let ok = true;
  if (!pid) {
    ok = false;
    console.log('watcher NOT running: run `node sync.mjs` after edits, or `node sync.mjs --restart`');
  } else if (!beat || Date.now() - Date.parse(beat.time) > STALE_MS) {
    ok = false;
    console.log(`watcher (pid ${pid}) is not writing its heartbeat: run \`node sync.mjs --restart\``);
  } else {
    console.log(`watcher running (pid ${pid})`);
  }
  if (last) {
    console.log(`last: ${last.time} ${last.state} ${last.message}`);
    if (last.state !== 'ok') ok = false;
  }
  try {
    const dirty = git('status', '--porcelain');
    const [ahead, behind] = git('rev-list', '--left-right', '--count', 'HEAD...@{u}').split(/\s+/).map(Number);
    if (dirty || ahead || behind) console.log(`repo: ${dirty ? 'uncommitted edits, ' : ''}${ahead} ahead, ${behind} behind (as of last fetch)`);
  } catch (e) {
    ok = false;
    console.log(`repo: ${(e.stderr || e.message).trim()}`);
  }
  const problems = linkProblems();
  for (const p of problems) console.log(`link: ${p}`);
  if (problems.length) ok = false;
  process.exit(ok ? 0 : 1);
}

const args = process.argv.slice(2);

if (args.includes('--watch')) {
  watch();
} else if (args.includes('--status')) {
  await status();
} else if (args.includes('--install')) {
  for (const n of [...link(), ...linkThemes()]) console.log(n);
  writeInstructions();
  installAutostart();
  await stopWatcher();
  if (IS_MAC) {
    spawnSync('launchctl', ['bootout', `gui/${os.userInfo().uid}/${LAUNCH_LABEL}`], { stdio: 'ignore' });
    const r = spawnSync('launchctl', ['bootstrap', `gui/${os.userInfo().uid}`, LAUNCH_AGENT], { encoding: 'utf8' });
    if (r.status !== 0) {
      console.log(`launchctl bootstrap failed (${r.stderr?.trim()}); starting directly`);
      startWatcher();
    } else {
      console.log('started watcher via launchd');
    }
  } else {
    startWatcher();
  }
} else if (args.includes('--restart')) {
  await stopWatcher();
  startWatcher();
} else if (args.includes('--stop')) {
  await stopWatcher();
} else if (args.includes('--uninstall')) {
  await stopWatcher();
  removeAutostart();
  writeInstructions(true);
  console.log('watcher stopped and removed from login. Skill links were left in place.');
} else {
  const reply = await askWatcher('sync');
  const result = reply ? readJson(STATUS, null) : exchange('manual sync');
  console.log(result ? `${result.state}: ${result.message}` : 'no result');
  process.exit(result?.state === 'ok' ? 0 : 1);
}
