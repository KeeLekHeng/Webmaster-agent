# Enable verified SIS dependency maintenance

[Architecture and limitations](dependency-maintenance.md) · [Technical guide](TECHNICAL_GUIDE.md)

Start with verification only. No SIS dependency PR is created merely by pushing
the Guardian workflow. Settings below belong to **KeeLekHeng/Webmaster-agent**.

## Credentials

Use GitHub Settings → Developer settings → Personal access tokens → Fine-grained
tokens, or separately installed GitHub App credentials. Select only the SIS repo.
Create/provide two independently scoped credentials:

| Actions secret | Selected repository | Repository permissions |
| --- | --- | --- |
| `GUARDIAN_SIS_READ_TOKEN` | `KeeLekHeng/sisweb` only | Contents: read; metadata read |
| `GUARDIAN_SIS_WRITE_TOKEN` | `KeeLekHeng/sisweb` only | Contents: read/write; Pull requests: read/write; metadata read |

No workflow, administration, deployment, website SSH or Supabase access is needed.
The writer is only exposed to the trusted publisher step. The reader is only used
by checkout with credential persistence disabled. Neither enters the test container.
An opaque PAT can have broader rights than the application uses; scope it narrowly.

In the **Guardian repository**, open Settings → Secrets and variables → Actions →
Secrets → New repository secret. Add the two values there, never in chat or Git.
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

Review and merge the separate SIS CI setup branch `guardian/setup-pr-verification`
in **KeeLekHeng/sisweb**. Its initial run deliberately fails if the base branch
does not yet contain the reviewed verifier. That bootstrap failure is expected;
review the setup files before merging, then manually run **SIS isolated PR
verification** on main to establish the first real pass. Subsequent SIS PRs use
the reviewed base verifier automatically; no extra secrets are needed there.
Do not infer a successful build from setup/mocked tests. If branch protection is
unavailable, inspect both repositories' successful checks before merging an upgrade.

The SIS assets are vendored from Guardian's `maintenance/` and maintenance Python
modules. Changes to the trusted verifier need a separate reviewed SIS setup PR;
dependency automation cannot update CI assets. No automatic deployment is included.

## Stop, troubleshoot and recover

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
