#!/bin/bash
# Give the smoke test its own disabled, credential-free environment.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Administrator privileges required'; exit 1; }
mode=${1:---verify-only}
[[ "$mode" = --verify-only || "$mode" = --resume ]]
install -d -m 0755 /etc/systemd/system/guardian-smoke.service.d
cat > /etc/systemd/system/guardian-smoke.service.d/50-no-credentials.conf <<'EOF'
[Service]
EnvironmentFile=
Environment=AGENT_ENABLED=false GUARDIAN_TELEGRAM_ENABLED=false
UnsetEnvironment=ANTHROPIC_API_KEY GUARDIAN_GITHUB_READ_TOKEN GUARDIAN_GITHUB_WRITE_TOKEN GUARDIAN_GSC_ACCESS_TOKEN GUARDIAN_GSC_CLIENT_ID GUARDIAN_GSC_CLIENT_SECRET GUARDIAN_GSC_REFRESH_TOKEN GUARDIAN_PAGESPEED_API_KEY GUARDIAN_TELEGRAM_BOT_TOKEN GUARDIAN_TELEGRAM_CHAT_ID
EOF
systemctl daemon-reload
systemctl restart guardian-smoke.service
test "$(systemctl show guardian-smoke.service -p ExecMainStartTimestampMonotonic --value)" -gt 0
test "$(systemctl show guardian-smoke.service -p Result --value)" = success
test "$(systemctl show guardian-smoke.service -p ExecMainStatus --value)" = 0
if [[ "$mode" = --resume ]]; then
    test ! -e /var/lib/guardian/work/data/STOP
    state=$(systemctl show guardian-weekly.service -p ActiveState --value)
    [[ "$state" = inactive || "$state" = failed ]]
    python3 - <<'PY'
import sqlite3,time
from contextlib import closing
with closing(sqlite3.connect('file:/var/lib/guardian/work/data/telegram.sqlite3?mode=ro',uri=True)) as db:
    expiry=db.execute('SELECT max(expires_at) FROM telegram_leases').fetchone()[0] or 0
if expiry > time.time():
    raise RuntimeError('Previous polling lease still active; wait two minutes and retry')
PY
    systemctl reset-failed guardian-listener.service
    systemctl start guardian-listener.service guardian-weekly.timer
    sleep 8
    systemctl is-active --quiet guardian-listener.service
    systemctl is-active --quiet guardian-weekly.timer
    systemctl is-active --quiet sisweb.service
    printf 'Smoke passed; Guardian listener/timer and SIS are active. Test /help and /status.\n'
else
    printf 'Credential-free sandbox smoke passed. No listener/timer started.\n'
fi
