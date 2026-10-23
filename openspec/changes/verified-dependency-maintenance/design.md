# Design

## Decisions
The controller runs in the Guardian repository's GitHub Actions workflow. The
website is checked out read-only at a pinned commit; its code runs only inside
resource-limited Docker containers. No website builds run on the shared VPS.
Registry resolution is deterministic; Claude explains results and cannot select
versions, execute commands, change policy or declare tests passed.

The network-enabled installation phase runs a fixed package-manager command with
scripts/hooks disabled. Verification uses network-none containers, synthetic
environment values, cached public font assets and no tokens/host sockets. Local
mock authentication/database tests may bind loopback inside the container.

Baseline and candidate use fresh source copies and the same toolchain/fixtures.
Required checks: frozen install, lint, typecheck, unit tests, production build,
integration tests and browser tests. A baseline failure blocks publication.
Candidate publication is only for stable same-major direct updates (0.x keeps
its minor), with no worsened known security advisory inventory. Major/transitive
fixes requiring overrides are reported for human migration review.

Publication runs in a separate job that never executes candidate code. It receives
only two bounded text files and a host-generated manifest; validates their hashes,
dependency-only semantic diff, required stages and unchanged base; then creates a
new branch/commit/PR through bounded GitHub API routes. No force push or merge.
The trusted workflow's own run and artifact are the attestation boundary; imported
local JSON is not proof of a trusted CI execution.

## Boundaries and rollout
Automatic dependency PRs are a new explicit standing authorization; other manual
proposals still require exact expiring approval. Publication defaults off. Separate
repository-scoped read/write credentials live in Actions secrets, not test
containers or the shared VPS. A GitHub App is preferable for longer-term scoping.

Passing synthetic tests establishes tested behavior, not a guarantee of all live
Supabase/email/data/authentication behavior. PRs must state coverage and exclusions.
No claim of a live successful pipeline is made before an actual Actions run.
