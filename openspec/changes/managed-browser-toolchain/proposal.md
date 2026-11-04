# Separate browser-toolchain upgrades

## Why
The first real dependency trial passed its baseline but selected Playwright 1.64.1
against the reviewed 1.62.1 browser image. Candidate integration could not launch
Chromium. The owner approved managing these upgrades separately while retaining
all checks for application updates.

## What changes
- Derive the reviewed browser version from the trusted, pinned Dockerfile.
- Keep direct Playwright-family packages unchanged in automatic batches; report
  eligible updates and advisories as explicit manual-review actions.
- Independently reject browser-package changes in the publisher and reject
  resolved toolchain drift before candidate checks.
- Allow manually dispatched non-main verification previews, with publishing and
  model-key jobs denied independently of repository flags.
- Refresh immutable GitHub Action pins to native Node 24 releases.

## Scope
Trusted Guardian CI/controller changes. No reduced assertions, test skips,
production access, repository secret changes, automatic merges or deployments.
A later coordinated browser-package/image/reference update remains human-reviewed.
