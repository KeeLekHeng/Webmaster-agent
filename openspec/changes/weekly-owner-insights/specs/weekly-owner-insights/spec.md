# Weekly owner insights

## ADDED Requirements

### Requirement: Bounded query/page insights
Guardian SHALL collect at most 1,000 finalized query/page rows per period when
enabled, validate page scope, omit likely identifiers/credentials, preserve
separate aggregate totals and keep query strings out of model inputs.

#### Scenario: A query is absent from the previous sample
- **WHEN** a current query/page row has no previous matching row
- **THEN** the report labels previous performance unknown and SHALL NOT invent
  a zero baseline, loss or ranking change

#### Scenario: Query collection fails
- **WHEN** the optional query request fails
- **THEN** aggregate results remain available and query coverage is unavailable

### Requirement: Explicit delivery reconciliation
Guardian SHALL expose safe receipt identifiers and accept local owner received
or retry decisions only for unresolved receipts of the enrolled destination.

#### Scenario: Owner permits a retry
- **WHEN** an unresolved receipt is marked retry
- **THEN** the decision is audited, no message is immediately sent, and only one
  subsequent claim of the same delivery key succeeds

#### Scenario: Delivery may still be running
- **WHEN** a pending receipt was updated less than 120 seconds ago
- **THEN** reconciliation is rejected

### Requirement: Authorized weekly local digest
Guardian SHALL default to disabled and run only after local owner activation,
using Monday 09:00 Malaysia weeks, durable per-site claims, the existing kill
switch and private-owner routing.

#### Scenario: A weekly trigger repeats
- **WHEN** a site/week was already claimed
- **THEN** no collection, model call or message is repeated

#### Scenario: A collection stage fails
- **WHEN** speed collection fails but search data is available
- **THEN** successful evidence is preserved, later independent stages may run,
  and the saved weekly outcome records partial collection without raw errors

### Requirement: Read-only listener recovery
Guardian SHALL retry transient read-only polling up to three times with 2, 4 and
8 second waits while respecting the kill switch, without resending messages.

#### Scenario: Poll recovers after a transient network failure
- **WHEN** a retry returns updates successfully
- **THEN** saved offsets and command receipts prevent duplicate processing
