## Proposal
- [x] Inspect SIS schema, configuration, observed failures and authorization.
- [x] Specify disposable real-service scope and explicit remaining coverage limits.
## Implementation
- [x] Implement pinned CLI bootstrap, private networking, audits and resource caps.
- [x] Apply migrations and seed synthetic data without host execution of website code.
- [x] Add real RLS/Auth/Storage and MFA browser verification.
- [x] Integrate fresh backend lifecycle into both verifier paths and publisher gates.
- [x] Vendor reviewed assets into the SIS setup branch and document operations.
- [x] Add separate documented UAT admin smoke coverage while retaining MFA-on checks.
## Validation
- [x] Prove minimal trusted startup and real SQL round trip without website input.
- [x] Isolate networking/resource restrictions incrementally after basic startup.
- [x] Test missing backend, unsafe SQL/config, leaked credentials, cleanup, isolation and stale proof boundaries.
- [x] Run Guardian suite, syntax checks and strict OpenSpec validation.
- [x] Run real Actions trials; record actual outcomes and remaining blockers.
- [x] Establish the initial fully passing SIS baseline (41041467795).
- [ ] Obtain paired dependency-upgrade proof with both admin profiles.
- [x] Verify both admin profiles and real draft persistence in the full Actions run.
- [ ] Owner reviews/merges SIS setup; enable dependency trial separately.

## Evidence and remaining blocker
- Startup control 41028651056 passed startup, real SQL and cleanup without website
  input. Internal control 41031839505 failed; transition control 41031844785
  passed isolation, quotas, blocked egress, SQL and cleanup.
- Full run 41041467795 passed all seven stages, schema/RLS/Auth/Storage, public
  signup denial, MFA, isolation, egress and cleanup. Browser: 308 passed, zero
  failures/flaky tests, 88 skips. The one-line iframe transition correction and
  contact-test panel-opening precondition retained their original assertions.
- The owner approved minimal admin coverage matching documented password-only UAT,
  while retaining the MFA-on probe and leaving extensive legacy UI cases skipped.
  Exact-head run 41163143674 passed both profiles, real draft persistence, all
  seven stages and cleanup: 308 broad browser passes, zero failures/flaky tests,
  88 disclosed skips. This is not yet paired dependency-upgrade evidence.
- Local regression: 428 passed, two Windows skips. Strict OpenSpec validation passed.
  Local orchestration tests do not replace the real Actions trial.
- Assets are in SIS PR #4, including 34 Linux references captured from approved
  main and a contact-test panel-opening precondition correction. Owner review and
  merge remain outstanding; no production changes or merges were performed.
- Paired dependency-upgrade proof is still pending. Guardian Actions needs a
  scoped SIS read token before that trial; publishing needs separate activation.
