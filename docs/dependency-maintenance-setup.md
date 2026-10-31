# Enable verified SIS dependency maintenance

[Architecture and limitations](dependency-maintenance.md) · [Technical guide](TECHNICAL_GUIDE.md)

Start with verification only. No SIS dependency PR is created merely by pushing
the Guardian workflow. Settings below belong to **KeeLekHeng/Webmaster-agent**.

## Review, merge and deploy

1. Review [SIS PR #4](https://github.com/KeeLekHeng/sisweb/pull/4), including the
   Linux reference images and its successful manual full run at the exact head.
   Its PR-event bootstrap failure happens before website testing because the
   reviewed base lacks the new verifier. Keep that guard intact.
2. Merge the reviewed SIS setup, then manually run **SIS isolated PR verification**
   on `main`. After that pass, deploy SIS through its normal owner-run deployment
   procedure if desired. The runtime change is the small iframe focus CSS fix;
   the verifier assets are CI-only. No dependency or production MFA setting changes.
3. Review and merge [Guardian PR #1](https://github.com/KeeLekHeng/Webmaster-agent/pull/1).
   These maintenance jobs run in GitHub Actions; a Guardian VPS package deployment
   is not needed for them. Do not install the disposable backend on the shared VPS.
4. Configure the scoped reader and run the paired baseline/candidate trial below
   with publishing disabled. Enable dependency PR publishing only after that
   trial passes. Merging these setup PRs alone does not prove an upgrade or activate
   publishing; no production deployment occurs automatically.

## Credentials

Use GitHub Settings → Developer settings → Personal access tokens → Fine-grained
tokens, or separately installed GitHub App credentials. Select only the SIS repo.
Use the reader for the first verification-only trial. Add the independently
scoped writer only when ready to enable dependency PR publishing:

| Actions secret | Selected repository | Repository permissions |
| --- | --- | --- |
| `GUARDIAN_SIS_READ_TOKEN` | `KeeLekHeng/sisweb` only | Contents: read; metadata read |
| `GUARDIAN_SIS_WRITE_TOKEN` | `KeeLekHeng/sisweb` only | Contents: read/write; Pull requests: read/write; metadata read |

No workflow, administration, deployment, website SSH or Supabase access is needed.
The writer is only exposed to the trusted publisher step. The reader is only used
by checkout with credential persistence disabled. Neither enters the test container.
An opaque PAT can have broader rights than the application uses; scope it narrowly.

In the **Guardian repository**, open Settings → Secrets and variables → Actions →
Secrets → New repository secret. Add the required value there, never in chat or Git.
Existing suitable scoped credentials can be reused after reviewing their permissions;
do not copy production `.env` files into Actions. Set an expiry and plan renewal.

## Variables and first trial

Under the same Actions settings, open **Variables** → New repository variable:

| Variable | Initial value |
| --- | --- |
| `GUARDIAN_MAINTENANCE_ENABLED` | `true` when ready for the first verification |
| `GUARDIAN_DEPENDENCY_PRS_ENABLED` | `false` initially |
| `GUARDIAN_DEPENDENCY_AI_ENABLED` | `false` initially |
| `GUARDIAN_COMPAT_REPAIRS_ENABLED` | `false` initially |

Once the reviewed workflow/code is on Guardian's main branch, open Actions →
**Verified SIS dependency maintenance** → Run workflow → main → Run workflow.
Inspect `verify` and download `dependency-verification`. A blocked baseline is a
real setup/test problem, not permission to skip a check. Resolve it and rerun.

Check the installed-version inventory, advisories, selected updates, both stage
maps, image ID and coverage limitations. No update may be needed that week.
The normal schedule is Monday 07:00 Malaysia (Sunday 23:00 UTC), independent of
the existing Monday 09:00 VPS reporting timer. CI results are not yet automatically
inserted into that Telegram digest. GitHub provides workflow/PR notifications.
`GUARDIAN_MAINTENANCE_ENABLED=true` allows both manual and scheduled verification.
For a manual-only trial, return it to `false` afterwards until weekly execution
is desired; the separate publishing flag stays `false` throughout the first trial.

## Enable automatic PRs

After a successful real verification trial, set
`GUARDIAN_DEPENDENCY_PRS_ENABLED=true` and run the workflow again. A verified
candidate can then create a scoped dependency maintenance SIS PR. No per-PR publishing approval
is required under this standing policy; merge and deployment remain yours.
Review the first real PR and its evidence before treating the automation as proven.

## Optional comprehensive AI report

Add the Actions secret `GUARDIAN_MAINTENANCE_CLAUDE_KEY`, and variable
`GUARDIAN_MAINTENANCE_MODEL` with your currently permitted Claude model ID.
Then set `GUARDIAN_DEPENDENCY_AI_ENABLED=true`. The separate interpretation job
uploads a `dependency-review` report; it cannot approve the publishing job.

Existing audit/SEO interpretation also gains impact, review action, verification
and alternative-explanation fields after the upgraded Guardian package is installed
on the VPS. Publishing this workflow does not update that VPS package.

## Optional compatibility repairs and SIS CI

After the baseline trial, use the same Claude Actions secret/model settings and
set `GUARDIAN_COMPAT_REPAIRS_ENABLED=true` to permit one bounded TypeScript repair
attempt. The key stays on the trusted controller host, never in website containers.
Eligible private display-component source is sent to Claude for this feature;
leave it false if source sharing is not desired. See the architecture scope rules.
PRs can then include mechanical component repairs as well as the two package files.

The owner merged SIS [PR #4](https://github.com/KeeLekHeng/sisweb/pull/4) and Guardian
[PR #1](https://github.com/KeeLekHeng/Webmaster-agent/pull/1). Post-merge
[SIS main verification](https://github.com/KeeLekHeng/sisweb/actions/runs/41180334440)
passed the bootstrap guard and every stage, with one disclosed browser retry.
The earlier bootstrap failure was before website testing because the reviewed
base lacked the new assets. Subsequent SIS PRs use the installed base verifier;
no extra secrets are needed in SIS. The owner provided Guardian's scoped reader
and activation settings; the first trial successfully checked out SIS but blocked
the upgraded candidate on a browser-toolchain mismatch. See the canonical
[current rollout status](dependency-maintenance.md#current-rollout-status) before
enabling publishing or changing eligibility policy.
Do not infer a successful build from setup/mocked tests. If branch protection is
unavailable, inspect both repositories' successful checks before merging an upgrade.

The SIS assets are vendored from Guardian's `maintenance/` and maintenance Python
modules. Changes to the trusted verifier need a separate reviewed SIS setup PR;
dependency automation cannot update CI assets. No automatic deployment is included.

## Disposable backend

Basic startup passed in [control run 41028651056](https://github.com/KeeLekHeng/sisweb/actions/runs/41028651056).
Use the SIS workflow's manual **check: backend-startup** option to diagnose the
networking restriction before another full website run. This
separate control starts only trusted service images on a standard bridge with
loopback bindings, performs a real temporary-table write/read and cleans up.
It receives no SIS source/migrations or production credentials, and its
`backend-startup-only` artifact cannot authorize dependency publishing. A pass
proves basic startup only. Step 2 must separately prove restricted networking and
resource limits before candidate code is introduced; the main verifier's existing
isolation requirements remain in force.

`startup_network=bridge` establishes the standard control; `internal` attempts
the same startup directly on an internal network. `transition` starts trusted
services on the control network, moves them to a fresh internal network while
preserving DNS aliases, removes all bootstrap attachments, applies the existing
service audits/quotas, checks blocked egress and repeats the real SQL probe.
Every mode remains diagnostic-only and requires successful cleanup.

The controlled comparison is complete: internal-from-start trial
[41031839505](https://github.com/KeeLekHeng/sisweb/actions/runs/41031839505) failed
before website input, while transition trial
[41031844785](https://github.com/KeeLekHeng/sisweb/actions/runs/41031844785) passed
isolation, quotas, blocked egress, real SQL and cleanup. The full verifier now uses
that sequence. Its host-side setup discovers the private gateway address from
Docker inspection and verifies that it belongs to the owned network's subnet.

Prerequisites: read the [isolation policy](dependency-maintenance.md#isolation-and-verification)
and [security rights](TECHNICAL_GUIDE.md#security-and-decision-rights). This feature
runs on a disposable Linux amd64 Actions runner with Docker and at least 6 GiB RAM.
The shared VPS and ordinary Windows listener are unsuitable for this verifier.

The trusted installer verifies the pinned Supabase CLI 2.119.0 archive SHA256.
Trusted configuration disables candidate hooks, automatic seeds/migrations and
external providers. Each source copy gets a unique private network and fresh
database, Auth and Storage. Before repository SQL runs, the controller audits
ownership, mounts, ports and networking, applies quotas and probes blocked egress.
Only loopback backend ports are permitted. Application containers receive no
production credentials, repository tokens or Docker socket.

Repository migrations execute inside the disposable database. A literal-only
parser reads public fixture content inside Docker; it never imports website code
on the host. Synthetic career records and a test administrator support real
application queries, password login, MFA and management-page checks. Test keys,
passwords and MFA material are not saved in reports. Existing password-only legacy
admin tests remain outside coverage unless compatible with MFA; provider/email
delivery remains intercepted or outside scope.

SIS documents password-only UAT with `REQUIRE_ADMIN_MFA=false`. The trusted probe
starts a separate application process in that mode, uses a fresh browser context
and generated account, checks anonymous rejection, creates/reads/edits/deletes a
synthetic draft through real application APIs/editor reads, independently checks
database persistence and private-draft denial, then signs out and verifies access
is denied. No production password, session key or authenticator code is required.
The MFA-on probe remains mandatory; broad browser mode and legacy skips are unchanged.
The publisher rejects earlier evidence without `uat_admin_browser=passed`.

The email/password provider is enabled while global public signup remains off.
The verifier creates its synthetic administrator through the local admin API and
requires a real public-signup denial before password/MFA verification. PostgREST
receives its documented SIGUSR1 schema-cache reload after migrations. The literal
fixture parser is installed at an explicit image prefix and verified during the
image build; it does not assume a host/global npm installation path.

The trusted Playwright configuration preserves the website's test suite/projects
but directly launches Next with real mode. The repository's usual E2E launcher
forces mock mode and is unsuitable here. Automatic failure screenshots, traces and
videos are disabled; the required authentication probe captures no images.

The repository initially has Windows screenshot references only. The manual
**check: visual-baseline** mode checks out approved SIS main, builds it using the
same pinned image/fonts and real backend, and prepares Linux references for owner
review. Its private artifact cannot authorize publishing. It also reproduces the
existing contact assertion independently of candidate changes. Normal verification
uses `--update-snapshots=none`: missing or changed references fail rather than
rewriting expected output. Reference images belong to the separately reviewed CI
setup PR; automatic dependency PRs cannot modify tests or reference images.

Version 2 evidence must include successful schema, access-policy, Auth, Storage,
MFA, password-only UAT admin, isolation, egress and cleanup checks. Publishing requires paired baseline and
candidate proofs with matching backend images, migration hashes and seed hashes.
Historical version 1 reports remain readable but cannot authorize new publishing.

Cleanup runs on normal exit, failure and an always-run workflow step. It targets
only this run's labelled disposable resources; it never globally prunes Docker.
Cleanup failure blocks verification. Cancelling a hosted runner may bypass cleanup;
GitHub disposes the runner. Never run this cleanup against a production Docker host.

The SIS PR workflow deliberately loads verifier assets from its reviewed base.
Testing a changed verifier before merging therefore needs an explicit manual run
on the setup branch. An ordinary PR check may still use the older base verifier.
Inspect the run's event, ref and tested SHA before interpreting its result.

## Stop, troubleshoot and recover

For a proposed controller change, select its branch under **Actions > Verified
SIS dependency maintenance > Run workflow**. Non-main dispatches are verification
previews: they cannot publish, invoke repair/interpretation models, or use the
writer. Main retains its explicit activation flags. Inspect the selected ref,
tested SHA and saved report; a green preview does not enable automatic publishing.

Browser-package updates are reported as deferred to a separately reviewed
toolchain change. Coordinate package/lock and reviewed image versions, run all
checks, and explicitly review any visual-reference changes. Do not bypass the
browser or admin tests to accommodate a mismatched image.

- Disable PR creation: `GUARDIAN_DEPENDENCY_PRS_ENABLED=false`.
- Stop new maintenance runs: `GUARDIAN_MAINTENANCE_ENABLED=false` and cancel any
  running workflow in Actions. The VPS STOP marker does not control this CI job.
- A request already in flight can leave a branch/PR; inspect and close it manually.
- If main changed, rerun. If a deterministic branch exists without a PR, compare
  its files/base against the saved artifact before deciding to remove/reconcile it.
- If the baseline fails, fix that independently before blaming an upgrade. If the
  candidate fails, keep production unchanged and review the blocked batch.
- Actions private-repo usage consumes the account's available runner allowance;
  check the account's current billing/usage settings before enabling the schedule.

No feature automatically merges, deploys, restores backups or modifies production.
