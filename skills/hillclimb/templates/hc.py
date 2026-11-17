import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HC = Path(__file__).resolve().parent
ROOT = HC.parent
CONFIG = HC / "config.json"
RUNS = HC / "runs"
RUNS_CSV = HC / "runs.csv"
DECISIONS = HC / "decisions.json"
LEDGER = HC / "LEDGER.md"
FROZEN = HC / "FROZEN.json"
CSV_FIELDS = ["timestamp", "set", "label", "app_version", "check_rate", "checks_passed", "checks_total", "case_rate", "cases_passed", "cases", "errors", "latency_p50_ms", "latency_p95_ms", "wall_seconds"]
METRICS = ["check_rate", "case_rate", "errors", "latency_p50_ms", "latency_p95_ms"]
LOWER_IS_BETTER = {"errors", "latency_p50_ms", "latency_p95_ms"}


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def holdout_path(cfg):
    raw = os.environ.get("HC_HOLDOUT") or cfg.get("holdout_path") or f"~/.hillclimb/{cfg['name']}/holdout.jsonl"
    return Path(os.path.expanduser(raw))


def set_path(cfg, name):
    if name == "dev":
        return HC / "data" / "dev.jsonl"
    return holdout_path(cfg)


def frozen_files(cfg):
    base = ["hillclimb/hc.py", "hillclimb/config.json", "hillclimb/data/dev.jsonl"]
    return sorted(set(base + cfg.get("frozen", [])))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_state(cfg):
    state = {f: digest(ROOT / f) for f in frozen_files(cfg)}
    hp = holdout_path(cfg)
    if hp.exists():
        state["<holdout>"] = digest(hp)
    return state


def verify(cfg, quiet=False):
    if not FROZEN.exists():
        if not quiet:
            print("FROZEN.json missing: run `python hillclimb/hc.py freeze` once setup is approved.")
        return True
    expected = json.loads(FROZEN.read_text(encoding="utf-8"))
    current = frozen_state(cfg)
    bad = [k for k in expected if expected.get(k) != current.get(k)]
    if not quiet or bad:
        for k in expected:
            print(f"{'CHANGED' if k in bad else 'OK     '} {k}")
    return not bad


def git_state():
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "none"
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=ROOT, capture_output=True, text=True).stdout
        dirty = [l for l in dirty.splitlines() if "hillclimb/runs" not in l and "hillclimb/runs.csv" not in l]
        return rev + ("+dirty" if dirty else "")
    except OSError:
        return "unknown"


def invoke(cfg, payload):
    inv = cfg["invoke"]
    timeout = inv.get("timeout_s", 120)
    started = time.perf_counter()
    if inv["type"] == "command":
        data = payload if isinstance(payload, str) and inv.get("input", "json") == "text" else json.dumps(payload)
        proc = subprocess.run(inv["command"], cwd=ROOT, input=data, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"exit {proc.returncode}: {proc.stderr.strip()[-500:]}")
        raw = proc.stdout
    elif inv["type"] == "http":
        headers = {"Content-Type": "application/json"}
        for header, env in inv.get("headers_env", {}).items():
            if os.environ.get(env):
                headers[header] = os.environ[env]
        req = urllib.request.Request(inv["url"], data=json.dumps(payload).encode("utf-8"), headers=headers, method=inv.get("method", "POST"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    else:
        raise ValueError(f"unknown invoke type {inv['type']}")
    ms = round((time.perf_counter() - started) * 1000)
    if cfg.get("output", "json") == "json":
        return json.loads(raw.strip()), ms
    return raw.strip(), ms


def pick(output, path):
    if not path:
        return output
    cur = output
    for part in path.split("."):
        if isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)] if int(part) < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def as_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def run_check(check, case, output, ms):
    kind = check["type"]
    value = pick(output, check.get("path"))
    fold = (lambda s: s.lower()) if check.get("ignore_case") else (lambda s: s)
    if kind == "equals":
        return value == check["value"], f"expected {check['value']!r} got {value!r}"
    if kind == "one_of":
        return value in check["values"], f"expected one of {check['values']!r} got {value!r}"
    if kind == "contains":
        return value is not None and fold(check["value"]) in fold(as_text(value)), f"missing {check['value']!r}"
    if kind == "not_contains":
        return value is None or fold(check["value"]) not in fold(as_text(value)), f"should not contain {check['value']!r}"
    if kind == "regex":
        flags = re.IGNORECASE if check.get("ignore_case") else 0
        return value is not None and re.search(check["pattern"], as_text(value), flags) is not None, f"no match for /{check['pattern']}/"
    if kind == "number_between":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return False, f"not a number: {value!r}"
        return check.get("min", float("-inf")) <= n <= check.get("max", float("inf")), f"{n} outside [{check.get('min')}, {check.get('max')}]"
    if kind == "max_latency_ms":
        return ms <= check["value"], f"{ms}ms > {check['value']}ms"
    if kind == "command":
        proc = subprocess.run(check["run"], cwd=ROOT, input=json.dumps({"case": case, "output": output, "latency_ms": ms}), capture_output=True, text=True, encoding="utf-8", timeout=check.get("timeout_s", 120))
        try:
            verdict = json.loads(proc.stdout.strip())
            return bool(verdict.get("pass")), str(verdict.get("reason", ""))
        except json.JSONDecodeError:
            return proc.returncode == 0, proc.stdout.strip()[-300:] or proc.stderr.strip()[-300:]
    raise ValueError(f"unknown check type {kind}")


def grade_case(cfg, case):
    checks = case.get("checks", [])
    try:
        output, ms = invoke(cfg, case["input"])
    except Exception as exc:
        return {"id": case["id"], "error": f"{type(exc).__name__}: {exc}", "output": None, "latency_ms": None, "checks": [{"type": c["type"], "pass": False, "detail": "error"} for c in checks]}
    results = []
    for c in checks:
        try:
            ok, detail = run_check(c, case, output, ms)
        except Exception as exc:
            ok, detail = False, f"check error {type(exc).__name__}: {exc}"
        results.append({"type": c["type"], "path": c.get("path"), "pass": ok, "detail": "" if ok else detail})
    return {"id": case["id"], "error": None, "output": output, "latency_ms": ms, "checks": results}


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def summarise(rows):
    total = sum(len(r["checks"]) for r in rows)
    passed = sum(c["pass"] for r in rows for c in r["checks"])
    cases_passed = sum(1 for r in rows if not r["error"] and all(c["pass"] for c in r["checks"]))
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    return {
        "check_rate": round(passed / total, 4) if total else 0.0,
        "checks_passed": passed,
        "checks_total": total,
        "case_rate": round(cases_passed / len(rows), 4) if rows else 0.0,
        "cases_passed": cases_passed,
        "cases": len(rows),
        "errors": sum(1 for r in rows if r["error"]),
        "latency_p50_ms": percentile(lat, 0.5),
        "latency_p95_ms": percentile(lat, 0.95),
    }


def base_label(label):
    return re.sub(r"-r\d+$", "", label)


def read_runs(set_name="dev"):
    if not RUNS_CSV.exists():
        return []
    with RUNS_CSV.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r["set"] == set_name]


def group(runs):
    out = {}
    for r in runs:
        out.setdefault(base_label(r["label"]), []).append(r)
    return out


def num(v):
    return float(v) if v not in (None, "", "None") else None


def agg(rows, metric):
    vals = [num(r[metric]) for r in rows if num(r[metric]) is not None]
    if not vals:
        return None
    return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)}


def read_decisions():
    return json.loads(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.exists() else {}


def current_best(decisions):
    kept = [k for k, v in decisions.items() if v.get("decision") == "kept"]
    if kept:
        return kept[-1]
    base = [k for k, v in decisions.items() if v.get("decision") == "baseline"]
    return base[-1] if base else None


def compare(cfg, label, against=None):
    decisions = read_decisions()
    against = against or current_best(decisions)
    groups = group(read_runs("dev"))
    label = base_label(label)
    if not against or against not in groups or label not in groups or against == label:
        return None
    primary = cfg.get("target", {}).get("metric", "check_rate")
    a, b = agg(groups[against], primary), agg(groups[label], primary)
    if a is None or b is None:
        return None
    total = num(groups[label][0]["checks_total"]) or 1
    one = 1 / total if primary == "check_rate" else 1 / (num(groups[label][0]["cases"]) or 1)
    noise = max(a["max"] - a["min"], b["max"] - b["min"], one if cfg.get("noise_min_one_check", True) else 0)
    gain = b["mean"] - a["mean"]
    if primary in LOWER_IS_BETTER:
        gain = -gain
    broken = []
    for g in cfg.get("guards", []):
        ga, gb = agg(groups[against], g["metric"]), agg(groups[label], g["metric"])
        if ga is None or gb is None:
            continue
        worse = gb["mean"] - ga["mean"] if g["metric"] in LOWER_IS_BETTER else ga["mean"] - gb["mean"]
        limit = g.get("max_worse", 0)
        if "max_worse_pct" in g and ga["mean"]:
            limit = abs(ga["mean"]) * g["max_worse_pct"] / 100
        if worse > limit:
            broken.append(f"{g['metric']} {ga['mean']:.4g} -> {gb['mean']:.4g}")
    verdict = "KEEP" if gain > noise and not broken else "REJECT"
    why = f"{primary} {a['mean']:.4f} -> {b['mean']:.4f} (gain {gain:+.4f}, noise {noise:.4f})"
    if broken:
        why += "; guard broken: " + ", ".join(broken)
    elif gain <= noise:
        why += "; gain is within noise"
    return {"verdict": verdict, "against": against, "reason": why}


def print_summary(s, set_name, label):
    print(f"\nset={set_name}  label={label}  app@{s['app_version']}")
    print(f"checks   {s['checks_passed']}/{s['checks_total']} ({s['check_rate']:.1%})")
    print(f"cases    {s['cases_passed']}/{s['cases']} ({s['case_rate']:.1%})")
    print(f"errors   {s['errors']}   latency p50 {s['latency_p50_ms']}ms  p95 {s['latency_p95_ms']}ms   wall {s['wall_seconds']}s")


def print_failures(rows, limit=40):
    misses = [r for r in rows if r["error"] or not all(c["pass"] for c in r["checks"])]
    if not misses:
        return
    print("\nfailures (dev):")
    for r in misses[:limit]:
        if r["error"]:
            print(f"  {r['id']}: ERROR {r['error']}")
            continue
        bad = "; ".join(f"{c['type']}{'@' + c['path'] if c.get('path') else ''}: {c['detail']}" for c in r["checks"] if not c["pass"])
        print(f"  {r['id']}: {bad}")
    if len(misses) > limit:
        print(f"  ... {len(misses) - limit} more in the run folder")


def cmd_run(cfg, args):
    if not verify(cfg, quiet=True):
        raise SystemExit("Frozen files changed. Restore them before scoring (python hillclimb/hc.py verify).")
    path = set_path(cfg, args.set)
    if not path.exists():
        raise SystemExit(f"No cases for set '{args.set}' at {path if args.set == 'dev' else 'the configured holdout path'}.")
    cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        cases = cases[: args.limit]
    repeat = args.repeat or (cfg.get("repeat", 3) if args.set == "dev" and not args.limit else 1)
    workers = args.workers or cfg["invoke"].get("workers", 4)
    for i in range(1, repeat + 1):
        label = f"{args.label}-r{i}" if repeat > 1 else args.label
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(lambda c: grade_case(cfg, c), cases))
        s = summarise(rows)
        s.update({"timestamp": datetime.now().isoformat(timespec="seconds"), "set": args.set, "label": label, "app_version": git_state(), "wall_seconds": round(time.perf_counter() - started, 1)})
        if args.limit:
            print_summary(s, args.set, label + " (smoke, not recorded)")
            if args.set == "dev":
                print_failures(rows)
            continue
        if args.set == "dev":
            out = RUNS / f"{datetime.now():%Y%m%d-%H%M%S}_dev_{label}"
            out.mkdir(parents=True)
            (out / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        new = not RUNS_CSV.exists()
        with RUNS_CSV.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(s)
        print_summary(s, args.set, label)
        if args.set == "dev" and i == repeat:
            print_failures(rows)
    if args.set == "dev" and not args.limit:
        verdict = compare(cfg, args.label)
        if verdict:
            print(f"\nverdict vs {verdict['against']}: {verdict['verdict']}  {verdict['reason']}")
        print_target(cfg, args.label)


def print_target(cfg, label):
    t = cfg.get("target")
    if not t:
        return
    rows = group(read_runs("dev")).get(base_label(label))
    a = agg(rows or [], t["metric"])
    if a is None:
        return
    hit = a["mean"] <= t["value"] if t["metric"] in LOWER_IS_BETTER else a["mean"] >= t["value"]
    print(f"target   {t['metric']} {'<=' if t['metric'] in LOWER_IS_BETTER else '>='} {t['value']}: {'REACHED' if hit else 'not yet'} (mean {a['mean']:.4f})")


def cmd_record(cfg, args):
    decisions = read_decisions()
    groups = group(read_runs("dev"))
    label = base_label(args.label)
    if label not in groups:
        raise SystemExit(f"No dev runs recorded for '{label}'.")
    decisions[label] = {"decision": args.decision, "title": args.title, "reason": args.reason, "timestamp": datetime.now().isoformat(timespec="seconds")}
    DECISIONS.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    primary = cfg.get("target", {}).get("metric", "check_rate")
    vals = ", ".join(r[primary] for r in groups[label])
    row = f"| {label} | {args.title} | {vals} | {groups[label][-1]['errors']} | {args.decision} | {args.reason} |\n"
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(row)
    print(f"recorded {label}: {args.decision}")


def cmd_status(cfg, _args):
    decisions = read_decisions()
    groups = group(read_runs("dev"))
    primary = cfg.get("target", {}).get("metric", "check_rate")
    print(f"{cfg['name']}: {cfg.get('goal', '')}")
    print(f"{'label':<28}{'decision':<10}{primary + ' mean':>18}{'spread':>10}{'errors':>8}{'p50 ms':>9}")
    for label, rows in groups.items():
        a, e, l = agg(rows, primary), agg(rows, "errors"), agg(rows, "latency_p50_ms")
        d = decisions.get(label, {}).get("decision", "-")
        print(f"{label:<28}{d:<10}{a['mean']:>18.4f}{a['max'] - a['min']:>10.4f}{(e or {}).get('mean', 0):>8.1f}{(l or {}).get('mean') or 0:>9.0f}")
    best = current_best(decisions)
    print(f"\ncurrent best: {best or 'none (record a baseline)'}")
    if best:
        print_target(cfg, best)
    hold = read_runs("holdout")
    if hold:
        print("\nholdout runs (scored by a human):")
        for r in hold:
            print(f"  {r['label']:<26}{r[primary]:>10}  cases {r['cases_passed']}/{r['cases']}  {r['timestamp']}")
    streak = 0
    for v in reversed(list(decisions.values())):
        if v.get("decision") != "rejected":
            break
        streak += 1
    if streak >= cfg.get("stagnation_after", 3):
        print(f"\nSTAGNATION: {streak} rejected attempts in a row. Stop and report to the user.")


def cmd_freeze(cfg, _args):
    FROZEN.write_text(json.dumps(frozen_state(cfg), indent=2) + "\n", encoding="utf-8")
    print(f"froze {len(frozen_files(cfg))} files" + (" + holdout" if holdout_path(cfg).exists() else ""))


def main():
    p = argparse.ArgumentParser(prog="hc")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", choices=["dev", "holdout"], default="dev")
    r.add_argument("--label", required=True)
    r.add_argument("--repeat", type=int, default=0)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--workers", type=int, default=0)
    c = sub.add_parser("compare")
    c.add_argument("--label", required=True)
    c.add_argument("--against")
    d = sub.add_parser("record")
    d.add_argument("--label", required=True)
    d.add_argument("--decision", choices=["baseline", "kept", "rejected"], required=True)
    d.add_argument("--title", required=True)
    d.add_argument("--reason", required=True)
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("freeze")
    args = p.parse_args()
    cfg = load_config()
    if args.cmd == "run":
        cmd_run(cfg, args)
    elif args.cmd == "compare":
        v = compare(cfg, args.label, args.against)
        print(f"{v['verdict']} vs {v['against']}: {v['reason']}" if v else "Nothing to compare (need dev runs for both labels).")
    elif args.cmd == "record":
        cmd_record(cfg, args)
    elif args.cmd == "status":
        cmd_status(cfg, args)
    elif args.cmd == "verify":
        sys.exit(0 if verify(cfg) else 1)
    elif args.cmd == "freeze":
        cmd_freeze(cfg, args)


if __name__ == "__main__":
    main()
