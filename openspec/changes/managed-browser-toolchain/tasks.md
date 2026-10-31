- [x] Record failed-trial evidence and owner-approved separation.
- [x] Implement trusted version binding, explicit deferrals and inventory gates.
- [x] Enforce the boundary independently in publishing and human/AI reports.
- [x] Add read-only branch preview and refresh reviewed Node 24 action pins.
- [x] Test deferrals, advisory visibility, drift and publisher/preview rejection.
- [x] Run all local checks and a real publishing-disabled application-upgrade trial.
- [x] Open a reviewable PR with actual evidence and remaining limits.

469 local tests passed, two skipped; strict validation passed. Read-only preview
41203746397 demonstrated explicit Playwright deferral and passed candidate
integration plus both real admin profiles, then correctly blocked on two public
accessibility assertions. It did not verify the 14-update batch. Guardian PR #2
remains draft pending bounded accessibility diagnosis; no gate was removed.
SIS workflow-only PR #5 passed run 41203784493 and is ready for owner review.

- [x] Add bounded public accessibility rule/route and flaky-location diagnostics.
- [x] Confine exact SIS commit selection to manual read-only non-main previews.
- [ ] Rerun the unchanged batch and diagnose the accessibility failures.
