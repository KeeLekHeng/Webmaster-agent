# Design

The pinned `FROM mcr.microsoft.com/playwright:vVERSION-FLAVOR` line is the reviewed
version source. Missing, ambiguous or unpinned configuration fails closed. Direct
`@playwright/test`, `playwright` and `playwright-core` declarations belong to that
toolchain. Their installed versions must match the image. Their declarations are
preserved during automatic selection, including when another update is urgent.

Registry selection still evaluates those packages. Available updates or existing
advisories produce bounded `deferred_updates` with a fixed review reason. Advisory
evidence remains visible. Deferred versions never receive an upgrade-verified
claim. An otherwise empty batch may complete its baseline without creating a PR.

Candidate inventory must retain the reviewed resolved versions, preventing a
range or transitive resolution from silently changing the managed toolchain.
The publisher separately rejects managed-package deltas and validates resolved
managed versions against its own reviewed Dockerfile before any write.

A non-main workflow can only run by explicit manual dispatch. Such a run is a
verification preview: publishing and interpretation jobs require main, repair
planning/model secrets are disabled, and the eligible output remains false even
if its report is verified. Main's existing activation and publishing flags remain
required. Preview success is evidence for review, not publication authority.

Native Node 24 action updates remain pinned to upstream commit hashes. They do
not select the website's Node version or change production configuration.
