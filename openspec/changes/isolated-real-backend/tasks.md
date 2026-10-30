## Proposal
- [x] Inspect SIS schema, configuration, observed failures and authorization.
- [x] Specify disposable real-service scope and explicit remaining coverage limits.
## Implementation
- [x] Implement pinned CLI bootstrap, private networking, audits and resource caps.
- [x] Apply migrations and seed synthetic data without host execution of website code.
- [x] Add real RLS/Auth/Storage and MFA browser verification.
- [x] Integrate fresh backend lifecycle into both verifier paths and publisher gates.
- [x] Vendor reviewed assets into the SIS setup branch and document operations.
## Validation
- [x] Prove minimal trusted startup and real SQL round trip without website input.
- [x] Isolate networking/resource restrictions incrementally after basic startup.
- [x] Test missing backend, unsafe SQL/config, leaked credentials, cleanup, isolation and stale proof boundaries.
- [x] Run Guardian suite, syntax checks and strict OpenSpec validation.
- [ ] Run real Actions trial; record actual outcomes and remaining blockers.
- [ ] Owner reviews/merges SIS setup; enable dependency trial separately.

## Evidence and remaining blocker
- Startup control 41028651056 passed startup, real SQL and cleanup without website
  input. Internal control 41031839505 failed; transition control 41031844785
  passed isolation, quotas, blocked egress, SQL and cleanup.
- Full real-service run 41038473256 passed install/lint/types/unit/build/integration,
  schema/RLS, password Auth, public-signup denial, Storage and browser MFA.
  Broader browser coverage: 307 passed, one reduced-motion Will Writing keyboard
  video failure, 88 skipped/unexecuted after fail-fast. The baseline stays blocked.
- A diagnostic-only rerun retains structured assertion locations and fixed matcher
  labels; it does not relax the browser test or any publishing gate.
- Local regression: 420 passed, two Windows skips, including the final diagnostic
  addition; focused diagnostic suite: 10 passed. Strict OpenSpec validation passed.
- Assets are in SIS PR #4, including 34 Linux references captured from approved
  main and a contact-test panel-opening precondition correction. Owner review and
  merge remain outstanding; no production changes or merges were performed.
- Paired dependency-upgrade proof is still pending. Guardian Actions needs a
  scoped SIS read token before that trial; publishing needs separate activation.
