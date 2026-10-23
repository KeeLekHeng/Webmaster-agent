## Implementation
- [x] Expand AI schema, evidence context, filtering and readable reports.
- [x] Implement conservative version/diff/security policy and tests.
- [x] Implement paired Docker verification and host-generated artifact binding.
- [x] Implement isolated publisher and disabled-by-default Actions workflow.
- [x] Document credentials, coverage limits, activation and rollback.
- [x] Extend opt-in compatibility policy with bounded AST recipes and independent publisher replay.
- [x] Prepare independent SIS PR CI assets in an isolated setup worktree.
## Acceptance
- [x] Run meaningful mocked boundary tests and full Guardian suite (338 passed; two Windows symlink skips).
- [x] Validate OpenSpec/workflow syntax; local Docker engine unavailable, so no real container success claimed.
- [x] Extension validation: 358 Guardian tests passed, two Windows symlink skips; 58 maintenance tests include actual AST replay and tamper rejection.
- [ ] Perform real GitHub Actions baseline/candidate trial after operator setup.
- [ ] Verify a real PR and owner notification before claiming operational success.
- [ ] Owner review/merge SIS CI bootstrap and run its first real verification.
