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
  -> host-generated file hashes and verification manifest
  -> separate trusted publisher job: independently validate artifacts/base/policy
  -> new Guardian branch and SIS pull request
  -> human reviews, merges and deploys
```

The optional interpretation job reads minimized technical evidence. Claude cannot
choose versions, mark checks passed, authorize writes or affect the publisher.

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

Install/audit may contact public registries with no credentials; project scripts
and pnpm hooks are disabled for installation. All executable test/build stages use
network-none with loopback available for local synthetic services. No arbitrary
commands come from the model or registry metadata. Timed-out containers are removed.

The baseline and candidate use the same image ID and cached public font fixtures.
Required checks: strict/frozen installation, ESLint, TypeScript, unit tests, build,
integration tests and Playwright. Missing checks and baseline failures block PRs.
Native packages requiring install scripts need an explicit future reviewed policy;
the controller does not turn scripts on to make a failing build pass.

Current SIS supports synthetic public data, local mock authentication and PGlite
tests. Google font files are fetched from fixed public hosts before test execution;
Next's font test hook serves cached files inside the container. Unsupported font
hooks/toolchain changes fail the baseline instead of silently permitting egress.
The pinned Playwright toolchain must be reviewed when browser revisions change.

Passing checks establishes covered synthetic behavior, not all live Supabase,
mail, authentication-provider, customer-data or production-load behavior.

## Publishing and evidence

Only `package.json`, `pnpm-lock.yaml` and host-generated `verification.json` cross
into the publisher job. No candidate scripts run there. A fingerprint from the
trusted verification job binds the manifest; it is not taken from downloaded data.
The publisher checks hashes, semantic dependency-only changes, all stages, advisory
delta and the current SIS base. Only two files may enter a new branch/commit.
It has no merge, default-branch update, force-push or deployment route.

A deterministic branch identifies duplicate/closed PRs; an existing open Guardian
dependency PR prevents another batch PR until it is reviewed/closed. Partial branch creation
requires reconciliation; do not delete state or blindly retry an uncertain write.
If main moves, rerun verification. Branch protection is not assumed to be available;
the owner still needs to review checks and code before merging.

Artifacts stay private in Actions for 30 days. Full package/test output is withheld
from model inputs and automatic logs; phase statuses and safe failure types remain.
`guardian dependency-review --input verification.json --llm claude` can generate a
saved evidence-backed review; importing JSON never grants publishing authority.

## Current rollout status

Implementation and mocked boundary tests are local work. The shared VPS and SIS
production have not been modified by this feature. A real Actions trial, provider
credentials and owner activation are still required. Do not claim a successful
dependency build or PR from mocked tests alone.
