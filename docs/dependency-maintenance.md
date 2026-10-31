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

The owner merged [Guardian PR #1](https://github.com/KeeLekHeng/Webmaster-agent/pull/1)
and [SIS CI setup PR #4](https://github.com/KeeLekHeng/sisweb/pull/4) on 31 October
2026. Guardian main is `fb89a8f`; SIS main is `6d40faf`. This is a
human-reviewed CI change; automatic dependency repairs cannot modify tests,
configuration, backend or authentication code. Verification made no production/VPS changes.

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
and publisher. [Full run 41164653090](https://github.com/KeeLekHeng/sisweb/actions/runs/41164653090)
passed both admin profiles, all seven stages and cleanup: 308 broad browser passes,
zero failures/flaky tests, 88 disclosed skips. Guardian's local suite passed 432
tests with two Windows skips. This is successful SIS verification, not yet paired
dependency-upgrade proof.

Review amendments consolidated repeated draft checks, bounded server shutdown
and prevented baseline backend proof being relabelled after candidate install
failure. Both PRs were merged as disabled-by-default setup changes.
See the [merge/deployment order](dependency-maintenance-setup.md#review-merge-and-deploy).

The pre-merge PR event stopped at the bootstrap guard because its reviewed base
lacked four verifier assets. Post-merge [SIS main run 41180334440](https://github.com/KeeLekHeng/sisweb/actions/runs/41180334440)
passed the guard, all seven stages, both admin profiles, isolation and cleanup.
It recorded 307 expected browser passes, one flaky case that passed on retry and
88 disclosed skips. That historical SIS summary omitted the retried case's
identity. Later Guardian diagnostics retain retry locations but cannot reconstruct
that old run. This is not a zero-flake claim; no gate changed for this run.

The owner configured the scoped SIS reader and enabled verification. Guardian
[trial 41191170056](https://github.com/KeeLekHeng/Webmaster-agent/actions/runs/41191170056)
checked out SIS main successfully and passed every baseline stage, both admin
profiles and cleanup (308 browser passes, zero flaky cases, 88 skips). It selected
15 compatible upgrades. Candidate install/lint/types/unit/build and real backend
service probes passed, but integration stopped at browser launch before the
candidate browser/admin profiles could run. Candidate Playwright 1.64.1 differs
from the reviewed image's 1.62.1 browser bundle; these versions must match.

The batch introduced no new/worse reported advisory, but existing zod/high and
minimatch/moderate findings remain. This is a blocked upgrade, not evidence that
all 15 selected versions are verified. Publishing was skipped. No dependency PR,
merge or deployment occurred. The owner approved separate reviewed browser-toolchain
updates. Ordinary batches preserve `@playwright/test`, `playwright` and
`playwright-core`, report available versions/advisories as explicit deferrals,
and still require every baseline/candidate stage. The reviewed Dockerfile supplies
the required version; installed baseline and candidate inventories must match it.
The independent publisher rejects browser-package changes and inventory drift.
Deferred updates are never described as verified or fixed.

A browser upgrade requires a separate human-reviewed change coordinating the SIS
manifest/lockfile, Guardian and SIS verifier images, and any reviewed visual
references. Run the complete baseline/candidate checks; review reference changes
explicitly rather than regenerating them to make a failed test pass.

Manual workflow dispatch on a non-main Guardian branch is a read-only preview.
It uses the scoped SIS reader but disables repairs, interpretation and publication.
Both the workflow and publisher require exact `refs/heads/main` for publishing.
The Node 24 action-pin refresh changes Actions' runtime, not the website runtime.

Read-only [preview 41203746397](https://github.com/KeeLekHeng/Webmaster-agent/actions/runs/41203746397)
tested controller `2435a95` against SIS `6d40faf`. It explicitly deferred
Playwright 1.62.1 to 1.64.1 and selected the other 14 updates. Baseline passed all
stages (307 expected browser passes, one retry/flaky pass, 88 disclosed skips).
Candidate install/lint/types/unit/build/integration, both real admin profiles,
isolation and cleanup passed. Browser execution then blocked on two accessibility
assertions at `tests/e2e/search-discovery.spec.ts:158:7`, which expects zero Axe
violations. Partial candidate counts were 68 expected, two unexpected and 326
skipped after early termination; these are not complete-suite coverage.

[Diagnostic run 41205217410](https://github.com/KeeLekHeng/Webmaster-agent/actions/runs/41205217410)
repeated the same 14 updates and identified `label-content-name-mismatch` on `/`
and `/will-writing`. Axe 4.14 enables this rule by default. The shared brand link
overrides its visible motto with `aria-label="SIS home"`. After removing it,
run 41206017601 identified the same defect on the mobile video control, whose
fixed name omitted its visible Watch/Loading text. The separate source repair
[SIS #6](https://github.com/KeeLekHeng/sisweb/pull/6) removes the brand override and
shares the video's state-derived display/ARIA label in `66c1f70`; its status child
alone cannot name the button. The keyboard locator follows the visible name;
its focus/Enter assertions remain. [Paired preview 41207985799](https://github.com/KeeLekHeng/Webmaster-agent/actions/runs/41207985799)
passed all seven stages for both copies and validated artifact hashes: baseline
307 direct passes plus one retry; candidate 306 plus two retries; each had 88 skips
and zero unexpected failures. Both admin profiles, isolation and cleanup passed.
[SIS CI 41207971207](https://github.com/KeeLekHeng/sisweb/actions/runs/41207971207)
passed on `66c1f70` / merge `21913c4`: 308 passes, 88 skips, zero failures/flakes.
[Guardian #2](https://github.com/KeeLekHeng/Webmaster-agent/pull/2) and SIS #6 are
ready for owner review. Publishing remains off; fresh merged-main proof is required.

The separate workflow-only [SIS PR #5](https://github.com/KeeLekHeng/sisweb/pull/5)
passed [run 41203784493](https://github.com/KeeLekHeng/sisweb/actions/runs/41203784493)
on head `3b0b9c2` / merge checkout `2544c47`: all stages, both real admin profiles,
isolation/cleanup, 308 browser passes, zero failures/flaky cases and 88 skips.
Its review/merge is owner-deferred. No merge or deployment occurred.

The follow-up diagnostic summary recognizes the existing public-accessibility
test title only for approved public routes, extracts Axe IDs from a reviewed
Deque v4.14.0 rule vocabulary, and retains source/project locations for failed
and flaky tests. Raw prose, HTML, selectors and unknown route/ID values are not
retained. Parsing failure never changes a test outcome or grants publishing.

Maintenance remains enabled as configured while post-trial weekly/manual
preference is pending. Publishing remains explicitly off; its separate writer
and activation are only relevant after successful paired verification.
