"""Isolated proposals and local OS-identity approvals; no arbitrary executor."""
import base64
import csv
import difflib
import json
import os
import re
import sqlite3
import subprocess
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Report
from .investigation import project_evidence
from .network import PolicyError, enabled
from .repository import MAX_FILE, GitHubRepository, blob_sha, safe_path, sha


def utcnow():
    return datetime.now(timezone.utc)


def identity():
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, 260):
            raise PolicyError("Unable to determine authenticated Windows identity")
        result = subprocess.run([str(Path(buffer.value) / "System32" / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                                capture_output=True, text=True, timeout=5, shell=False)
        rows = list(csv.reader(result.stdout.splitlines()))
        if result.returncode or len(rows) != 1 or len(rows[0]) != 2 or not re.fullmatch(r"S-1-[0-9-]+", rows[0][1]):
            raise PolicyError("Unable to authenticate Windows user")
        return "sid:" + rows[0][1]
    return f"uid:{os.getuid()}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def diff_for(path, before, after):
    for value in (before, after):
        if len(value) > MAX_FILE or b"\0" in value or not value.endswith(b"\n"):
            raise PolicyError("Proposals require bounded UTF-8 text with a final newline")
        if re.search(rb"sk-ant-|github_pat_|gh[pousr]_", value):
            raise PolicyError("Potential credential detected; proposal blocked")
    return "".join(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True), fromfile="a/"+path, tofile="b/"+path)).encode()


def check_patch(path, before, patch):
    """Validate application to a copied file; no website scripts or dependencies run."""
    safe_path(path)
    git = shutil.which("git")
    if not git:
        raise PolicyError("Git required for isolated patch check")
    with tempfile.TemporaryDirectory(prefix="guardian-patch-") as temporary:
        root = Path(temporary)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(before)
        patch_file = root / "proposal.patch"
        patch_file.write_bytes(patch)
        result = subprocess.run([git, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=", "apply",
                                 "--check", "--no-index", str(patch_file)],
                                cwd=root, shell=False, capture_output=True, timeout=15)
        if result.returncode:
            raise PolicyError("Isolated git apply check failed; output omitted")


def make_proposal(site_id, repository, replacement, path, report, evidence_ids, output):
    enabled()
    if path not in repository.config.patch_paths:
        raise PolicyError("File is not approved for isolated patch proposals")
    safe_path(path)
    if (report.site_id != site_id or not re.fullmatch(r"[a-f0-9]{32}", report.run_id) or not evidence_ids
            or any(not re.fullmatch(r"E\d{3,6}", eid) for eid in evidence_ids)
            or not set(evidence_ids) <= {e.id for e in report.evidence}):
        raise PolicyError("Proposal evidence/site does not match the report")
    if not any(set(evidence_ids) & set(f.evidence_ids) for f in report.findings):
        raise PolicyError("Proposal must reference an existing finding")
    base_sha = repository.revision()
    before = repository.read(path, base_sha)
    replacement = Path(replacement)
    if replacement.is_symlink() or replacement.stat().st_size > MAX_FILE:
        raise PolicyError("Replacement must be a bounded regular file")
    after = replacement.read_bytes()
    if before == after:
        raise PolicyError("Proposal contains no changes")
    patch = diff_for(path, before, after)
    check_patch(path, before, patch)
    evidence_payload, _ = project_evidence(report)
    evidence_data = canonical(evidence_payload)
    proposal_id = uuid.uuid4().hex
    manifest = {"version": 1, "proposal_id": proposal_id, "site_id": site_id,
        "repository": f"{repository.config.owner}/{repository.config.name}", "base_branch": repository.config.base_branch,
        "base_sha": base_sha, "path": path, "before_sha256": sha(before), "after_sha256": sha(after),
        "blob_sha": blob_sha(before), "diff_sha256": sha(patch), "source_run_id": report.run_id,
        "evidence_sha256": sha(evidence_data), "observed_at": report.started_at,
        "evidence_ids": sorted(set(evidence_ids)), "created_at": utcnow().isoformat(),
        "action": "create_pull_request", "status": "pending_review",
        "validation": "git apply --check passed; website build/tests not executed",
        "risk": "Human must review compatibility, rollout and production impact; no deployment is authorized."}
    digest = sha(canonical(manifest))
    directory = Path(output) / proposal_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "before.txt").write_bytes(before)
    (directory / "after.txt").write_bytes(after)
    (directory / "diff.patch").write_bytes(patch)
    (directory / "evidence.json").write_bytes(evidence_data)
    (directory / "proposal.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory / "REVIEW.md").write_text(
        f"# Proposed patch for human review\n\nProposal: {proposal_id}\nArtifact SHA-256: {digest}\n"
        f"Repository: {manifest['repository']}\nBase revision: {base_sha}\nFile: {path}\n"
        f"Evidence: {', '.join(manifest['evidence_ids'])} in run {report.run_id}\n\n"
        "See evidence.json for the bounded scanner observations bound to this artifact hash.\n"
        "Review diff.patch and after.txt. Only copied committed source was read; the website checkout is unchanged.\n"
        "Validation checks artifact hashes, diff reconstruction and git apply --check in a temporary copy. No website build, package installation, "
        "application tests, contact submissions or live traffic tests were run.\n"
        "PR publishing is disabled by default and requires an eligible OS user, exact hash, unexpired approval, "
        "an unchanged base branch, configured protection policy and separate scoped write credential. Merge/deploy remain human-only.\n", encoding="utf-8")
    return directory, digest


def validate_proposal(directory, config, site_id):
    enabled()
    directory = Path(directory).resolve(strict=True)
    files = {}
    for name in ("proposal.json", "before.txt", "after.txt", "diff.patch", "evidence.json"):
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory or path.stat().st_size > MAX_FILE*2:
            raise PolicyError("Proposal artifact path/size invalid")
        files[name] = path.read_bytes()
    manifest = json.loads(files["proposal.json"])
    if (manifest.get("version") != 1 or manifest.get("site_id") != site_id
            or manifest.get("repository") != f"{config.owner}/{config.name}"
            or manifest.get("base_branch") != config.base_branch or manifest.get("path") not in config.patch_paths
            or manifest.get("action") != "create_pull_request"
            or not re.fullmatch(r"[a-f0-9]{32}", manifest.get("proposal_id", ""))
            or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("base_sha", ""))):
        raise PolicyError("Proposal scope/action invalid")
    safe_path(manifest["path"])
    before, after, patch = files["before.txt"], files["after.txt"], files["diff.patch"]
    if (sha(before) != manifest["before_sha256"] or sha(after) != manifest["after_sha256"]
            or sha(patch) != manifest["diff_sha256"] or blob_sha(before) != manifest["blob_sha"]
            or sha(files["evidence.json"]) != manifest["evidence_sha256"]
            or diff_for(manifest["path"], before, after) != patch or before == after):
        raise PolicyError("Proposal integrity validation failed")
    check_patch(manifest["path"], before, patch)
    return manifest, sha(canonical(manifest)), after


class ApprovalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL,
              artifact_hash TEXT NOT NULL, site_id TEXT NOT NULL, approver TEXT NOT NULL,
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(proposal_id TEXT PRIMARY KEY, approval_id TEXT NOT NULL,
              status TEXT NOT NULL, pr_url TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
              proposal_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, outcome TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def approve(self, directory, config, site_id, expected_hash, minutes=30):
        enabled()
        manifest, digest, _ = validate_proposal(directory, config, site_id)
        actor = identity()
        if actor not in config.approver_ids or digest != expected_hash or not 1 <= minutes <= 60:
            raise PolicyError("Eligible approver, exact artifact hash and bounded approval expiry required")
        approval_id = uuid.uuid4().hex
        now = utcnow()
        with self.connect() as db:
            db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)", (approval_id, manifest["proposal_id"],
                digest, site_id, actor, now.isoformat(), (now+timedelta(minutes=minutes)).isoformat(), "approved"))
            db.execute("INSERT INTO events(timestamp,proposal_id,action,actor,outcome) VALUES(?,?,?,?,?)",
                       (now.isoformat(), manifest["proposal_id"], "approve_exact_patch", actor, "approved"))
        return approval_id

    def revoke(self, approval_id, config, site_id):
        enabled()
        actor = identity()
        if actor not in config.approver_ids:
            raise PolicyError("Approver not eligible")
        with self.connect() as db:
            changed = db.execute("""UPDATE approvals SET status='revoked' WHERE id=? AND approver=? AND site_id=?
                AND (status='approved' OR (status='consumed' AND EXISTS
                    (SELECT 1 FROM attempts WHERE approval_id=? AND status='started')))""",
                                 (approval_id, actor, site_id, approval_id)).rowcount
            if changed != 1:
                raise PolicyError("Approval cannot be revoked or was not found")
            proposal_id = db.execute("SELECT proposal_id FROM approvals WHERE id=?", (approval_id,)).fetchone()[0]
            db.execute("INSERT INTO events(timestamp,proposal_id,action,actor,outcome) VALUES(?,?,?,?,?)",
                       (utcnow().isoformat(), proposal_id, "revoke_approval", actor, "revoked"))

    def consume(self, manifest, digest, approval_id, config):
        enabled()
        actor = identity()
        if not config.allow_pr_creation or actor not in config.approver_ids:
            raise PolicyError("PR creation disabled or actor not eligible")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT proposal_id,artifact_hash,site_id,approver,created_at,expires_at,status FROM approvals WHERE id=?",
                             (approval_id,)).fetchone()
            now = utcnow()
            if (not row or row[:4] != (manifest["proposal_id"], digest, manifest["site_id"], actor)
                    or row[6] != "approved" or not datetime.fromisoformat(row[4]) <= now < datetime.fromisoformat(row[5])):
                raise PolicyError("Approval missing, mismatched, expired, revoked or consumed")
            if db.execute("SELECT 1 FROM attempts WHERE proposal_id=?", (manifest["proposal_id"],)).fetchone():
                raise PolicyError("Proposal already attempted; reconcile remotely before any further action")
            db.execute("UPDATE approvals SET status='consumed' WHERE id=?", (approval_id,))
            db.execute("INSERT INTO attempts VALUES(?,?,?,NULL)", (manifest["proposal_id"], approval_id, "started"))
            db.execute("INSERT INTO events(timestamp,proposal_id,action,actor,outcome) VALUES(?,?,?,?,?)",
                       (now.isoformat(), manifest["proposal_id"], "create_pull_request", actor, "started"))

    def check(self, manifest, digest, approval_id, config, running=False):
        enabled()
        actor = identity()
        with self.connect() as db:
            row = db.execute("SELECT proposal_id,artifact_hash,site_id,approver,created_at,expires_at,status FROM approvals WHERE id=?",
                             (approval_id,)).fetchone()
        if (actor not in config.approver_ids or not row
                or row[:4] != (manifest["proposal_id"], digest, manifest["site_id"], actor)
                or row[6] != ("consumed" if running else "approved")
                or not datetime.fromisoformat(row[4]) <= utcnow() < datetime.fromisoformat(row[5])):
            raise PolicyError("Approval missing, mismatched, expired, revoked or consumed")

    def receipt(self, proposal_id, status, pr_url=None):
        with self.connect() as db:
            db.execute("UPDATE attempts SET status=?,pr_url=? WHERE proposal_id=?", (status, pr_url, proposal_id))
            db.execute("INSERT INTO events(timestamp,proposal_id,action,actor,outcome) VALUES(?,?,?,?,?)",
                       (utcnow().isoformat(), proposal_id, "create_pull_request", identity(), status))

    def denied(self, proposal_id, outcome):
        with self.connect() as db:
            db.execute("INSERT INTO events(timestamp,proposal_id,action,actor,outcome) VALUES(?,?,?,?,?)",
                       (utcnow().isoformat(), proposal_id, "create_pull_request", identity(), outcome))


def create_pull_request(directory, config, site_id, approval_id, store, token, client=None, title=None, body=None):
    enabled()
    if not config.allow_pr_creation:
        store.denied("unvalidated", "denied_disabled_policy")
        raise PolicyError("PR creation is disabled by repository policy")
    manifest, digest, content = validate_proposal(directory, config, site_id)
    # Validate approval before reading credentials or performing even preflight requests.
    try:
        store.check(manifest, digest, approval_id, config)
    except PolicyError:
        store.denied(manifest["proposal_id"], "denied_invalid_approval")
        raise
    if not token:
        raise PolicyError("Separate repository-scoped write token required")
    if token == os.getenv("GUARDIAN_GITHUB_READ_TOKEN"):
        raise PolicyError("Read and write credentials must be separate")
    github = GitHubRepository(config, token, client)
    if github._request("GET", "").get("default_branch") != config.base_branch:
        raise PolicyError("Configured base is not the repository default branch")
    revision, protected = github.branch()
    if revision != manifest["base_sha"]:
        raise PolicyError("Base branch moved; prepare/review a fresh proposal")
    if config.require_protected_branch and not protected:
        raise PolicyError("Repository policy requires a protected base branch")
    original = github.read(manifest["path"], revision)
    if sha(original) != manifest["before_sha256"]:
        raise PolicyError("Remote base content differs from approved proposal")
    title = title or "Website Guardian: reviewed patch proposal"
    body = body or (f"Human-reviewed proposal {manifest['proposal_id']}. Artifact SHA-256: {digest}. "
                   "Artifact integrity and isolated git apply checked; website build/tests not executed. Human merge/deployment required.")
    if (len(title) > 200 or len(body) > 12000 or "\n" in title
            or re.search(r"sk-ant-|github_pat_|gh[pousr]_", title + body)):
        raise PolicyError("PR title/body exceeds limits or contains a potential credential")
    if not protected:
        body += "\n\nOwner-authorized unprotected-branch exception: " + config.unprotected_branch_reason
        body += "\nGuardian has no merge or deployment operation. Human merge/deployment required."
    store.consume(manifest, digest, approval_id, config)
    branch = "guardian/" + manifest["proposal_id"]
    def write(method, suffix, **kwargs):
        # Expiry, revocation, identity and kill switch are rechecked before every mutation.
        store.check(manifest, digest, approval_id, config, running=True)
        return github._request(method, suffix, **kwargs)
    try:
        write("POST", "/git/refs", json={"ref": "refs/heads/"+branch, "sha": revision})
        write("PUT", "/contents/"+manifest["path"], json={"message": "Website Guardian proposal " + manifest["proposal_id"],
            "content": base64.b64encode(content).decode(), "sha": manifest["blob_sha"], "branch": branch})
        result = write("POST", "/pulls", json={"title": title,
            "head": branch, "base": config.base_branch, "draft": config.draft_pr, "body": body})
        url = result.get("html_url", "")
        if not re.fullmatch(r"https://github\.com/"+re.escape(config.owner+"/"+config.name)+r"/pull/\d+", url):
            raise PolicyError("Unexpected PR receipt; manual reconciliation required")
        store.receipt(manifest["proposal_id"], "created", url)
        return url
    except BaseException:
        store.receipt(manifest["proposal_id"], "failed_manual_reconciliation")
        raise
