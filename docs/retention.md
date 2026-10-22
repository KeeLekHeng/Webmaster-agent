# Retention and safe cleanup

[Technical guide](TECHNICAL_GUIDE.md#storage-and-retention) ·
[Security prerequisites](TECHNICAL_GUIDE.md#security-and-decision-rights) ·
[VPS operations](vps.md)

Guardian has a manual preview/apply retention command. No cleanup timer is enabled.
Run it against the active Guardian work directory, not the old Windows copy.
Inside the VPS sandbox that directory is `/work`; on the host its mounted storage
is `/var/lib/guardian/work`. The configured environment and filesystem permissions
still apply. Do not run the Windows copy's listener or scheduler.

## Policy

- Eligible full report files and audit snapshots expire after 90 days, using
  report timestamps rather than file modification time.
- Old lab samples expire after 90 days, preserving the latest sample per site,
  URL and device/profile, plus evidence referenced by retained reports.
- Before removing report/sample detail, retain compact numeric observations in
  `data/retention.sqlite3`. Keep the current calendar month and previous 12 months.
  Observations are grouped by month for storage, not summed: overlapping 14-day
  Search Console windows cannot establish monthly totals.
- Keep latest audit/review reports, latest live database baselines, partial/failed
  reports, current issue evidence, alert references, retained replay sources,
  proposal sources and incomplete weekly-job references.
- Unresolved Telegram deliveries block applying cleanup because their hashed
  delivery keys cannot safely identify every affected report.
- Pairing, offsets, receipts, weekly claims, approval databases and proposal
  artifacts are never purged. Deleted snapshot IDs remain as compact tombstones
  so replaying an old run cannot recreate its history entry.
- Unknown files are preserved. Symlink/junction paths, malformed records and
  unknown database schemas fail closed. No arbitrary directory deletion occurs.

## Preview and apply

Preview does not write files, create databases, collect data or contact APIs:

```text
guardian retention --root PATH_TO_GUARDIAN_WORK
```

The JSON shows protected run IDs, eligible files/bytes, blocking conditions and
a fingerprint binding the day, file contents and logical database state.
No query phrases, source URLs or credentials are included in this preview.

For apply, stop the listener, timer and any running collection first, then set the
Guardian STOP marker. Wait for active leases to end. Review a **fresh** preview
and supply its fingerprint:

```text
guardian retention --root PATH_TO_GUARDIAN_WORK --apply PREVIEW_FINGERPRINT
```

Apply requires STOP, locks existing operational databases and recomputes the plan.
Changed files/state or unresolved jobs/deliveries invalidate it. It commits numeric
preservation before deleting detail and records counts/time/fingerprint in
`cleanup_receipts`. An interrupted cleanup can leave partial progress; preserve
state, inspect and generate a new preview. It is not an atomic filesystem rollback.
Restart only the intended host after reviewing the outcome and clearing STOP.

## Limits and recovery

SQLite deletion does not necessarily shrink the database file; no automatic
VACUUM is performed. Temporary backups need separate retention. Cleanup does not
erase attachments already downloaded to Telegram or other devices.

Routine VPS journals already use 30-day retention with size caps. This command
does not delete arbitrary application logs. Approval/proposal evidence is retained
indefinitely for now, exceeding the suggested minimum 12 months. Protected records
can therefore exceed 90 days; retention is not a guarantee of fixed disk usage.

The migration helper includes `retention.sqlite3` when present, so numeric history
and cleanup receipts move with the agent. History tombstones travel within
`guardian.sqlite3`. History schema version 2 rejects older Guardian code that does
not understand retention tombstones. Do not roll back to that code against a
version-2 database. Always transfer current state after stopping the old host.
