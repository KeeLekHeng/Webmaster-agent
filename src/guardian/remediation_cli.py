"""Manual owner CLI; never exposed as LLM tools or scheduled graph nodes."""
import json
import os
from pathlib import Path

from .models import Report
from .network import enabled
from .remediation import ApprovalStore, create_pull_request, identity, make_proposal, validate_proposal
from .repository import GitHubRepository, LocalRepository, RepoConfig, sha


COMMANDS = {"identity", "repo-inspect", "propose", "proposal-check", "approve", "revoke", "create-pr"}


def register(commands):
    commands.add_parser("identity", help="Show authenticated local OS principal for owner configuration")
    for name in sorted(COMMANDS - {"identity"}):
        cmd = commands.add_parser(name)
        cmd.add_argument("--site", required=True)
        cmd.add_argument("--repositories", default="config/repositories.json")
        if name in ("repo-inspect", "propose"):
            cmd.add_argument("--repo-path", help="Read committed local files instead of GitHub API")
        if name == "propose":
            cmd.add_argument("--report", required=True)
            cmd.add_argument("--evidence", required=True, nargs="+")
            cmd.add_argument("--path", required=True)
            cmd.add_argument("--replacement", required=True)
            cmd.add_argument("--output", default="data/proposals")
        if name in ("proposal-check", "approve", "create-pr"):
            cmd.add_argument("--proposal", required=True)
        if name in ("approve", "revoke", "create-pr"):
            cmd.add_argument("--approval-database", default="data/approvals.sqlite3")
        if name == "approve":
            cmd.add_argument("--artifact-hash", required=True)
            cmd.add_argument("--minutes", type=int, default=30)
        if name in ("revoke", "create-pr"):
            cmd.add_argument("--approval-id", required=True)


def run(args):
    enabled()
    if args.command == "identity":
        print(identity())
        return 0
    config = RepoConfig.model_validate(json.loads(Path(args.repositories).read_text(encoding="utf-8"))[args.site])
    if args.command in ("repo-inspect", "propose"):
        repository = LocalRepository(args.repo_path, config) if args.repo_path else GitHubRepository(
            config, os.getenv("GUARDIAN_GITHUB_READ_TOKEN"))
        if args.command == "repo-inspect":
            revision = repository.revision()
            files = {}
            for path in config.read_paths:
                content = repository.read(path, revision)
                files[path] = {"bytes": len(content), "sha256": sha(content)}
            print(json.dumps({"repository": f"{config.owner}/{config.name}", "base_sha": revision,
                              "files": files, "mode": "read-only"}, indent=2))
            return 0
        report_path = Path(args.report)
        if report_path.stat().st_size > 1048576:
            raise ValueError("Report exceeds input size limit")
        report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
        directory, digest = make_proposal(args.site, repository, args.replacement, args.path,
                                          report, args.evidence, args.output)
        print(f"Pending human review: {directory / 'REVIEW.md'}\nArtifact SHA-256: {digest}")
        return 0
    if args.command == "proposal-check":
        _, digest, _ = validate_proposal(args.proposal, config, args.site)
        print(f"Artifact integrity and isolated patch check passed. SHA-256: {digest}")
        print("Website build/tests not executed. No approval or remote write performed.")
        return 0
    store = ApprovalStore(args.approval_database)
    if args.command == "approve":
        approval_id = store.approve(args.proposal, config, args.site, args.artifact_hash, args.minutes)
        print(f"Local approval recorded: {approval_id}. No remote write performed.")
    elif args.command == "revoke":
        store.revoke(args.approval_id, config, args.site)
        print("Approval revoked.")
    elif args.command == "create-pr":
        url = create_pull_request(args.proposal, config, args.site, args.approval_id, store,
                                  os.getenv("GUARDIAN_GITHUB_WRITE_TOKEN"))
        print(f"Draft PR created: {url}. Human merge/deployment required.")
    return 0
