import json
import os
import re
import sys
from pathlib import Path


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


def norm(value):
    return str(value).replace("\\", "/").lower()


def load():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    cfg_path = root / "hillclimb" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {"name": "", "frozen": []}
    hold = os.environ.get("HC_HOLDOUT") or cfg.get("holdout_path") or f"~/.hillclimb/{cfg.get('name', '')}/holdout.jsonl"
    hold_dir = norm(os.path.dirname(os.path.expanduser(hold)))
    locked = ["hillclimb/hc.py", "hillclimb/config.json", "hillclimb/data/", "hillclimb/frozen.json", "hillclimb/runs.csv", "hillclimb/runs/", ".claude/"]
    locked += [norm(f) for f in cfg.get("frozen", [])]
    return hold_dir, locked


def check_path(tool, value, writing, hold_dir, locked):
    p = norm(os.path.expanduser(str(value)))
    if "holdout" in p or ".hillclimb/" in p or (hold_dir and hold_dir in p):
        deny(f"{tool} blocked: the holdout set is scored only by a human (hillclimb/HILLCLIMB.md).")
    if writing and any(p.endswith(l) or l in p for l in locked):
        deny(f"{tool} blocked: {value} is frozen. Change only the editable files listed in hillclimb/HILLCLIMB.md.")


def check_command(tool, command, hold_dir, locked):
    c = norm(command)
    if "holdout" in c or ".hillclimb" in c or (hold_dir and hold_dir in c) or "hc_holdout" in c:
        deny(f"{tool} blocked: the holdout set is scored only by a human (hillclimb/HILLCLIMB.md).")
    if re.search(r"\bhc\.py\s+(freeze|record\b.*--decision\s+baseline)", c):
        deny(f"{tool} blocked: freezing and recording the baseline are human steps.")
    writes = re.search(r"(>|\btee\b|\bsed\s+-i|\bset-content\b|\badd-content\b|\bout-file\b|\bremove-item\b|\brm\b|\bdel\b|\bmv\b|\bmove-item\b|\bcp\b|\bcopy-item\b|\bgit\s+(checkout|restore|reset|rm)\b)", c)
    if writes and any(l in c for l in locked):
        deny(f"{tool} blocked: the command may change frozen hillclimb files or .claude/.")


def main():
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    hold_dir, locked = load()
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        check_path(tool, ti.get("file_path") or ti.get("notebook_path") or "", tool != "Read", hold_dir, locked)
    elif tool in ("Grep", "Glob"):
        for key in ("path", "glob", "pattern"):
            if ti.get(key):
                check_path(tool, ti[key], False, hold_dir, locked)
    elif tool in ("Bash", "PowerShell"):
        check_command(tool, ti.get("command", ""), hold_dir, locked)
    sys.exit(0)


if __name__ == "__main__":
    main()
