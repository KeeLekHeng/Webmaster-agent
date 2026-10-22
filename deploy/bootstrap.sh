#!/bin/bash
# Explicit administrator setup only. Leaves scheduling/delivery disabled.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Administrator privileges required'; exit 1; }
cd "$(dirname "$0")"
sha256sum --check SHA256SUMS
test "$(uname -m)" = x86_64
python3 -c 'import sys; assert sys.version_info[:2] == (3,12)'
test "$(awk '/MemAvailable:/{print $2}' /proc/meminfo)" -ge 409600 || { echo 'Less than 400 MiB available; stop and reassess'; exit 1; }
test "$(df --output=avail -k /opt | tail -n 1)" -ge 2097152
systemctl is-active --quiet sisweb.service
test ! -e /opt/guardian && test ! -e /var/lib/guardian && test ! -e /etc/guardian || { echo 'Guardian paths already exist; review partial/previous install'; exit 1; }
! getent passwd websiteguardian >/dev/null || { echo 'Guardian identity already exists; inspect before reuse'; exit 1; }
for unit in guardian.slice guardian-listener.service guardian-weekly.service guardian-weekly.timer var-lib-guardian-work.mount; do
    test ! -e "/etc/systemd/system/$unit" || { echo 'Guardian unit already exists'; exit 1; }
done
useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin websiteguardian
install -d -m 0755 /opt/guardian /opt/guardian/app /var/lib/guardian /var/lib/guardian/root
install -d -m 0700 /etc/guardian
cp -a app/. /opt/guardian/app/
cp -a wheelhouse /opt/guardian/wheelhouse
chown -R root:root /opt/guardian
chmod -R go-w /opt/guardian
chown -R websiteguardian:websiteguardian /opt/guardian/app
trap 'chown -R root:root /opt/guardian/app' EXIT
systemd-run --wait --pipe --collect --unit=guardian-install \
    -p User=websiteguardian -p Group=websiteguardian -p PrivateNetwork=yes \
    -p NoNewPrivileges=yes -p MemoryMax=192M -p MemorySwapMax=0 \
    -p CPUQuota=15% -p Nice=10 -p OOMScoreAdjust=1000 \
    /bin/bash /opt/guardian/app/deploy/install-env.sh
chown -R root:root /opt/guardian/app
trap - EXIT
# A bounded state filesystem avoids letting growing reports fill the website disk.
truncate -s 512M /var/lib/guardian/state.img
chmod 0600 /var/lib/guardian/state.img
mkfs.ext4 -q -F -m 0 /var/lib/guardian/state.img
install -d -m 0755 /var/lib/guardian/work
for unit in guardian.slice guardian-listener.service guardian-weekly.service guardian-weekly.timer var-lib-guardian-work.mount; do
    install -m 0644 "/opt/guardian/app/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
install -d -m 0755 /etc/systemd/journald@guardian.conf.d
install -m 0644 /opt/guardian/app/deploy/systemd/journald.conf /etc/systemd/journald@guardian.conf.d/limits.conf
systemctl daemon-reload
systemctl start var-lib-guardian-work.mount
chown websiteguardian:websiteguardian /var/lib/guardian/work
chmod 0700 /var/lib/guardian/work
install -d -o websiteguardian -g websiteguardian -m 0700 /var/lib/guardian/work/data /var/lib/guardian/work/reports
install -o websiteguardian -g websiteguardian -m 0600 /opt/guardian/app/config/weekly.json /var/lib/guardian/work/data/weekly.json
printf 'AGENT_ENABLED=false\nGUARDIAN_TELEGRAM_ENABLED=false\n' > /etc/guardian/guardian.env
chmod 0600 /etc/guardian/guardian.env
root=/var/lib/guardian/root
install -d -m 0755 "$root/usr" "$root/etc/ssl/certs" "$root/app" "$root/work" "$root/tmp" "$root/proc" "$root/dev" "$root/sys" "$root/run"
ln -s usr/lib "$root/lib"
ln -s usr/lib64 "$root/lib64"
ln -s usr/bin "$root/bin"
touch "$root/etc/resolv.conf" "$root/etc/nsswitch.conf" "$root/etc/hosts"
# The smoke unit inherits the exact runtime isolation and shared resource slice.
sed -e 's|ExecStart=.*|ExecStart=/app/.venv/bin/python /app/deploy/smoke.py|' \
    -e '/^\[Service\]$/a RemainAfterExit=yes' \
    /etc/systemd/system/guardian-weekly.service > /etc/systemd/system/guardian-smoke.service
systemctl daemon-reload
bash /opt/guardian/app/deploy/verify-install.sh
