from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
API = "7.1"
POLICY_API = "7.1-preview.1"
STATE_DIR = Path.home() / ".local" / "state" / "pr-wait"
STALE_STATE_SECONDS = 6 * 3600
MAX_FAILED_POLLS = 10
TOKEN_TTL = 40 * 60
DONE = ("approved", "notApplicable")
FAILED = ("rejected", "broken")
OPEN_THREADS = ("active", "pending")
VOTES = {10: "approved", 5: "approved with suggestions", 0: "no vote", -5: "waiting for author", -10: "rejected"}
REMOTE_PATTERNS = (
    re.compile(r"https://(?:[^@/\s]+@)?dev\.azure\.com/([^/\s]+)/([^/\s]+)/_git/([^/\s?#]+)(?:/pullrequest/(\d+))?", re.I),
    re.compile(r"https://(?:[^@/\s]+@)?([^./\s]+)\.visualstudio\.com/(?:DefaultCollection/)?([^/\s]+)/_git/([^/\s?#]+)(?:/pullrequest/(\d+))?", re.I),
    re.compile(r"(?:ssh://)?git@ssh\.dev\.azure\.com[:/]v3/([^/\s]+)/([^/\s]+)/([^/\s]+?)(?:\.git)?()$", re.I),
)

Json = dict[str, Any]


class AdoError(Exception):
    def __init__(self, message: str, transient: bool, status: int = 0) -> None:
        super().__init__(message)
        self.transient = transient
        self.status = status


def log(message: str) -> None:
    print(f"pr-wait: {message}", file=sys.stderr, flush=True)


def fail(message: str, code: int = 2) -> NoReturn:
    print(f"pr-wait: {message}", flush=True)
    sys.exit(code)


def snippet(body: str, limit: int = 100) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body or "")).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def branch(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


def parse_remote(url: str) -> tuple[str, str, str, int | None] | None:
    for pattern in REMOTE_PATTERNS:
        match = pattern.search(url.strip())
        if match:
            org, project, repo, pr = match.groups()
            unquote = urllib.parse.unquote
            return unquote(org), unquote(project), unquote(repo), int(pr) if pr else None
    return None


def repo_from_checkout() -> tuple[str, str, str] | None:
    git = shutil.which("git")
    if not git:
        return None
    proc = subprocess.run([git, "remote", "-v"], capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            found = parse_remote(parts[1])
            if found:
                return found[:3]
    return None


class Ado:
    def __init__(self, org: str, project: str, repo: str) -> None:
        self.org, self.project, self.repo = org, project, repo
        self.base = f"https://dev.azure.com/{urllib.parse.quote(org)}"
        self.project_base = f"{self.base}/{urllib.parse.quote(project)}"
        self.repo_base = f"{self.project_base}/_apis/git/repositories/{urllib.parse.quote(repo)}"
        self.web = f"{self.project_base}/_git/{urllib.parse.quote(repo)}"
        self.token: str | None = None
        self.token_at = 0.0

    def access_token(self, force: bool = False) -> str:
        if force or not self.token or time.time() - self.token_at > TOKEN_TTL:
            az = shutil.which("az") or shutil.which("az.cmd")
            if not az:
                raise AdoError("az CLI not found on PATH", False)
            proc = subprocess.run(
                [az, "account", "get-access-token", "--resource", ADO_RESOURCE, "--query", "accessToken", "-o", "tsv"],
                capture_output=True,
                text=True,
            )
            if proc.returncode or not proc.stdout.strip():
                lines = proc.stderr.strip().splitlines()
                raise AdoError(f"az could not issue a token ({lines[-1] if lines else proc.returncode}); run `az login`", False)
            self.token, self.token_at = proc.stdout.strip(), time.time()
        return self.token

    def get(self, url: str, params: dict[str, str] | None = None) -> Json:
        query = urllib.parse.urlencode({"api-version": API, **(params or {})})
        full = f"{url}{'&' if '?' in url else '?'}{query}"
        delay, refreshed = 2, False
        for attempt in range(5):
            request = urllib.request.Request(full, headers={"Authorization": f"Bearer {self.access_token()}", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    if response.status == 203 or "json" not in response.headers.get("Content-Type", ""):
                        raise urllib.error.HTTPError(full, 401, "sign-in page returned", response.headers, None)
                    return json.loads(body)
            except urllib.error.HTTPError as error:
                if error.code in (401, 203) and not refreshed:
                    refreshed = True
                    self.access_token(force=True)
                    continue
                transient = error.code >= 500 or error.code == 429
                message = f"HTTP {error.code} on {url.removeprefix(self.base)}"
                if not transient or attempt == 4:
                    raise AdoError(message, transient, error.code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                message = f"network error: {getattr(error, 'reason', error)}"
                if attempt == 4:
                    raise AdoError(message, True) from None
            log(f"{message}; retry in {delay}s")
            time.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")

    def me(self) -> str:
        return self.get(f"{self.base}/_apis/connectionData", {"api-version": "7.1-preview"})["authenticatedUser"]["id"]

    def pr(self, number: int) -> Json:
        return self.get(f"{self.repo_base}/pullrequests/{number}")

    def threads(self, number: int) -> list[Json]:
        return self.get(f"{self.repo_base}/pullRequests/{number}/threads")["value"]

    def policies(self, project_id: str, number: int) -> list[Json]:
        artifact = f"vstfs:///CodeReview/CodeReviewId/{project_id}/{number}"
        return self.get(f"{self.project_base}/_apis/policy/evaluations", {"artifactId": artifact, "api-version": POLICY_API})["value"]

    def pr_files(self, number: int) -> set[str]:
        iterations = self.get(f"{self.repo_base}/pullRequests/{number}/iterations")["value"]
        if not iterations:
            return set()
        last = iterations[-1]["id"]
        changes = self.get(f"{self.repo_base}/pullRequests/{number}/iterations/{last}/changes", {"$top": "2000", "$compareTo": "0"})
        return {c["item"]["path"] for c in changes.get("changeEntries", []) if c.get("item", {}).get("path")}

    def commit_diff(self, base: str, target: str, kind: str) -> Json:
        return self.get(
            f"{self.repo_base}/diffs/commits",
            {"baseVersion": base, "baseVersionType": kind, "targetVersion": target, "targetVersionType": kind, "$top": "2000"},
        )


def lock(key: str) -> Any:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(STATE_DIR / f"{key}.lock", "a+")
    pid_file = STATE_DIR / f"{key}.pid"
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        pid = pid_file.read_text().strip() if pid_file.exists() else "unknown"
        fail(
            f"pid {pid} already watches this PR, so this watcher exits to avoid duplicate events. "
            f"If no events reach you from it, stop pid {pid} and start again."
        )
    pid_file.write_text(str(os.getpid()))
    return handle


def policy_name(policy: Json) -> str:
    config = policy.get("configuration") or {}
    return (config.get("settings") or {}).get("displayName") or (config.get("type") or {}).get("displayName") or "policy"


def is_review_policy(policy: Json) -> bool:
    return "reviewer" in ((policy.get("configuration") or {}).get("type") or {}).get("displayName", "").lower()


def is_blocking(policy: Json) -> bool:
    config = policy.get("configuration") or {}
    return bool(config.get("isBlocking")) and config.get("isEnabled", True) and not config.get("isDeleted")


def text_comments(thread: Json) -> list[Json]:
    return [c for c in thread.get("comments", []) if c.get("commentType") == "text" and not c.get("isDeleted")]


class Watcher:
    def __init__(self, ado: Ado, pr: int, until: str, interval: int) -> None:
        self.ado, self.pr, self.until, self.interval = ado, pr, until, interval
        self.key = re.sub(r"[^\w.-]", "_", f"{ado.org}__{ado.project}__{ado.repo}__{pr}")
        self.path = STATE_DIR / f"{self.key}.json"
        state = self.load()
        self.baseline = state is None
        self.state: Json = state or {"reported": [], "target_oid": None, "merge_status": None}
        self.reported: set[str] = set(self.state["reported"])
        self.printed: set[str] = set()
        self.events = 0
        self.me: str | None = None
        self.prev_snapshot: list[tuple[Any, str]] | None = None
        self.files: dict[str, set[str]] = {}
        self.url = f"{ado.web}/pullrequest/{pr}"

    def load(self) -> Json | None:
        try:
            if time.time() - self.path.stat().st_mtime > STALE_STATE_SECONDS:
                return None
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state["reported"] = sorted(self.reported)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state), encoding="utf-8")
        tmp.replace(self.path)

    def say(self, line: str) -> None:
        if line not in self.printed:
            self.printed.add(line)
            print(f"!{self.pr} {line}", flush=True)

    def emit(self, key: str, line: str) -> None:
        if key in self.reported:
            return
        self.reported.add(key)
        if not self.baseline:
            self.events += 1
            self.say(line)

    def finish(self, code: int, lines: list[str] | tuple[str, ...] = ()) -> NoReturn:
        for line in lines:
            self.say(line)
        self.save()
        sys.exit(code)

    def fetch(self) -> tuple[Json, list[Json], list[Json]]:
        pr = self.ado.pr(self.pr)
        if pr.get("status") != "active":
            return pr, [], []
        return pr, self.ado.threads(self.pr), self.ado.policies(pr["repository"]["project"]["id"], self.pr)

    def build_link(self, policy: Json) -> str:
        build = (policy.get("context") or {}).get("buildId")
        return f" {self.ado.project_base}/_build/results?buildId={build}" if build else ""

    def overlap(self, head: str, old: str, new: str) -> list[str]:
        try:
            if head not in self.files:
                self.files[head] = self.ado.pr_files(self.pr)
            moved = {c["item"]["path"] for c in self.ado.commit_diff(old, new, "commit").get("changes", []) if c.get("item", {}).get("gitObjectType") == "blob"}
        except AdoError as error:
            log(f"could not compare target commits: {error}")
            return []
        return sorted(p.lstrip("/") for p in self.files[head] & moved)

    def behind(self, source: str, target: str) -> int:
        try:
            return int(self.ado.commit_diff(target, source, "branch").get("behindCount") or 0)
        except AdoError as error:
            log(f"could not measure how far behind {target} the branch is: {error}")
            return 0

    def poll(self) -> None:
        pr, threads, policies = self.fetch()
        if pr["status"] == "completed":
            self.finish(0, [f"merged: {self.url}"])
        if pr["status"] == "abandoned":
            self.finish(1, [f"abandoned without merging: {self.url}"])
        if self.me is None:
            self.me = self.ado.me()
            log(f"watching {self.url} until {self.until}")

        head = pr["lastMergeSourceCommit"]["commitId"]
        short = head[:7]
        source, target = branch(pr["sourceRefName"]), branch(pr["targetRefName"])
        mine = {self.me, (pr.get("createdBy") or {}).get("id")}
        self.events = 0

        blocking = [p for p in policies if is_blocking(p)]
        checks = [p for p in blocking if not is_review_policy(p)]
        reviews = [p for p in blocking if is_review_policy(p)]

        fail_lines: list[str] = []
        for policy in checks:
            if policy["status"] in FAILED:
                fail_lines.append(f"policy failed: {policy_name(policy)}{self.build_link(policy)}")
                build = (policy.get("context") or {}).get("buildId")
                self.emit(f"fail:{head}:{policy['evaluationId']}:{build}", fail_lines[-1])
        checks_done = all(p["status"] in DONE + FAILED for p in checks)
        snapshot = sorted((p["evaluationId"], p["status"]) for p in blocking)
        stable = snapshot == self.prev_snapshot
        self.prev_snapshot = snapshot
        green = checks_done and stable and not fail_lines
        approved = all(p["status"] in DONE for p in reviews)

        rejected_by: list[str] = []
        for reviewer in pr.get("reviewers", []):
            vote = reviewer.get("vote", 0)
            if vote == -10:
                rejected_by.append(reviewer.get("displayName", "a reviewer"))
            if reviewer.get("id") in mine or vote == 0 or reviewer.get("isContainer"):
                continue
            self.emit(f"vote:{reviewer['id']}:{vote}", f"vote from {reviewer.get('displayName')}: {VOTES.get(vote, vote)}")

        unresolved: list[str] = []
        for thread in threads:
            if thread.get("isDeleted"):
                continue
            comments = text_comments(thread)
            if not comments:
                continue
            link = f"{self.url}?discussionId={thread['id']}"
            if thread.get("status") in OPEN_THREADS:
                unresolved.append(link)
            context = thread.get("threadContext") or {}
            line = (context.get("rightFileStart") or context.get("leftFileStart") or {}).get("line")
            where = f" on {context['filePath'].lstrip('/')}{':' + str(line) if line else ''}" if context.get("filePath") else ""
            for index, comment in enumerate(comments):
                if (comment.get("author") or {}).get("id") in mine:
                    continue
                kind = "new thread" if index == 0 else "thread reply"
                author = (comment.get("author") or {}).get("displayName", "someone")
                self.emit(f"c:{thread['id']}:{comment['id']}", f"{kind} from {author}{where}: {snippet(comment.get('content', ''))} {link}")

        target_oid = (pr.get("lastMergeTargetCommit") or {}).get("commitId")
        old_target = self.state["target_oid"]
        if target_oid and old_target and target_oid != old_target and not self.baseline:
            touched = self.overlap(head, old_target, target_oid)
            if touched:
                more = f" and {len(touched) - 5} more" if len(touched) > 5 else ""
                self.emit(f"target:{target_oid}", f"{target} moved to {target_oid[:7]} and touches files in this PR: {', '.join(touched[:5])}{more}")
        if target_oid:
            self.state["target_oid"] = target_oid

        merge_status = pr.get("mergeStatus", "notSet")
        conflict_line = f"merge status is conflicts: the branch conflicts with {target}, rebase it"
        if merge_status == "conflicts" and self.state["merge_status"] != merge_status:
            self.emit(f"merge:conflicts:{head}:{target_oid}", conflict_line)
        self.state["merge_status"] = merge_status

        counts: dict[str, int] = {}
        for policy in blocking:
            counts[policy["status"]] = counts.get(policy["status"], 0) + 1
        votes = [f"{r.get('displayName')} {VOTES.get(r.get('vote', 0), r.get('vote'))}" for r in pr.get("reviewers", []) if not r.get("isContainer")]
        parts = [
            "blocking policies " + (", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "none"),
            "reviewers " + (", ".join(votes) or "none"),
            f"{len(unresolved)} unresolved threads",
            f"merge status {merge_status}",
            "draft" if pr.get("isDraft") else "",
        ]
        summary = "; ".join(p for p in parts if p)
        checks_key = f"checks:{head}"

        if self.until != "any-change":
            if merge_status == "conflicts":
                self.finish(1, [conflict_line])
            if fail_lines:
                self.finish(1, fail_lines)
            if green and self.until == "green":
                self.reported.add(checks_key)
                count = self.behind(source, target)
                self.finish(0, [f"green on {short}: {summary}{f'; {count} commits behind {target}' if count else ''}"])
            if green and self.until == "ready":
                if rejected_by:
                    self.finish(1, [f"rejected by {', '.join(rejected_by)} on {short}: {summary}"])
                if approved and merge_status == "succeeded":
                    if unresolved:
                        self.finish(1, [f"blocked by {len(unresolved)} unresolved threads on {short}: {' '.join(unresolved)}"])
                    if pr.get("isDraft"):
                        self.finish(1, [f"draft: publish the PR before it can merge {self.url}"])
                    count = self.behind(source, target)
                    if count:
                        self.finish(1, [f"behind {target} by {count} commits: update the branch before merging"])
                    self.reported.add(checks_key)
                    self.finish(0, [f"ready on {short}: {summary}"])
                if not approved:
                    self.emit(f"awaiting:{head}", f"waiting for required approval on {short}: {summary}")
        if checks_done and (stable or self.baseline):
            self.emit(checks_key, f"policies finished on {short}: {summary}")
        if self.until == "any-change" and self.events:
            self.finish(0)

    def run(self) -> NoReturn:
        failures = 0
        while True:
            try:
                self.poll()
                failures = 0
            except AdoError as error:
                if not error.transient:
                    self.finish(1, [f"pr-wait stopped: {error}"])
                failures += 1
                log(f"poll failed ({failures}/{MAX_FAILED_POLLS}): {error}")
                if failures >= MAX_FAILED_POLLS:
                    self.finish(1, [f"pr-wait stopped: Azure DevOps unreachable for {failures} polls: {error}"])
            else:
                self.save()
                if self.baseline:
                    log(f"baseline recorded for {self.url}; reporting only new events")
                self.baseline = False
            time.sleep(self.interval)


def resolve(args: argparse.Namespace) -> tuple[Ado, int]:
    raw = (args.pr or "").strip()
    if not raw:
        fail("missing PR id. Did a variable expand to nothing? Usage: pr-wait <pr id or url>")
    from_url = parse_remote(raw)
    number_match = re.fullmatch(r"!?#?(\d+)", raw)
    if from_url and from_url[3]:
        org, project, repo, number = from_url
    elif number_match:
        number = int(number_match.group(1))
        found = repo_from_checkout()
        org, project, repo = args.org or (found and found[0]), args.project or (found and found[1]), args.repo or (found and found[2])
        if not (org and project and repo):
            fail("no Azure DevOps remote in the current checkout; pass a PR URL or --org, --project and --repo")
    else:
        fail(f"'{raw}' is not a PR id or Azure DevOps PR URL")
    if number <= 0:
        fail(f"'{raw}' is not a valid PR id")
    ado = Ado(str(org), str(project), str(repo))
    try:
        ado.pr(number)
    except AdoError as error:
        if not error.transient:
            fail(f"cannot read PR {number} in {org}/{project}/{repo}: {error}")
    return ado, number


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="pr-wait",
        description="Watch one Azure DevOps pull request and print one line per real event.",
        epilog=(
            "--until green: blocking non-reviewer policies passed. ready (default): every blocking policy approved, "
            "merge status succeeded, no active threads, not draft, not behind the target. any-change: stop after the "
            "first event. Exit 0: condition met or PR merged. Exit 1: needs action (policy failed, conflicts, rejected, "
            "unresolved threads, behind, abandoned, unreachable). Exit 2: bad arguments, unknown PR, or another watcher "
            "already runs. Auth comes from `az login`."
        ),
    )
    parser.add_argument("pr", nargs="?", help="PR id or PR URL")
    parser.add_argument("--org", help="organization name (default: from the URL or the current checkout)")
    parser.add_argument("--project", help="project name")
    parser.add_argument("--repo", help="repository name")
    parser.add_argument("--until", choices=("green", "ready", "any-change"), default="ready")
    parser.add_argument("--interval", type=int, default=30, help="seconds between polls (default 30, min 10)")
    args = parser.parse_args()
    ado, number = resolve(args)
    watcher = Watcher(ado, number, args.until, max(args.interval, 10))
    _lock = lock(watcher.key)
    watcher.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
