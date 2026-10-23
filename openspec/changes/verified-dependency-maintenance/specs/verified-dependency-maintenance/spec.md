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
after verification, limited to the package manifest, lockfile and separately
enabled bounded mechanical display-component compatibility repairs.

#### Scenario: Base revision changed
- **WHEN** the website base branch differs from the tested base
- **THEN** publication SHALL stop and require a new verification run

#### Scenario: Artifact changes scripts or dependencies outside policy
- **WHEN** an artifact changes scripts, adds/removes a dependency, or changes files outside the dependency/repair policy
- **THEN** publication SHALL be rejected independently of AI assessment

### Requirement: Compiler-driven bounded compatibility repair
Guardian SHALL permit at most one structured repair attempt for a supported
candidate TypeScript failure after a passing baseline, only when explicitly enabled.

#### Scenario: A supported display import changed
- **WHEN** the planner proposes an eligible dependency-related rename at an observed compiler location
- **THEN** a trusted parser SHALL apply the bounded recipe to fresh original source, all candidate checks SHALL rerun, and the publisher SHALL independently reproduce exact source bytes

#### Scenario: Repair needs backend or test changes
- **WHEN** a proposed repair touches protected paths or exceeds mechanical recipe limits
- **THEN** publication SHALL be blocked and human migration review required

### Requirement: Independent SIS PR verification
SIS SHALL verify merge checkouts in credential-free containers using reviewed base-branch verifier scripts.

#### Scenario: Verifier bootstrap has not been reviewed
- **WHEN** the base branch lacks the verifier assets
- **THEN** CI SHALL fail explicitly rather than execute PR-provided verifier scripts on the host

### Requirement: Comprehensive advisory interpretation
Structured AI advice SHALL distinguish observation, possible impact, proposed
human review and verification, retaining cited evidence and uncertainty.

#### Scenario: Advice contains an executable command or secret
- **WHEN** any expanded advisory field violates output policy
- **THEN** the entire note SHALL be rejected and deterministic results retained
