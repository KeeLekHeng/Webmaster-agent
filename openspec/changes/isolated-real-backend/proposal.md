# Isolated real backend verification

## Why
The first SIS CI trials exposed an incomplete sandbox: career pages query a
Supabase endpoint that was never started or seeded. Blanket mocks would hide
database, RLS and authentication regressions. The owner approved implementing
real disposable services with synthetic data and test-only credentials.

## What Changes
- Start pinned local Supabase/Postgres/Auth/Storage in a private disposable network.
- Apply the tested repository's migrations inside the restricted database, then
  seed repeatable public content and a dedicated test account.
- Exercise real anonymous RLS, password authentication, MFA and browser management
  access. Keep existing deterministic failure mocks explicitly separate.
- Exercise the separately documented password-only UAT mode with a small real
  admin draft create/read/edit/delete/sign-out smoke test; retain MFA-on coverage.
- Remove application fixture bypasses from the broad verification environment.
- Require backend evidence for dependency PR publishing; missing coverage blocks.
- Record safe stage/coverage evidence and clean up on failure/cancellation.

## Scope
Trusted CI setup and testing only. No production connection, customer data,
production keys, auth bypass, automatic merge, deployment or changes to standing
dependency repair authority. Existing authenticated UI suites that assume
password-only login remain disclosed as uncovered until separately adapted;
the required browser probes exercise both the actual MFA path and documented
password-only UAT draft lifecycle.

## Impact
Guardian maintenance controller, trusted SIS verifier assets, Actions setup,
boundary tests and linked operator documentation. This is a separately reviewed
CI extension, outside automatic dependency PR file scope.
