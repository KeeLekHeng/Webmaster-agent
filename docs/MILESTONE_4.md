# Milestone 4 local implementation and review bundle

Implemented on 2026-10-19: scoped repository reading, isolated patch proposals,
evidence/artifact hashes, manual OS-identity approvals, expiry/revocation and a
disabled-by-default draft-PR executor. The audit/scheduling graph remains read-only
and has no remediation tools. No new agents, provider dependencies or credentials
were created.

## Concrete proposal for review

Current bundle: `data/proposals/2c6fe0c3eb014de9bb193d6dd251f1bc/`.

- Repository: KeeLekHeng/sisweb.
- Base commit: `9791eefcd5b5535c81c40cc3d108eb0b981d695e`.
- File: `next.config.ts` only.
- Proposed addition: `Strict-Transport-Security: max-age=86400`.
- Evidence: E003, E006, E009, E012, E015, E018, E021, E024 and E027 from audit
  `7174faecaa6e48b19179663f404858ef`, where the header was absent on nine responses.
- Artifact SHA-256:
  `087880e2637caa3b14ee2b5a0c34ad069faea555d51eb1ffd5227602ea671444`.

This is a review proposal, not an applied fix. One day is a bounded initial HSTS
duration; includeSubDomains and preload are absent because their suitability has
not been established. The owner should review HTTPS/edge policy and run the
website's normal build/tests in an appropriately isolated environment before
publishing or deploying. Source changes may not reflect active edge configuration.
No deployment is authorized by this proposal.

`before.txt` and `after.txt` contain only the copied allowlisted committed file.
`diff.patch` contains the exact change. `evidence.json` contains bounded scanner
facts without raw HTML/header text, URLs or credentials. `proposal.json` binds
source revision, site/repository/path, before/after/diff/evidence hashes, requested
action, finding evidence IDs and validation limits. `REVIEW.md` explains the bundle.
An earlier preliminary bundle exists locally; the ID above is the current review
bundle with evidence hashing.

## Read-only integration

`config/repositories.json` selects the repository and exact readable/patchable
paths for each configured site. The initial read scope is `package.json`,
`pnpm-lock.yaml` and `next.config.ts`; only `next.config.ts` is patchable.
Environment files, Git metadata, workflow paths, traversal, shell metacharacters
and Windows device paths are blocked. No general-purpose shell executor exists.

The local adapter reads committed Git objects using fixed argument arrays with
shell execution disabled, hooks/fsmonitor disabled, bounded output and timeouts.
It does not copy working-tree edits, ignored files, node_modules or secrets.
Tracked symlinks, submodules and executable file modes are rejected.
Local repository identity comes from the owner's explicit path/configuration;
publishing additionally verifies the pinned content against the configured GitHub
repository. The adapters do not execute repository instructions or test scripts.

The GitHub adapter uses fixed HTTPS API routes, no redirects, no proxy inheritance,
bounded responses and a dedicated read credential. It validates pinned tree modes
before fetching content, and checks blob hashes. No ambient GH_TOKEN, GITHUB_TOKEN
or Git credential is used by the API adapter. The existing local adapter was
verified against the actual website checkout. The new GitHub API path was tested
with mock HTTP responses; live API credential access is not yet configured.

## Validation and trust limits

`proposal-check` verifies file/path scope, exact hashes, reconstructed unified diff
and `git apply --check` in a temporary copy. It never applies the patch to the
website checkout. No website packages were installed, and no website build,
application tests, production requests or form submissions were run for this work.
These checks establish artifact integrity/application, not functional correctness.
The proposal also does not prove the cited finding semantically warrants the patch;
that is part of human review.

## Approval and publishing policy

Defaults are `allow_pr_creation: false` and `approver_ids: []`. A missing response
does not authorize anything. Owner enrollment and enabling publishing are separate
explicit decisions; no such changes were made during implementation.

Approvals use the authenticated current OS principal: Windows SID from the system
whoami executable, or the actual POSIX user ID. Environment-provided usernames and
model-supplied identities are not accepted. The eligible principal must be explicitly
listed in repository policy. An approval binds site, proposal, exact manifest hash,
authenticated approver and expiry (at most 60 minutes). SQLite stores decisions,
revocations, execution attempts and receipts without tokens or raw API errors.

This is a local trusted-workstation boundary. Another process running as the same
OS user can invoke the same CLI or alter local configuration/database files. It
is not a separately authenticated remote approval service. A server deployment
needs a protected human approval channel/identity boundary before enabling writes.

Publishing checks the exact artifact, current eligible actor and approval before
network preflight. The configured base must be the repository default branch,
protected, still at the approved SHA, with matching original file content. Approval
consumption is transactional and single-use; expiry, revocation and kill switch
are rechecked before every mutation. Revocation can stop subsequent stages of an
already-started operation, but cannot reverse an in-flight request or completed
remote changes.

The executor can create only `guardian/<proposal-id>`, update the approved file
there and create a draft PR. It has no merge, deploy, force-push, production SSH,
DNS/firewall/credential or backup-restore operation. API side effects are not one
atomic transaction: failures/interruptions may leave a branch or PR, and retries
are blocked pending human reconciliation. Concurrent remote changes remain a
reason for human review; a draft PR is never permission to merge/deploy.

The proposed GitHub credentials must be limited to this repository:

- Reader: Contents read plus required metadata access.
- Writer: Contents write and Pull requests write plus required metadata access.
  Use a separate credential; using the configured reader token as writer is denied.

These permissions follow GitHub's
[contents API](https://docs.github.com/en/rest/repos/contents) and
[pull-request API](https://docs.github.com/en/rest/pulls/pulls) documentation.
No real GitHub token was created, inspected or scope-verified. Opaque credential
scope is an operator provisioning requirement, not something the local policy
can attest from the token string. Before enabling publishing, verify permissions,
live branch protection and any branch/PR automation in the website repository.

## Manual commands

Read-only inspection and validation work now:

```powershell
.venv\Scripts\guardian repo-inspect --site estateplanning --repo-path C:/Users/User/Desktop/Work/sisweb
.venv\Scripts\guardian proposal-check --site estateplanning --proposal data/proposals/2c6fe0c3eb014de9bb193d6dd251f1bc
```

To prepare a different bounded proposal, supply an owner-prepared replacement:

```powershell
.venv\Scripts\guardian propose --site estateplanning --repo-path <local-checkout> --report <report.json> --evidence E003 --path next.config.ts --replacement <candidate-file>
```

Future approval/publishing commands are available via `guardian identity`,
`guardian approve --help`, `guardian revoke --help` and `guardian create-pr --help`.
They are not invoked automatically. Keep policy disabled until the exact patch is
reviewed and credential/identity prerequisites have been explicitly settled.

## Verification outcome

The full suite passes 121 tests. Remediation cases cover actual isolated Git patch
application, committed-versus-working-tree reads, exact artifact/evidence hashes,
path/action/site restrictions, symlink rejection, missing/expired/revoked approvals,
wrong identities/hashes, revocation/expiry between API writes, protected unchanged
base checks, separate credentials, a mocked successful draft PR, consumed approval
reuse and partial API failure with manual reconciliation. Mocked API operations
never contacted GitHub. No real approval record or PR was created.

The actual website checkout remains clean and at the pinned commit. The proposed
patch passes isolated Git validation. Live authenticated API access, token scope,
branch protection and real PR publishing remain unverified/disabled. Milestone 4's
local implementation is ready for review; no claim of live publishing acceptance
is made. Production deployment remains human-only; local approval trust and human
review capacity remain known limits.
