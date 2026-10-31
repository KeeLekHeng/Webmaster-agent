## ADDED Requirements

### Requirement: Explicit browser-toolchain ownership
Automatic dependency planning SHALL preserve direct managed browser-package
declarations and derive their reviewed version from trusted pinned configuration.

#### Scenario: New Playwright release is available
- **WHEN** registry policy selects an eligible managed-package update
- **THEN** the report SHALL defer it with a manual-review action
- **AND** other eligible packages SHALL still undergo every required check

#### Scenario: Toolchain is vulnerable or no automatic update remains
- **WHEN** a managed package has an advisory or is the only available update
- **THEN** its review action and advisory evidence SHALL remain visible
- **AND** no deferred version SHALL be claimed as verified or published

### Requirement: Independent enforcement
The controller and publisher SHALL reject managed resolved-version drift and
the publisher SHALL reject managed manifest changes before any repository write.

#### Scenario: Lockfile regeneration changes a managed browser version
- **WHEN** candidate inventory differs from the reviewed browser version
- **THEN** the batch SHALL be blocked without weakening browser checks

### Requirement: Read-only branch previews
A manually dispatched non-main preview SHALL retain every verification gate and
SHALL NOT expose writer/model secrets or authorize publishing, regardless of flags.

#### Scenario: Preview report is verified while publishing flag is true
- **WHEN** verification runs from a non-main branch
- **THEN** publishing and model jobs SHALL be skipped and eligible SHALL be false
