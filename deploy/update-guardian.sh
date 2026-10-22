#!/bin/bash
# Owner-run, offline Guardian-only update; never applies retention or touches SIS.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Administrator privileges required'; exit 1; }
cd "$(dirname "$0")"
expected=${1:?Supply the reviewed wheel SHA256}
[[ "$expected" =~ ^[a-f0-9]{64}$ ]]
wheel=website_guardian-0.1.0-py3-none-any.whl
printf '%s  %s\n' "$expected" "$wheel" | sha256sum --check -
test ! -L "$wheel"
test -f /opt/guardian/cutover-receipt.json
test ! -e /var/lib/guardian/work/data/STOP
systemctl is-active --quiet sisweb.service
systemctl is-active --quiet guardian-listener.service
systemctl is-active --quiet guardian-weekly.timer
weekly_state=$(systemctl show guardian-weekly.service -p ActiveState --value)
[[ "$weekly_state" = inactive || "$weekly_state" = failed ]] || { echo 'Weekly work is running; try after completion'; exit 1; }
# Copy only the verified wheel into a root-owned location before service changes.
backup=$(mktemp -d /opt/guardian/update-XXXXXXXX)
chmod 0700 "$backup"
install -m 0600 "$wheel" "$backup/$wheel"
printf '%s  %s\n' "$expected" "$backup/$wheel" | sha256sum --check -
systemctl stop guardian-weekly.timer
weekly_state=$(systemctl show guardian-weekly.service -p ActiveState --value)
[[ "$weekly_state" = inactive || "$weekly_state" = failed ]] || { echo 'Weekly work started; timer stays stopped, inspect before retry'; exit 1; }
systemctl stop guardian-listener.service
trap 'echo "Update interrupted. Preserve state; inspect stopped Guardian units. Backup: $backup"' ERR
# SIGTERM can leave the durable polling lease until expiry. Never erase it or
# restart repeatedly into systemd's start limit; wait before starting the new bot.
python3 - <<'PY'
import pathlib, sqlite3, time
from contextlib import closing
path = pathlib.Path('/var/lib/guardian/work/data/telegram.sqlite3')
deadline = time.monotonic() + 130
if path.exists():
    while True:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
            expiry = db.execute('SELECT max(expires_at) FROM telegram_leases').fetchone()[0] or 0
        if expiry <= time.time():
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Polling lease did not expire; preserve state and inspect')
        print('Waiting for the previous polling lease to expire...', flush=True)
        time.sleep(min(10, expiry-time.time()))
PY
site=/opt/guardian/app/.venv/lib/python3.12/site-packages
test -d "$site/guardian"
cp -a "$site/guardian" "$backup/guardian"
cp -a "$site/website_guardian-0.1.0.dist-info" "$backup/website_guardian-0.1.0.dist-info"
# Back up the history store before newer code can upgrade its schema.
python3 - "$backup" <<'PY'
import pathlib, sqlite3, sys
from contextlib import closing
source = pathlib.Path('/var/lib/guardian/work/data/guardian.sqlite3')
if source.exists():
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(str(pathlib.Path(sys.argv[1])/'guardian.sqlite3'))) as dst:
            src.backup(dst)
PY
systemd-run --wait --pipe --collect --unit=guardian-code-update \
    -p PrivateNetwork=yes -p NoNewPrivileges=yes -p MemoryMax=192M \
    -p MemorySwapMax=0 -p CPUQuota=15% -p Nice=10 -p OOMScoreAdjust=1000 \
    /opt/guardian/app/.venv/bin/python -m pip install --no-index --no-deps \
    --force-reinstall "$backup/$wheel"
# Reuse the installed isolation and preserved-execution proof.
systemctl restart guardian-smoke.service
test "$(systemctl show guardian-smoke.service -p ExecMainStartTimestampMonotonic --value)" -gt 0
test "$(systemctl show guardian-smoke.service -p Result --value)" = success
systemctl start guardian-listener.service
systemctl start guardian-weekly.timer
sleep 5
systemctl is-active --quiet guardian-listener.service
systemctl is-active --quiet guardian-weekly.timer
systemctl is-active --quiet sisweb.service
printf 'Guardian updated; no retention applied. Rollback material: %s\n' "$backup"
printf 'Test /help and /status in Telegram. Do not restore the old database over newer state.\n'
