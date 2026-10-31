# Dependency maintenance architecture

[Technical guide](TECHNICAL_GUIDE.md) · [Security](TECHNICAL_GUIDE.md#security-and-decision-rights)
· [Activation and operations](dependency-maintenance-setup.md)

The owner selected GitHub Actions and automatic PRs for verified security fixes
and compatible patch/minor updates. Merge and deployment remain human actions.
This is a separate standing policy; the existing manual patch tool still requires
its exact, expiring approval for other changes.

## Flow

```text
Guardian repository: Monday 07:00 Malaysia or manual Actions run
  -> read-only SIS main checkout, pinned commit
  -> regular committed source export; exclude credentials/config hooks
  -> fresh baseline container: frozen install, advisory/resolved inventory
  -> deterministic stable compatible version selection
  -> baseline lint / types / unit / build / integration / browser checks
  -> fresh candidate: exact selected versions + regenerated lockfile
  -> same candidate checks, advisory delta, source integrity
  -> optional bounded TypeScript repair, fresh candidate and full re-verification
  -> host-generated file hashes and verification manifest
  -> separate trusted publisher job: independently validate artifacts/base/policy
  -> new Guardian branch and SIS pull request
  -> independent SIS-side PR verification of the merge checkout
  -> human reviews, merges and deploys
```

The optional interpretation job reads minimized technical evidence. Claude cannot
choose versions, mark checks passed, authorize writes or affect the publisher.
The separate optional repair planner proposes only structured mechanical recipes;
the controller and publisher enforce their scope independently.

## How two repositories cooperate

GitHub allocates a temporary hosted runner to the Guardian workflow. Checkout
downloads Guardian's trusted controller and a separate copy of the private SIS
repository, using a scoped read token. Neither repository moves. The controller
exports SIS's pinned commit into disposable baseline/candidate directories and
mounts them into isolated containers. A separate job uses the scoped writer only
to create a branch and PR in SIS. The VPS is not involved.

SIS keeps its own small PR workflow and reviewed verifier assets under `.github`.
It checks the PR's merge checkout using verifier scripts from the base commit,
with read-only GitHub permissions, no model key, and no production credentials.
The initial CI setup requires human review/merge before that trusted base exists.
Normal PRs cannot substitute their own verifier code for base-branch scripts.

## Update and security policy

- Package releases and known advisories are distinct facts. Newer does not mean
  vulnerable; an advisory does not prove this application is exploitable.
- Compare resolved installed versions separately from manifest declarations.
- Select stable same-major upgrades. For 0.x, preserve its minor version because
  minor releases may break compatibility. No prereleases, downgrades, new packages,
  dependency removals, new overrides, script changes or broad range changes.
- Updated ranges are narrowed to exact selected versions. Candidate resolved
  versions must match selection, so registry changes cannot bypass the decision.
- Normal releases must be seven days old. A directly affected package can bypass
  that age delay; the resulting candidate must still pass the advisory delta gate.
- Deprecated releases are excluded. Missing/malformed registry or audit evidence
  fails closed. Newly introduced or more severe reported advisories block a PR.
- Existing advisories can remain: PRs explicitly state this. Major-only fixes and
  transitive overrides require a human migration review.
- The initial implementation groups eligible updates into one bounded batch.
  One failing update blocks that batch; automatic subset/bisection is future work.

## Isolation and verification

Website code executes in fresh Docker containers on GitHub-hosted runners, never
on the shared website/Guardian VPS. Containers have a read-only root, limited
CPU/memory/processes, dropped capabilities, no Docker socket, no host ports or
production environment, and only their disposable work directory is writable.

Trusted backend services first bootstrap on a loopback-bound bridge, then move to
a fresh internal network with all bootstrap attachments removed and aliases kept.
Mount/network/port audits, quotas and a blocked-egress probe must pass before any
website SQL or code executes. Host-side setup uses the gateway IP discovered and
validated against the owned private subnet. This avoids relying on published
ports after isolation and grants no website code a bootstrap-network phase.

Install/audit may contact public registries with no credentials; project scripts
and pnpm hooks are disabled for installation. Executable test/build stages use
a private internal Docker network with real disposable backend services. No arbitrary
commands come from the model or registry metadata. Timed-out containers are removed.

The baseline and candidate use the same image ID and cached public font fixtures.
Required checks: strict/frozen installation, ESLint, TypeScript, unit tests, build,
integration tests and Playwright. Missing checks and baseline failures block PRs.
Native packages requiring install scripts need an explicit future reviewed policy;
the controller does not turn scripts on to make a failing build pass.

The new verifier starts a fresh Supabase stack for each baseline/candidate, applies
bounded repository migrations and seeds test content/accounts. Broad browser/build
checks use `E2E_TEST_DATA=0`; existing mocked unit/integration failure cases remain.
Real database access policies, password authentication, Storage and browser MFA
must pass. A separate process also tests the documented password-only UAT mode:
anonymous rejection, real admin draft creation/read/edit/deletion, independent
database persistence, private-draft denial and actual sign-out. Neither profile
uses success interception or saved sessions; both proofs are required. The broad
browser suite retains its MFA-on configuration and disclosed legacy UI skips.
Only disposable signing/API keys enter application containers. See
[backend operations and evidence](dependency-maintenance-setup.md#disposable-backend).
Google font files are
fetched from fixed public hosts before test execution.
Next's font test hook receives an explicit serializable URL-to-CSS map; a small
trusted server supplies only hashed cached font files over container loopback
during the unchanged `pnpm run build` command. No host port is published and test
egress remains blocked. A Proxy-only map is incompatible with Turbopack's JSON
evaluation, so it is not used. Unsupported font
hooks/toolchain changes fail the baseline instead of silently permitting egress.
The pinned Playwright toolchain must be reviewed when browser revisions change.

Passing checks establishes covered local-service behavior, not all hosted Supabase,
mail, authentication-provider, customer-data or production-load behavior.

## Publishing and evidence

The package manifest, lockfile, any approved component repairs and host-generated
`verification.json` cross into the publisher job. No candidate scripts run there.
A fingerprint from the
trusted verification job binds the manifest; it is not taken from downloaded data.
The publisher checks hashes, semantic dependency-only changes, all stages, advisory
delta and the current SIS base. Only declared dependency/repair files may enter a commit.
It has no merge, default-branch update, force-push or deployment route.

A deterministic branch identifies duplicate/closed PRs; an existing open Guardian
dependency PR prevents another batch PR until it is reviewed/closed. Partial branch creation
requires reconciliation; do not delete state or blindly retry an uncertain write.
If main moves, rerun verification. Branch protection is not assumed to be available;
the owner still needs to review checks and code before merging.

Artifacts stay private in Actions for 30 days. Full package/test output is withheld
from model inputs and automatic logs; phase statuses and safe failure types remain.
Command failures also record the failed stage and fixed diagnostic labels (for
example font/module/resource-limit signals), never raw source or error prose.
Browser failures include bounded Playwright counts and failed source file/line
locations. Page contents, credentials, test titles and raw error messages are
excluded from this diagnostic summary.
`guardian dependency-review --input verification.json --llm claude` can generate a
saved evidence-backed review; importing JSON never grants publishing authority.

## Bounded compatibility repairs

Repairs default off. Only a candidate TypeScript failure after a passing baseline
can trigger one planning attempt. Lint/build/security failures are not auto-fixed.
Supported errors must identify an existing `src/components/public/*.ts(x)` file,
including nested directories. Authentication, forms, admin, validation, backend,
tests, workflows and configuration remain outside automatic repair authority.

Claude receives at most three eligible original files (32 KiB each, 64 KiB total
context) and bounded compiler diagnostics. Source/comments are untrusted data;
credential patterns block submission. This is an explicit exception to audit
reasoning's no-source-input policy, enabled only by the separate repair setting.
It proposes at most eight import/member/JSX-prop renames tied to an updated
React/Next dependency and observed compiler line. No arbitrary code or commands.

A trusted pinned TypeScript parser applies exactly matching AST edits. It rejects
ambiguous targets, shadowed bindings, unsafe names and malformed syntax. Budgets:
three existing files, 80 added/deleted lines total. Failed candidate state is
discarded; the repaired candidate starts fresh, repeats frozen install, inventory,
advisory checks and every test stage. A second failure blocks the batch.
Browser execution stops after its first confirmed failed test; a passing browser
stage still requires the entire suite to pass. Fixed JSON progress events mark
each stage as running/passed. Source integrity is checked after each stage and
on errors; violations report bounded safe path names, not file contents. Timeout
and output-budget failures retain only fixed diagnostic signals in saved reports.

The publisher fetches original files from the tested Git commit, independently
replays the recipe with a separately installed trusted parser and compares exact
bytes. A small-looking arbitrary patch is insufficient. Human review still checks
semantic behavior; these recipes do not guarantee correct migration logic.

## Current rollout status

The real-service verifier is implemented on Guardian's feature branch and vendored
into [SIS CI setup PR #4](https://github.com/KeeLekHeng/sisweb/pull/4). This is a
human-reviewed CI change; automatic dependency repairs cannot modify tests,
configuration, backend or authentication code. No production/VPS changes occurred.

Controlled runs proved [standard startup/SQL](https://github.com/KeeLekHeng/sisweb/actions/runs/41028651056)
and [bootstrap-to-internal isolation](https://github.com/KeeLekHeng/sisweb/actions/runs/41031844785).
[Internal-from-start](https://github.com/KeeLekHeng/sisweb/actions/runs/41031839505)
reproduced the original CLI startup failure before website input. The verifier
uses the proven transition with its isolation gates intact.

[Full run 41041467795](https://github.com/KeeLekHeng/sisweb/actions/runs/41041467795)
passed all seven stages, real schema/RLS/Auth/Storage, public-signup denial, MFA,
isolation, egress and cleanup: 308 browser passes, zero failures/flaky tests,
88 skips. Source review accounts for 51 authenticated legacy UI instances and
37 intentional project/viewport skips. The iframe focus defect was corrected
with one CSS declaration; the original keyboard assertion remains unchanged.
The contact test now opens its real panel before checking links. PR #4 also has
34 Linux screenshot references captured from approved main
`11a2d83082b16c5d5eb659d0d22db3a79842609a`; owner review is required. Existing
Windows references and thresholds are unchanged; normal runs cannot update them.

SIS explicitly documents `REQUIRE_ADMIN_MFA=false` for UAT in its README and
admin-session guide. The owner approved a small real admin smoke test in that
mode while retaining the separate MFA-on check and leaving the extensive legacy
UI suite outside MVP coverage. Both profiles are now required by the controller
and publisher. [Full run 41163143674](https://github.com/KeeLekHeng/sisweb/actions/runs/41163143674)
passed both admin profiles, all seven stages and cleanup: 308 broad browser passes,
zero failures/flaky tests, 88 disclosed skips. Guardian's local suite passed 428
tests with two Windows skips. This is successful SIS verification, not yet paired
dependency-upgrade proof.

The PR-event check stops at the explicit bootstrap guard because the reviewed
base does not yet contain four new verifier assets. This occurs before website
installation/tests; it is distinct from the manual exact-head result. Initial
setup still needs owner review/merge. A paired dependency-upgrade trial remains
pending, needs a scoped SIS read-token secret in Guardian Actions, and must pass
both copies before any dependency PR. Publishing needs its separate writer and
explicit activation. Nothing here merges, deploys or activates the workflow.
