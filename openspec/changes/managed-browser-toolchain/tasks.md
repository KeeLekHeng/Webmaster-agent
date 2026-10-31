- [x] Record failed-trial evidence and owner-approved separation.
- [x] Implement trusted version binding, explicit deferrals and inventory gates.
- [x] Enforce the boundary independently in publishing and human/AI reports.
- [x] Add read-only branch preview and refresh reviewed Node 24 action pins.
- [x] Test deferrals, advisory visibility, drift and publisher/preview rejection.
- [x] Run all local checks and a real publishing-disabled application-upgrade trial.
- [x] Open a reviewable PR with actual evidence and remaining limits.

480 local tests passed, two skipped; strict validation and documentation checks
passed. Initial previews correctly blocked accessibility defects. The independent
SIS source repair is separate from the automated mechanical-repair policy.

- [x] Add bounded public accessibility rule/route and flaky-location diagnostics.
- [x] Confine exact SIS commit selection to manual read-only non-main previews.
- [x] Rerun the unchanged batch and diagnose the accessibility failures.
- [x] Verify the independent SIS brand/video repairs with full PR CI and the paired batch.

SIS run 41207971207 passed on source `66c1f70` (merge checkout `21913c4`):
308 browser passes, zero failures/flakes, 88 disclosed skips. Guardian paired
preview 41207985799 passed all stages, both admin profiles, isolation and cleanup
for the same 14 upgrades, with Playwright explicitly deferred and artifact hashes
validated. Baseline had 307 direct passes plus one retry; candidate 306 plus two
retries; both had 88 skips and zero unexpected failures. Existing zod/high and
minimatch/moderate advisories remain; responsive-layout flakes need follow-up.
Guardian #2 and SIS #6 are ready for owner review, not merged or deployed. SIS #5
remains owner-deferred. A fresh merged-main trial is still required before enabling
dependency publication. See the canonical setup guide for review/merge order.
