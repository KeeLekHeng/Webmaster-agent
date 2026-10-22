#!/bin/bash
# Apply only Guardian's network sandbox correction, then resume smoke verification.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Administrator privileges required'; exit 1; }
cd "$(dirname "$0")"
sha256sum --check --status SHA256SUMS
for unit in guardian-listener.service guardian-weekly.timer; do
    if systemctl is-active --quiet "$unit"; then
        echo 'Stop active Guardian operation before repairing setup'
        exit 1
    fi
done
systemctl is-active --quiet sisweb.service
test -f /opt/guardian/app/deploy/smoke.py
for name in guardian-listener guardian-weekly guardian-smoke; do
    target="/etc/systemd/system/$name.service.d/20-network-isolation.conf"
    if test -e "$target" && ! cmp -s network-isolation.conf "$target"; then
        echo 'Existing Guardian override differs; inspect before overwrite'
        exit 1
    fi
done
for name in guardian-listener guardian-weekly guardian-smoke; do
    install -d -m 0755 "/etc/systemd/system/$name.service.d"
    install -m 0644 network-isolation.conf "/etc/systemd/system/$name.service.d/20-network-isolation.conf"
done
printf '[Service]\nRemainAfterExit=yes\n' > /etc/systemd/system/guardian-smoke.service.d/40-verification-state.conf
install -o root -g root -m 0644 smoke.py /opt/guardian/app/deploy/smoke.py
install -o root -g root -m 0644 verify-install.sh /opt/guardian/app/deploy/verify-install.sh
systemctl daemon-reload
systemctl reset-failed guardian-smoke.service || true
bash /opt/guardian/app/deploy/verify-install.sh
