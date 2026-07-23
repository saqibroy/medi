# Security Audit Implementation Plan

Status: Implementation boundary complete; production gates remain

This plan is the recovery point for the Phase 4 immutable security-audit work.
Audit records must provide operational accountability without becoming a
second store of patient data, credentials, or clinical free text.

## Current Implementation Boundary

- [x] Add a tenant-scoped, append-only security-event table with actor user and
  session identifiers, action, result, target type/ID, timestamp, request ID,
  and a strictly allowlisted details object.
- [x] Add keyed integrity hashes so exported or copied events can be verified.
- [x] Reject audit-event updates and deletes in both the ORM and database.
- [x] Add an admin-only, organization-scoped listing API. Do not add update or
  delete endpoints.
- [x] Record login success/failure, logout, medical-image intake and reprocess
  decisions, sensitive pixel/mask reads, signed-URL issuance, exports, project
  and label administration, annotation changes/reviews/deletions, and mask
  changes/deletions.
- [x] Record administrator active-session listing and forced revocation using
  organization/session IDs only; never copy user email, token digest, activity
  metadata, network context, or credentials into audit details.
- [x] Record retained release-artifact materialization and download using only
  the stable release target; never copy artifact bytes, manifests, storage keys,
  object versions, checksums, or generated filenames into audit details.
- [x] Record retention-policy, legal-hold, deletion-request approval/cancellation,
  and successful operator execution using only stable IDs and controlled scalar
  details; governance payloads, inventories, and receipts do not enter audit
  rows.
- [x] Prove tenant isolation, non-admin denial, safe-field behavior, integrity
  verification, and database-level immutability with automated tests.
- [x] Enforce an explicit authentication/role policy for all 90 API routes and
  prove every parameterized route, collection, query, and request-body object
  reference is cross-tenant opaque. Audit rows remain organization-scoped while
  still recording the signed-in tenant's denied access attempts.
- [x] Rebuild and run the complete application, rehearse migrations against
  PostgreSQL, and perform authenticated live smoke checks before publication.

## Data-Minimization Rules

Audit events must never contain:

- bearer tokens, token digests, passwords, cookies, or secrets;
- DICOM values removed or rejected by de-identification;
- uploaded filenames or object-storage keys;
- image pixels, mask bytes, annotation coordinates, or scan metadata;
- email addresses, free-text descriptions, annotation notes, or request bodies;
- raw network addresses or user-agent strings.

Identifiers already used for authorization boundaries may be recorded as UUIDs.
The `details` object is action-specific and accepts only documented keys with
bounded scalar values.

## Verification Evidence

Completed on 2026-07-16:

- 82 backend tests passed, including priority route emission, tenant isolation,
  safe-field exclusion, keyed-hash verification, and ORM/database immutability.
- The frontend TypeScript/Vite production build passed.
- PostgreSQL completed upgrade to head, downgrade to base, and a second upgrade
  to migration `20260716_0009`.
- Docker Compose rebuilt successfully; database, backend, and frontend health
  checks passed.
- Live authenticated smoke checks proved sensitive slice-read audit creation,
  organization-admin retrieval, correlation/session identifiers, non-admin
  denial, and absence of bearer/email values.
- A direct PostgreSQL `UPDATE` against the live audit table was rejected by the
  append-only trigger.

The later data-lifecycle increment adds audited governance routes and operator
execution without changing the ledger's allowlisted, payload-free boundary;
signed success evidence is transactionally committed with the deletion receipt
and lifecycle events, while failed attempts append signed error evidence. Its
full evidence is tracked in `DATA_LIFECYCLE_RECOVERY_PLAN.md`.

The external-AI governance increment adds explicit signed audits for provider
and project-flow creation/revocation plus every dry-run authorization decision.
Only stable targets, controlled purpose/reason, class count, provider version,
and allowed/denied result enter audit details; provider contracts, prompts,
medical payloads, credentials, and model responses do not. See
`EXTERNAL_AI_GOVERNANCE_PLAN.md`.

The privacy-operations increment audits processing-record creation/revocation
and every privacy-request transition. Audit details are limited to stable target
IDs plus controlled policy version, purpose, scope, request type, workflow
status, and reason codes. Raw or digested subject references, case/evidence
references, identity material, correspondence, and delivered data never enter
the audit ledger. See `PRIVACY_OPERATIONS_PLAN.md`.

Its local verification added signed-audit assertions to the 129-test backend
suite and an authenticated synthetic smoke proving the request-create audit is
present while the raw subject reference is absent from the API response and
audit details.

The object-authorization increment adds a fail-closed route inventory and
two-organization matrix without weakening denied-attempt audit evidence. Its
local verification passes all 151 backend tests and is recorded in
`OBJECT_AUTHORIZATION_PLAN.md`.

The annotation-history retention increment replaces cascade loss with an
append-only, value-free tombstone for direct and lifecycle deletion. It retains
controlled summaries plus keyed lineage/integrity hashes while removing raw
geometry and notes. Its 153-test and migration evidence is recorded in
`ANNOTATION_HISTORY_TOMBSTONE_PLAN.md`.

The retained-release increment audits administrator artifact materialization
and authenticated downloads without widening the details allowlist. Release
bytes remain in private storage, while the audit target is the stable release
UUID only. Its evidence is recorded in
`RETAINED_RELEASE_ARTIFACT_PLAN.md`.

The organization-deletion increment retains append-only audit identifiers while
removing working medical data and mutable user identity. Its signed execution
event and checksum receipt use stable IDs and controlled target dispositions
only; see `ORGANIZATION_DELETION_PLAN.md`.

## Remaining Production Gates

- [ ] Export events to independently controlled append-only/WORM-capable
  storage and verify the keyed hashes after export.
- [ ] Approve an audit retention period, archival access process, and deletion
  exception policy with legal/security stakeholders.
- [x] Replace annotation-history cascade loss with immutable, data-minimized
  tombstones while allowing raw geometry/notes to follow approved deletion
  policy.
- [ ] Add safe network context only after a trusted-proxy policy and privacy
  review define what may be retained.
- [ ] Monitor integrity verification and alert on gaps or failed audit writes.
