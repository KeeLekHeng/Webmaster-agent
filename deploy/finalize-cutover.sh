#!/bin/bash
# Explicit owner cutover: import encrypted scoped state, verify, then activate.
set -euo pipefail
test "$(id -u)" -eq 0
cd "$(dirname "$0")"
sha256sum --check --status SHA256SUMS
test "$#" -eq 1 && [[ "$1" =~ ^[a-f0-9]{64}$ ]]
printf '%s  payload.cms\n' "$1" | sha256sum --check --status -
test ! -e /opt/guardian/cutover-receipt.json || { echo 'Cutover already recorded; inspect before repeat'; exit 1; }
systemctl is-active --quiet sisweb.service
test "$(systemctl show guardian-smoke.service -p Result --value)" = success
test "$(systemctl show guardian-smoke.service -p ExecMainStartTimestampMonotonic --value)" -gt 0
for unit in guardian-listener.service guardian-weekly.timer; do
    if systemctl is-active --quiet "$unit"; then echo 'Guardian already active; stop and inspect'; exit 1; fi
done
private=$(mktemp -d /etc/guardian/import.XXXXXX)
trap 'rm -f -- "$private/payload.zip"; rmdir -- "$private"' EXIT
openssl cms -decrypt -binary -inform DER -in payload.cms \
    -recip /opt/guardian/migration-cert.pem -inkey /etc/guardian/migration-key.pem -out "$private/payload.zip"
if test -e /etc/guardian/imported-payload.sha256; then
    test "$(cat /etc/guardian/imported-payload.sha256)" = "$1" || { echo 'Different payload was already imported; inspect before replacing state'; exit 1; }
else
    python3 migration.py install "$private/payload.zip"
    (umask 077; printf '%s\n' "$1" > /etc/guardian/imported-payload.sha256)
fi
install -o root -g root -m 0644 live-readiness.py /opt/guardian/app/deploy/live-readiness.py
sed -e 's|ExecStart=.*|ExecStart=/app/.venv/bin/python /app/deploy/live-readiness.py|' \
    -e '/^\[Service\]$/a RemainAfterExit=yes' \
    /etc/systemd/system/guardian-weekly.service > /etc/systemd/system/guardian-readiness.service
install -d -m 0755 /etc/systemd/system/guardian-readiness.service.d
install -m 0644 /etc/systemd/system/guardian-weekly.service.d/20-network-isolation.conf \
    /etc/systemd/system/guardian-readiness.service.d/20-network-isolation.conf
systemctl daemon-reload
if ! systemctl restart guardian-readiness.service; then
    journalctl --namespace=guardian -u guardian-readiness.service -n 20 --no-pager
    echo 'Preflight failed. VPS listener/timer remain disabled; preserve state and inspect before retry.'
    exit 1
fi
test "$(systemctl show guardian-readiness.service -p ExecMainStartTimestampMonotonic --value)" -gt 0
test "$(systemctl show guardian-readiness.service -p Result --value)" = success
journalctl --namespace=guardian -u guardian-readiness.service -n 12 --no-pager
systemctl enable --now guardian-listener.service guardian-weekly.timer
sleep 12
systemctl is-active --quiet guardian-listener.service
systemctl is-active --quiet guardian-weekly.timer
systemctl is-active --quiet sisweb.service
python3 - <<'PY'
import json,datetime,pathlib,subprocess
def prop(unit,name):
    return subprocess.check_output(['systemctl','show',unit,'-p',name,'--value'],text=True).strip()
receipt={'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'live_readiness_started':prop('guardian-readiness.service','ExecMainStartTimestamp'),
         'readiness_result':prop('guardian-readiness.service','Result'),
         'listener':prop('guardian-listener.service','ActiveState'),
         'timer':prop('guardian-weekly.timer','ActiveState'),'website':prop('sisweb.service','ActiveState')}
pathlib.Path('/opt/guardian/cutover-receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
PY
chmod 0644 /opt/guardian/cutover-receipt.json
systemctl list-timers guardian-weekly.timer --no-pager
systemctl show guardian.slice -p MemoryCurrent -p MemoryPeak -p MemoryMax
printf '\nGuardian VPS cutover complete. Keep Windows tasks disabled; test /status and /report in Telegram.\n'
