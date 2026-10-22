#!/bin/bash
# Resume verification only. Does not reinstall or enable background operation.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Administrator privileges required'; exit 1; }
test -x /opt/guardian/app/.venv/bin/python
test -f /opt/guardian/app/deploy/smoke.py
systemctl is-active --quiet var-lib-guardian-work.mount
systemctl is-active --quiet sisweb.service
for unit in guardian-listener.service guardian-weekly.timer; do
    if systemctl is-active --quiet "$unit"; then
        echo 'Background Guardian operation is already active; inspect before setup verification'
        exit 1
    fi
done
# verify checks executable paths without constructing BindReadOnlyPaths mounts.
# Check directives against the installed host interpreter, then test the real
# unchanged RootDirectory/bind-mount configuration by actually starting smoke.
verify_dir=$(mktemp -d /run/guardian-verify.XXXXXX)
cleanup() {
    rm -f -- "$verify_dir"/*.service "$verify_dir"/*.timer "$verify_dir"/*.mount "$verify_dir"/*.slice
    rmdir -- "$verify_dir"
}
trap cleanup EXIT
for name in guardian-listener.service guardian-weekly.service guardian-smoke.service; do
    sed -e '/^RootDirectory=/d' \
        -e 's|^ExecStart=/app/|ExecStart=/opt/guardian/app/|' \
        -e 's| /app/deploy/| /opt/guardian/app/deploy/|' \
        -e 's|^WorkingDirectory=/work$|WorkingDirectory=/var/lib/guardian/work|' \
        "/etc/systemd/system/$name" > "$verify_dir/$name"
done
for name in guardian.slice guardian-weekly.timer var-lib-guardian-work.mount; do
    cp "/etc/systemd/system/$name" "$verify_dir/$name"
done
systemd-analyze --man=no verify "$verify_dir"/*
if ! systemctl restart guardian-smoke.service; then
    journalctl --namespace=guardian -u guardian-smoke.service -n 20 --no-pager
    exit 1
fi
started=$(systemctl show guardian-smoke.service -p ExecMainStartTimestampMonotonic --value)
test "${started:-0}" -gt 0
test "$(systemctl show guardian-smoke.service -p ExecMainStatus --value)" = 0
test "$(systemctl show guardian-smoke.service -p Result --value)" = success
journalctl --namespace=guardian -u guardian-smoke.service -n 15 --no-pager
systemctl show guardian.slice -p MemoryPeak -p MemoryCurrent -p MemoryMax -p CPUQuotaPerSecUSec
systemctl is-active --quiet sisweb.service
printf '\nGuardian sandbox installed and smoke-tested. Listener/timer remain disabled. No secrets or local state migrated.\n'
