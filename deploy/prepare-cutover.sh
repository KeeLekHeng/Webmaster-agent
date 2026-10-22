#!/bin/bash
# Administrator preparation: durable readiness proof and root-only decryption key.
set -euo pipefail
test "$(id -u)" -eq 0
cd "$(dirname "$0")"
sha256sum --check --status SHA256SUMS
for unit in guardian-listener.service guardian-weekly.timer; do
    if systemctl is-active --quiet "$unit"; then
        echo 'Guardian already active; inspect before migration'
        exit 1
    fi
done
install -d -m 0755 /etc/systemd/system/guardian-smoke.service.d
printf '[Service]\nRemainAfterExit=yes\n' > /etc/systemd/system/guardian-smoke.service.d/40-verification-state.conf
install -o root -g root -m 0644 verify-install.sh /opt/guardian/app/deploy/verify-install.sh
systemctl daemon-reload
bash /opt/guardian/app/deploy/verify-install.sh
if ! test -e /etc/guardian/migration-key.pem && ! test -e /opt/guardian/migration-cert.pem; then
    (umask 077; openssl req -x509 -newkey rsa:3072 -nodes -days 2 \
        -subj /CN=WebsiteGuardianMigration -keyout /etc/guardian/migration-key.pem \
        -out /opt/guardian/migration-cert.pem)
fi
test -f /etc/guardian/migration-key.pem
openssl x509 -checkend 3600 -noout -in /opt/guardian/migration-cert.pem
chmod 0600 /etc/guardian/migration-key.pem
chmod 0644 /opt/guardian/migration-cert.pem
python3 - <<'PY'
import json,subprocess,datetime,pathlib
def prop(name):
    return subprocess.check_output(['systemctl','show','guardian-smoke.service','-p',name,'--value'],text=True).strip()
assert int(prop('ExecMainStartTimestampMonotonic'))>0
assert prop('Result')=='success' and prop('ExecMainStatus')=='0'
pathlib.Path('/opt/guardian/readiness.json').write_text(json.dumps({
    'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'smoke_started':prop('ExecMainStartTimestamp'),'result':'success',
    'listener_enabled':False,'timer_enabled':False}),encoding='utf-8')
PY
chmod 0644 /opt/guardian/readiness.json
printf '\nReadiness proof and public migration certificate prepared. Private key stays root-only. No credentials/state migrated or background operation enabled.\n'
