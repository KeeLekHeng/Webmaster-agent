## ADDED Requirements

### Requirement: Disposable real backend
Verification SHALL use real isolated Postgres, Supabase Auth and data APIs with
synthetic records and test-only credentials, preserving RLS and MFA.

#### Scenario: Career page requires a published job
- **WHEN** the browser suite requests the seeded career route
- **THEN** the normal application query SHALL retrieve the publication from the disposable database without an application success stub

#### Scenario: Backend or seed is unavailable
- **WHEN** a required service, migration, seed or real backend probe fails
- **THEN** verification and dependency publishing SHALL be blocked

#### Scenario: Establish the startup control before website verification
- **WHEN** startup fails before any website migration executes
- **THEN** an explicitly selected diagnostic job MAY start trusted service images with standard loopback-bound networking and no website input
- **AND** it SHALL execute a real temporary-table write/read, clean up its resources and emit startup-only evidence that cannot authorize publishing

### Requirement: Restricted candidate execution
Candidate application and migration input SHALL execute only inside restricted
test containers, with no production connection, host socket or production secret.

#### Scenario: Candidate migration contains a psql host escape
- **WHEN** a migration contains a psql meta-command or exceeds input budgets
- **THEN** initialization SHALL reject it before execution

#### Scenario: Backend exposes a public port or unsafe mount
- **WHEN** inspection finds an unauthorized binding, privilege, mount or network
- **THEN** candidate input SHALL NOT execute and owned resources SHALL be cleaned up

### Requirement: Real authentication and honest coverage
Required verification SHALL exercise real password authentication and MFA browser
access. Mock-specific tests and skipped legacy suites SHALL be disclosed separately.

#### Scenario: Password-only legacy UI fixture conflicts with MFA
- **WHEN** an existing suite lacks MFA automation
- **THEN** MFA SHALL NOT be disabled to make that suite pass and its coverage limit SHALL be recorded

#### Scenario: Documented password-only UAT configuration
- **WHEN** the trusted admin smoke test runs against the disposable backend
- **THEN** a separate application process SHALL use the documented `REQUIRE_ADMIN_MFA=false` UAT configuration
- **AND** it SHALL verify anonymous rejection, real password login, synthetic draft creation/read/update/deletion, database persistence, draft privacy and actual sign-out without success mocks or saved sessions
- **AND** the separate MFA-on probe SHALL still pass; neither profile changes production configuration or enables the extensive legacy admin suites

#### Scenario: Admin smoke coverage is absent
- **WHEN** either required admin profile fails or its proof is missing, skipped or malformed
- **THEN** verification and dependency publishing SHALL be blocked

### Requirement: Independent backend proof and cleanup
Publishing SHALL require backend evidence for each tested copy and successful
scoped cleanup. Earlier mock-only reports SHALL NOT authorize publication.

#### Scenario: Backend proof is omitted or cleanup fails
- **WHEN** an artifact lacks required real-service evidence or successful cleanup
- **THEN** the trusted publisher SHALL reject it before any repository write
