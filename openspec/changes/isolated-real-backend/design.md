# Design

## Services and isolation
Before another full trial, establish a minimal startup control with trusted
configuration/images only, standard bridge networking and loopback bindings.
No website checkout/input, migrations or application code enter this control.
Its separate artifact is diagnostic evidence only, rejected by publishing policy.
After it passes, evaluate internal networking/resource restrictions separately;
the candidate verifier's isolation requirements are not relaxed by this control.

Control 41028651056 passed. Trial 41031839505 reproduces the failure using internal
networking from startup with no website input. Trial 41031844785 passed trusted
startup followed by isolation, the existing service audits/quotas, blocked egress,
real SQL and cleanup. Use this proven sequence in the candidate verifier.

Use pinned Supabase CLI 2.119.0 (release archive SHA256 verified) with a minimal
trusted configuration, never candidate config/hooks. CLI-managed service images
are version-pinned by that CLI; record their resolved image IDs. Bootstrap trusted
services/configuration on a loopback-bound bridge so the CLI can complete its own
database setup. Read disposable API keys into memory, then move every service to a
fresh internal network, preserving aliases and removing bootstrap attachments.
Discover the gateway address from that owned network for host-side setup APIs;
never depend on published host ports after isolation. Published backend ports bind
loopback only and are audited before any candidate SQL executes. Unneeded services and
external providers are disabled. No Docker socket enters application containers.

Start the empty trusted stack before introducing candidate input. Audit container
mounts/privilege/ports/network membership and apply resource quotas, then execute
bounded regular migration SQL via the disposable database only. Website SQL is
untrusted executable input; psql meta-commands are rejected. Candidate source is
never executed on the runner host. No production config/env files are imported.

The application shares the gateway's network namespace, accessing its test API
through loopback. Tests cannot route to production; registry install/audit remains
a separate script-disabled phase. Use independent stacks for baseline, candidate
and repaired candidate. Resource/capacity failure blocks rather than weakening
checks. The shared VPS is never used for this work.

## Data and real checks
Seed normal public tables using literal fixture content parsed as data in a
trusted parser inside Docker, plus synthetic career/account records. Keep
E2E_TEST_DATA=0 so normal application queries execute. Preserve RLS and MFA.
Check real PostgREST anonymous published reads/draft denial, real Auth password
tokens, real Storage and browser password/MFA/management access. Application
signing keys and accounts belong only to this test stack.

Existing unit/integration mocks remain valuable for deterministic expiry/provider
failure cases. Existing browser email interception prevents real delivery.
Password-only legacy admin UI cases are not silently enabled by disabling MFA;
report that coverage limit. Hosted OAuth/provider deliverability remains outside
the local test proof.

SIS documents `REQUIRE_ADMIN_MFA=false` for its current UAT period. A separate
trusted browser smoke process tests that configuration with the same disposable
backend and fresh browser context. It must reject anonymous access, sign in via
the real password form, create/read/edit/delete a unique synthetic draft through
the application, check persistence independently through local PostgREST, confirm
anonymous draft denial and perform actual sign-out followed by protected-access
rejection. Server restarts separate the MFA-on and UAT configurations. No session
storage, production credentials, route interception or success stubs are used.
Both profile proofs are mandatory; extensive legacy admin suites remain skipped
and disclosed. This UAT profile does not change production or the broad suite's
MFA-on policy. These are trusted CI setup changes, not automatic repair authority.

## Evidence and cleanup
Store only versions/image identities, migration hashes, stage statuses and bounded
browser summaries. Never store test passwords, API keys, MFA secrets, raw logs or
page contents. Publishing requires versioned backend evidence for both copies.
Old reports remain readable but cannot satisfy the new publishing policy.

Use finally cleanup and a workflow always-run fallback scoped to labelled
Guardian resources, with no global Docker prune. Cleanup failure blocks proof.
Initial rollout is manual on the reviewed setup branch; owner merge/activation
remains separate. Local Docker is currently unavailable, so real CI trials must
be distinguished from mocked controller tests.
