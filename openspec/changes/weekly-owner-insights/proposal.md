# Weekly owner insights

## Why

The owner authorized finishing Telegram validation, query-level SEO insights,
manual uncertain-delivery reconciliation and Monday 09:00 Malaysia local
scheduling on 2026-10-22. A transient poll failure caused a live /report request
to receive no response until the listener restarted.

## What Changes

- Collect bounded query/page samples alongside separate property/page metrics.
- Show evidence-backed keyword/page review actions with confidence and uncertainty.
- Add safe receipt inspection and explicit local received/retry decisions.
- Retry read-only polling with bounded backoff and supervise the local listener.
- Run a weekly read-only audit, mobile/desktop samples, 14-day SEO comparison and
  private-owner Telegram delivery, with durable weekly run suppression.

## Capabilities

### New Capabilities
- `weekly-owner-insights`: query samples, delivery reconciliation and explicitly
  enabled local collection/delivery scheduling.

## Impact

Python Search Console collector, period review, Telegram state/CLI/service,
new weekly runner and Windows Task Scheduler scripts. No new dependencies,
production writes, public port, customer submissions or Telegram write commands.
