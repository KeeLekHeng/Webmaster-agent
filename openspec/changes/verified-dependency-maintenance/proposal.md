# Verified dependency maintenance

## Why
The owner authorized weekly security/compatible dependency maintenance and
automatic SIS pull requests after isolated verification, with human merge/deploy.
They selected GitHub Actions and security fixes plus patch/minor updates.
The current shared VPS must not build or execute website dependency code.

## What Changes
- Expand structured AI explanations with impact, review steps and verification.
- Inventory pinned manifests/lockfiles; distinguish advisories from new releases.
- Test the pinned baseline and candidate in disposable, credential-free containers
  on GitHub-hosted runners; mock external integrations and deny test egress.
- Publish package.json/pnpm-lock.yaml and optional bounded compatibility recipes
  after all required stages pass (including fresh full verification after repairs),
  rechecking base revision, artifact hashes and policy in a separate trusted job.
- Prepare independent SIS PR CI using reviewed base verifier assets.
- Default publication disabled until scoped Actions secrets and owner activation.
- No automatic major upgrades, merges, deployments or production credentials.

## Capabilities
### New Capabilities
- `verified-dependency-maintenance`: weekly review, isolated verification and
  scoped PR publication under the owner's standing policy.
### Modified Capabilities
- Structured advisory interpretation includes actionable review/verification fields.

## Impact
Guardian Python modules, tests, GitHub Actions workflow, sandbox assets and operator
documentation. Existing manual proposal approval remains unchanged for other edits.
