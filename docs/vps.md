# Temporary same-host VPS deployment

[Technical router](TECHNICAL_GUIDE.md) · [Security prerequisites](TECHNICAL_GUIDE.md#security-and-decision-rights)
· [Storage/cutover context](TECHNICAL_GUIDE.md#storage-and-retention)

Status: cutover complete. The owner ran administrator setup and final import.
The receipt at `/opt/guardian/cutover-receipt.json` records completion at
2026-10-22 16:26:24 UTC after successful live readiness checks. A subsequent SSH
check confirmed listener and timer active/enabled, with SIS active. The owner
confirmed `/status` replies from the VPS. Windows tasks remain disabled with STOP set.
Next scheduled run: 26 October 2026, Monday 09:00 Asia/Kuala_Lumpur. Its first
automatic execution and delivery remain to be verified.

Smoke proof at `/opt/guardian/readiness.json` records actual execution on
22 October 2026 at 14:50 UTC. Earlier failure notes below are historical.

## Cleanup and future migration

### Guardian code updates

The retained [update helper](../deploy/update-guardian.sh) installs a reviewed
platform-independent Guardian wheel offline. It refuses active weekly work, pauses
the timer/listener, saves the previous package and consistent history backup in a
private `/opt/guardian/update-*` directory, installs under CPU/memory limits, runs
the sandbox smoke and restarts only Guardian units. Failures require inspection;
do not overwrite newer operational state with a backup. It does not apply retention.
Run it with administrator privileges and the exact reviewed wheel SHA256. The
retention/menu update is staged at `/home/deploy/guardian-update-20261023`; installation
is pending owner execution. Telegram command-menu registration is already live;
the richer `/help` response and retention CLI require the package update.

Update smoke regression: after cutover, the smoke unit inherited the live
`EnvironmentFile` and failed its disabled/no-credentials assertions. The package
installation had completed, but the updater correctly left polling/scheduling
stopped. [repair-smoke.sh](../deploy/repair-smoke.sh) clears the environment-file
list for **smoke only**, explicitly disables activity and unsets credential keys.
It retains the filesystem, resource and seccomp checks. `--verify-only` checks
without starting background work; owner-run `--resume` also verifies no active
polling lease before starting the listener/timer. The updater now calls this
helper. No live environment file or API credential is changed by the repair.

### Files to preserve

Keep `deploy/`, its tests, dependency locks, configuration templates and this guide
as reusable deployment sources. Keep live `/opt/guardian`, `/etc/guardian`,
`/var/lib/guardian`, installed units and receipts. Reports, SQLite state and bot
offsets/receipts are operational data, not disposable installation files.

Disposable transfer material: local `data/vps-*` directories and server
`/home/deploy/guardian-stage-20261022`. Automated deletion was blocked; the owner
subsequently reported completing the supplied manual cleanup commands.
The root-only migration private key/certificate are also one-time transfer material;
administrator cleanup can remove them after verification, without changing API keys.

For another VPS, build from the retained source and locked dependencies, repeat
isolation/readiness checks, then stop the current listener and timer before making
fresh consistent state backups. Generate a new recipient key on the new host and
transfer current state/credentials securely. Do not reuse the old encrypted payload
or restart Windows with stale bot state. Verify the new host before retiring the old.

Owner bootstrap update: the owner installed the account, application, dependencies,
bounded state volume and inactive units. It then stopped at static executable
validation: `/app` is a runtime bind mount not present in the validator's filesystem
view. The original smoke unit had never executed (empty start timestamp), so its
default `Result=success`/exit status was not evidence of a passed test. Actual
runtime isolation and same-host feasibility remain unverified. The earlier success
statement was corrected; listener/timer remain disabled.

## Read-only inspection

Confirmed on the current SIS host:

| Item | Observed |
| --- | --- |
| OS/runtime | Ubuntu 24.04, x86_64, Python 3.12.3, systemd 255, cgroup v2 |
| Capacity | 1 CPU; 961 MiB physical RAM; about 491 MiB available at inspection |
| Swap/disk | 1 GiB swap, about 92 MiB used; about 16 GiB free on 24 GiB root disk |
| SIS | Active; about 211 MiB; deploy identity; MemoryMax 750 MiB |
| Other apps | Caddy about 37 MiB; chillix-api active, about 5 MiB |
| Isolation tools | systemd present; no Docker found; Python venv ensurepip package absent |
| Privileges | deploy has sudo membership but noninteractive sudo requires a password |

SIS cgroup counters reported zero OOM/OOM-kill events at inspection. That is scoped
to the current service cgroup, not proof of an incident-free host history.

These are a point-in-time sample, not peak-load evidence. A small trial may fit;
safe same-host operation is not proven until isolation, memory and live behavior
are tested. Existing website build/load spikes remain a shared-host risk. Do not
change SIS/Caddy limits or install a container daemon to make Guardian fit.

## Prepared layout and limits

- Dedicated non-login `websiteguardian` identity, no sudo or website group access.
- Root-owned application/virtual environment: `/opt/guardian/app`.
- Root-only environment file: `/etc/guardian/guardian.env`; no website or GitHub
  write credentials are copied. Initial flags disable agent activity/delivery.
- Minimal service root: `/var/lib/guardian/root`. Only runtime OS libraries,
  certificate/DNS configuration, Guardian application and its own work storage are
  made available. `/opt/sisweb`, deploy home and production secrets are absent.
- Separate 512 MiB ext4 loop image at `/var/lib/guardian/state.img`, mounted as
  `/var/lib/guardian/work` with nodev/nosuid/noexec; reports cannot fill the host disk.
- Combined listener/weekly `guardian.slice`: 15% of one CPU, 192 MiB maximum,
  160 MiB memory pressure threshold, no swap, 48 tasks and low CPU/I/O priority.
- Guardian is preferentially OOM-killed rather than increasing host budgets to
  accommodate it. This reduces impact, not a guarantee against shared-host failure.
- No public listening socket, reverse-proxy route, DNS/firewall change or production
  mount. Seccomp denies bind/listen, including ephemeral port 0. Smoke checks
  IPv4/IPv6, TCP/UDP, fixed/ephemeral binds and implicit listening.
- Dedicated journal namespace: 16 MiB persistent/8 MiB runtime limits, 30-day retention.

Service restrictions use systemd root/filesystem isolation and cgroup controls:
[execution controls](https://www.freedesktop.org/software/systemd/man/systemd.exec.html),
[resource controls](https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html).
The bootstrap validates directives with the target's systemd, not just local assumptions.

## Administrator setup gate

The prepared offline bundle contains application source, locked Linux Python 3.12
wheels, systemd units and SHA256SUMS. It contains no `.env`, reports or databases.
Do not run it against a different OS/architecture or install over existing Guardian
paths without review. Its code is [bootstrap.sh](../deploy/bootstrap.sh).

The explicit administrator command verifies hashes and invokes bootstrap. Bootstrap:

```bash
ssh deploy@104.248.144.176
cd /home/deploy/guardian-stage-20261022
sudo bash bootstrap.sh
```

Enter the sudo password only in the SSH terminal, never in chat. The staged bundle
passed hash, shell syntax and target-systemd directive checks; directive validation
used a harmless host executable because the real sandbox does not exist yet.
The real filesystem/resource/network isolation is tested only by bootstrap smoke.
Local validation: 272 tests passed, one Windows symlink privilege skip.

For this already-installed host, do **not** rerun bootstrap. Resume with:

```bash
cd /home/deploy/guardian-stage-20261022
sudo bash verify-install.sh
```

The prepared verifier checks directive copies against the real host interpreter,
then starts the unchanged sandbox smoke unit. A pass requires an actual nonzero
execution timestamp, zero exit status and successful result; merely loaded units
do not count. The verifier enables no listener/timer and migrates no credentials.

Socket repair: the first actual smoke run failed at ephemeral binding. The BPF
`SocketBindDeny=any` rule covers positive ports, not port 0; this host's systemd
also reports `-BPF_FRAMEWORK`. Do not rely on it as sole enforcement. The host has
`+SECCOMP`; the correction denies bind/listen with EPERM and native architecture.
Outbound connect/DNS remains permitted but must be checked by the actual smoke run.

Prepared one-time resume, without reinstalling dependencies or enabling services:

```bash
cd /home/deploy/guardian-stage-20261022/isolation-fix
sudo bash repair-isolation.sh
```

The repair verifies its payload, adds Guardian-only service drop-ins, updates the
smoke/verifier, and runs the actual sandbox with stronger socket checks. It changes
no SIS/Caddy configuration, firewall, credential or existing runtime data. A pass
must be observed before migrating secrets or enabling background operation.

1. Rechecks free memory/disk, SIS active state and absence of conflicting paths/users.
2. Creates only Guardian's identity/directories; installs offline inside a capped,
   network-disabled temporary unit, with no apt upgrade or website build/restart.
3. Creates its bounded state filesystem and minimal runtime root.
4. Installs inactive listener/weekly/timer units and namespaced logging configuration.
5. Runs a disabled/no-credentials smoke unit under the actual runtime sandbox,
   testing imports, absent production paths, blocked socket bind, DNS and SQLite.
6. Reports resource usage and confirms SIS remains active. It does not enable
   the listener, timer, live scans, model requests or external delivery.

Initial budgets are candidates. If installation/smoke fails under them, stop and
inspect; do not raise caps until website headroom is assessed. A partial install
is intentionally not overwritten automatically. Review safe Guardian-only recovery
paths; never remove website directories, users, mounts or services.

## Cutover after successful setup

The prepared finalizer is [finalize-cutover.sh](../deploy/finalize-cutover.sh).
The scoped [migration helper](../deploy/migration.py) exports only Google, Claude,
PageSpeed and Telegram configuration, consistent SQLite backups, eligible reports,
samples and the weekly schedule. It excludes GitHub credentials, approval records,
publishing policy and website credentials. Local plaintext transfer archives are
removed after CMS AES-256-GCM/RSA-OAEP encryption for the root-only server key.
Windows/OpenSSL 3.2 encryption and Ubuntu/OpenSSL 3.0 decryption were tested with
synthetic data before the real transfer. Only ciphertext is staged under deploy.

The finalizer checks its files/payload digest, decrypts under `/etc/guardian`,
installs private configuration and Guardian-owned state, and checks website HTTP,
Google renewal/property data, Claude report analysis and bot identity/pairing under
the actual sandbox before enabling anything. No Telegram report is sent by that
preflight. Successful cutover enables the listener and Monday timer and writes
`/opt/guardian/cutover-receipt.json`. Identical partial copies can resume; different
server database bytes require manual reconciliation. Preserve state on failure.

1. Verify smoke output, namespace paths, limits, socket denial and memory use.
2. Perform a bounded manual read-only check before enabling background operation.
3. Stop Windows Guardian tasks/listener; wait for in-flight work and lease expiry.
4. Make consistent SQLite backups and copy selected reports/samples and durable
   history, Telegram pairing/offsets/receipts, and weekly claim state if present.
   Never run two hosts against separate copies of one bot's polling state.
5. Provision only required Guardian secrets privately into the root-only environment
   file. Exclude GitHub write tokens, approvals/publishing configuration and website
   credentials. Provisioning secrets is separate from this bootstrap.
6. Verify Google refresh/property access, latest saved /status and /report, uncertain
   receipts, weekly claims and existing baseline continuity.
7. Explicitly enable the listener and Monday 09:00 Asia/Kuala_Lumpur timer. Persistent
   catch-up uses the existing weekly claim guard; inspect before triggering it.
8. Monitor Guardian/SIS memory and host pressure. Keep local tasks disabled.

On failure, stop Guardian units/timer and preserve state before returning operation
to Windows. Restore current durable state, not a stale independent database copy.
No website deployment rollback is needed. Move the same isolated app/state to a
dedicated host later, repeating the single-poller and scheduler cutover checks.

Read [systemd timer behavior](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)
and the [ranked backlog](../stackrank.md) before expanding deployment scope.
