## 1. Implementation
- [x] 1.1 Add bounded optional query/page collection and safe owner insights.
- [x] 1.2 Keep query text outside model inputs and validate exact evidence bindings.
- [x] 1.3 Add audited local receipt reconciliation and atomic one-attempt retry.
- [x] 1.4 Add durable weekly runner and restricted Windows activation/disable scripts.
- [x] 1.5 Add read-only poll retries and listener supervision.

## 2. Validation and activation
- [x] 2.1 Test privacy/scope, missing rows, partial APIs, retries and duplicate runs.
- [x] 2.2 Collect live Search Console query data with owner-configured credentials.
- [x] 2.3 Restart listener and confirm owner-generated /report delivery.
- [x] 2.4 Validate latest full suite and strict OpenSpec checks.
- [x] 2.5 Activate and inspect owner-authorized local schedule; document limitations.

## Live validation (2026-10-22)

- Search Console query/page collection and Claude review completed; current period
  2026-10-05 through 2026-10-18 versus previous 2026-09-21 through 2026-10-04.
  Property clicks 3 to 10 and impressions 24 to 120. Recommendations low confidence.
- Latest summary/document sent successfully; repeating the same send suppressed.
- Owner confirmed /report delivery and /status from the supervised listener.
- Both fresh mobile and desktop lab samples saved. Initial mobile API 400 left no
  sample and recovered later; no missing result was represented as a measurement.
- Windows tasks inspected: current interactive owner, limited run level, IgnoreNew;
  weekly catch-up enabled, next run 2026-10-26 09:00 Malaysia. Listener running.
- 271 tests passed, one Windows symlink test skipped. Strict change validation passed.
