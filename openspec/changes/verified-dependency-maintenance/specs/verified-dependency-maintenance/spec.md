## ADDED Requirements

### Requirement: Deterministic dependency selection
Guardian SHALL distinguish installed versions, stable compatible updates and
known advisories using registry/package-manager evidence, never model guesses.

#### Scenario: Only a major release is available
- **WHEN** a dependency has no newer compatible stable version
- **THEN** Guardian SHALL NOT change its major version automatically

### Requirement: Isolated paired verification
Guardian SHALL verify a pinned baseline and candidate using the same required
checks in credential-free containers, without production connections.

#### Scenario: The baseline fails
- **WHEN** a required baseline check fails or is unavailable
- **THEN** no dependency PR SHALL be published

#### Scenario: Candidate verification fails
- **WHEN** any candidate check fails, times out or is missing
- **THEN** the outcome SHALL be reported as unverified and publication blocked

### Requirement: Narrow standing authorization
Guardian SHALL allow automatic dependency PRs only under explicit enabled policy,
after verification, limited to the package manifest and lockfile.

#### Scenario: Base revision changed
- **WHEN** the website base branch differs from the tested base
- **THEN** publication SHALL stop and require a new verification run

#### Scenario: Artifact changes scripts or dependencies outside policy
- **WHEN** an artifact changes scripts, adds/removes a dependency, or changes other files
- **THEN** publication SHALL be rejected independently of AI assessment

### Requirement: Comprehensive advisory interpretation
Structured AI advice SHALL distinguish observation, possible impact, proposed
human review and verification, retaining cited evidence and uncertainty.

#### Scenario: Advice contains an executable command or secret
- **WHEN** any expanded advisory field violates output policy
- **THEN** the entire note SHALL be rejected and deterministic results retained
