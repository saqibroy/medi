# Phase 4 Production Operations Plan

This plan turns Medi's research MVP into an operable deployment while treating
medical images as potentially sensitive data. Model selection does not change
these controls: no model or external AI service may receive image pixels,
metadata, annotations, or free text unless that data flow has been explicitly
approved and configured.

Status: in progress.

## Production Boundary

The current product remains intended for synthetic, properly anonymized, or
contractually approved research data. A deployment must not claim support for
identifiable patient data until every applicable release gate in this document
has evidence and the deployment owner has completed legal, privacy, and
security review.

Important distinctions:

- DICOM metadata removal alone does not prove anonymization. Filenames, private
  tags, UIDs, free text, annotations, linked tables, and burned-in pixel text can
  still identify a person.
- Pseudonymized data remains personal data under GDPR. The re-identification key
  must stay separate and outside Medi unless a specifically approved workflow
  requires it.
- NIfTI files and sidecars can also contain identifying descriptions, filenames,
  dates, or linked research identifiers.
- The default external-AI policy is deny: Medi performs no external model/API
  egress unless an administrator enables an approved provider and purpose.

This is an engineering baseline, not a substitute for legal advice. GDPR lawful
basis, controller/processor roles, research exemptions, national health-data
rules, and transfer requirements must be reviewed for each deployment.

## Current Baseline And Gaps

Already present:

- Organization-scoped projects, scans, annotations, labels, and exports.
- Admin, annotator, and reviewer role checks with cross-organization tests.
- Synthetic seed data and documentation requiring de-identified uploads.
- DICOM metadata allowlisting plus warnings for likely PHI-bearing tags.
- Annotation change history and segmentation-mask checksums.
- Migration-first startup and PostgreSQL-backed Docker Compose.
- Backend liveness/readiness, database readiness, and frontend health probes.

Not production-ready yet:

- Development Compose intentionally seeds synthetic demo data; production
  deployment must set `SEED_DEMO_DATA=false` and now fails startup if it does not.
- Bearer sessions now have absolute expiry and logout revocation, but active
  session inventory, idle timeout, and secure-cookie transport remain absent.
- Production configuration now requires an explicit token secret and exact CORS
  origins; local-only defaults remain available only for development.
- Uploaded originals and previews use local volumes without encryption policy.
- PHI detection warns but does not provide a validated de-identification gate.
- Annotation history is append-oriented but not immutable; cascade deletion can
  remove it with the annotation.
- Dataset releases and annotation snapshots are not versioned.
- Backup, restore, retention, legal-hold, and verified deletion procedures are
  not implemented.
- Request logging is structured and payload-safe, and process-local rate limits
  exist; security audit records, shared rate enforcement, monitoring, and error
  tracking remain absent.

## Medical Image Intake And De-identification

- [ ] Define an upload policy per organization: `synthetic_only`,
  `anonymized_only`, or `approved_sensitive`.
- [ ] Quarantine new originals until format validation and de-identification
  checks finish; quarantined objects must not be viewable or exportable.
- [ ] Store only an allowlisted metadata projection in normal application tables.
- [ ] Apply a documented DICOM de-identification profile and record its profile
  version, tool version, timestamp, and result without storing removed values.
- [ ] Reject or quarantine unknown/private tags unless a reviewed rule handles
  them.
- [ ] Detect and flag burned-in annotations; do not claim automatic pixel
  anonymization without a validated workflow and human review option.
- [ ] Pseudonymize UIDs consistently when study relationships must survive; keep
  any mapping key in a separate, access-controlled system.
- [ ] Sanitize filenames, archive paths, NIfTI headers, and JSON/BIDS sidecars.
- [ ] Add admin-visible intake results and safe remediation messages.
- [ ] Add fixtures proving patient name, ID, birth date, accession number,
  institution data, private tags, and unsafe filenames are never returned by the
  public API or written to logs.

Acceptance evidence:

- A written de-identification profile and threat model.
- Automated allowlist/denylist fixtures plus a human review protocol for
  burned-in text.
- An end-to-end test showing quarantined data cannot be viewed, signed, or
  exported.

## Encryption And Secrets

- [ ] Terminate TLS at the ingress and redirect HTTP to HTTPS.
- [ ] Require TLS for PostgreSQL, object storage, Redis, monitoring, and any
  other service connection outside a private host boundary.
- [ ] Encrypt database volumes, object storage, and backups with managed keys.
- [ ] Define key ownership, rotation, access logging, and emergency revocation.
- [ ] Remove default production secrets and fail startup when required secrets
  are missing or still use documented development values.
- [ ] Load secrets from a deployment secret manager; never bake them into images,
  frontend bundles, Compose files, logs, or example datasets.
- [ ] Add automated secret scanning and dependency/container vulnerability
  scanning to CI.

## Identity, Sessions, And Authorization

- [x] Replace perpetual bearer tokens with database-backed opaque sessions that
  store only keyed token digests and enforce configurable absolute expiry.
- [ ] Prefer `Secure`, `HttpOnly`, `SameSite` cookies for the browser deployment,
  with CSRF protection where required.
- [ ] Add idle timeout and active-session inventory. Logout revocation,
  inactive-user enforcement, and absolute expiry are implemented.
- [x] Configure exact allowed origins from environment variables.
- [ ] Preserve deny-by-default roles and add project-level membership if users
  must not see every project in their organization.
- [ ] Add object-level authorization tests for every scan, mask, export, signed
  URL, audit, and administrative endpoint.
- [ ] Plan SSO/MFA for deployments handling sensitive or regulated data.

## Immutable Audit Records

- [ ] Introduce a dedicated audit-event model covering authentication, reads of
  sensitive scans, uploads, downloads, signed URLs, exports, role changes,
  annotation changes, reviews, and deletions.
- [ ] Store actor user/session, organization, object identifiers, action, result,
  timestamp, request/correlation ID, and safe network context.
- [ ] Never store tokens, removed DICOM values, raw free-text payloads, image
  pixels, or secrets in audit events.
- [ ] Prevent application roles from updating or deleting audit events.
- [ ] Export audit events to append-only/WORM-capable storage with integrity
  verification and an approved retention period.
- [ ] Replace annotation-history cascade deletion with a tombstone or retained
  audit reference before claiming immutability.
- [ ] Add tests proving normal administrators cannot alter audit history.

## Dataset And Annotation Versioning

- [ ] Add immutable dataset releases containing a manifest of scan object
  versions, checksums, metadata-profile versions, labels, and approved
  annotation versions.
- [ ] Give releases stable IDs and monotonic project version numbers.
- [ ] Preserve annotation revision lineage rather than overwriting the only
  training-data representation.
- [ ] Record export format/tool versions and deterministic checksums.
- [ ] Prevent a released dataset from silently changing when live annotations
  are edited or deleted.
- [ ] Support superseding and revoking releases without erasing their audit
  trail.

## Private Object Storage

Implementation details remain in `PRODUCTION_STORAGE_PLAN.md`.

- [ ] Put originals, previews, masks, and export artifacts in private,
  organization-prefixed object storage.
- [ ] Use least-privilege service identities and deny public bucket access.
- [ ] Issue short-lived signed URLs only after object-level authorization; do
  not sign original uploads for browser access by default.
- [ ] Encrypt objects and object versions with managed keys.
- [ ] Log signed-URL issuance and sensitive object access.
- [ ] Define lifecycle rules separately for originals, derivatives, exports,
  quarantined objects, and deleted-data tombstones.

## Backup, Restore, Retention, And Deletion

- [ ] Define recovery point and recovery time objectives for PostgreSQL and
  object storage.
- [ ] Automate encrypted backups with separate credentials and failure alerts.
- [ ] Run and record restore drills; a backup is not accepted until restoration
  has been tested.
- [ ] Define retention by data class and customer agreement, including audit
  records and superseded dataset releases.
- [ ] Add organization/project/scan deletion workflows that enumerate database
  rows, object versions, previews, masks, exports, queues, caches, and backups.
- [ ] Support legal holds and prevent deletion while a valid hold applies.
- [ ] Produce a deletion receipt containing identifiers and completion state,
  never deleted PHI.
- [ ] Document how deletion propagates into expiring backups and how exceptions
  are communicated.

## GDPR And Privacy Operations

- [ ] Record controller/processor roles, processing purposes, lawful basis, and
  the additional Article 9 condition for health data before sensitive-data use.
- [ ] Complete a DPIA when the planned processing is likely to create high risk,
  especially for large-scale health-data or new-technology processing.
- [ ] Maintain records of processing activities, subprocessors, data locations,
  and international transfer mechanisms.
- [ ] Provide workflows for access, correction, restriction, objection, export,
  and erasure requests where applicable.
- [ ] Apply purpose limitation and data minimization to metadata, logs, free text,
  analytics, and support tooling.
- [ ] Define incident response, breach assessment, notification ownership, and
  evidence preservation.
- [ ] Obtain privacy/security review and appropriate customer agreements before
  enabling identifiable or pseudonymized patient data.

Useful primary references:

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj), including
  Articles 5, 9, 25, 30, 32, 35, and 44-49.
- [European Data Protection Board: anonymisation and pseudonymisation](https://www.edpb.europa.eu/topics/ai-and-technology/anonymisationpseudonymisation_en).

## External AI And Model Governance

- [ ] Keep `EXTERNAL_AI_ENABLED=false` as the safe default and implement no
  provider call on the default code path.
- [ ] Maintain an approved-provider registry with purpose, model/version, data
  classes allowed, region, retention/training terms, subprocessors, and contract
  owner.
- [ ] Block pixels, raw DICOM, metadata, annotations, and notes from external
  egress unless the exact data flow is approved.
- [ ] Prefer local or private-endpoint inference for sensitive workloads.
- [ ] Add an egress gateway/allowlist and audit every approved request without
  logging sensitive payloads.
- [ ] Present clear administrator controls and dataset-level consent/policy
  checks; never silently enable a provider from a frontend feature flag.
- [ ] Version model outputs and keep them distinguishable from human annotations.

## Operational Reliability

- [x] Add database-aware backend readiness, process liveness, frontend health,
  and Compose health dependencies.
- [ ] Add health probes to deployment manifests and alert on sustained failure.
- [x] Add structured JSON request logs with server-issued correlation IDs and an
  allowlist that excludes bodies, headers, query values, and exception text.
- [ ] Add error tracking that strips sensitive request bodies and metadata.
- [ ] Replace the process-local login and expensive-route limits with shared,
  per-user, per-organization enforcement for multi-instance production.
- [ ] Add database connection-pool settings, statement timeouts, and slow-query
  visibility.
- [x] Define migration preflight, backup/restore rehearsal, forward deployment,
  and rollback procedures for PostgreSQL in `POSTGRES_MIGRATION_RUNBOOK.md`.
- [x] Remove automatic demo seeding from production startup; development seeding
  remains explicit through `SEED_DEMO_DATA=true`.
- [ ] Pin and scan runtime images, run containers as non-root, and use read-only
  filesystems where possible.
- [ ] Add operator runbooks for deploy, rollback, degraded storage, database
  outage, queue outage, key compromise, and security incident.

## Implementation Sequence

1. [x] Establish liveness/readiness and verify Compose startup.
2. [x] Separate development and production configuration; production startup
   rejects demo seeding, development database defaults, missing/weak token
   secrets, and implicit CORS origins.
3. [x] Document and test the PostgreSQL migration/rollback procedure with an
   isolated upgrade/downgrade/upgrade cycle in CI.
4. [x] Add structured request logging, request IDs, and redaction. Error
   tracking remains a separate controlled integration.
5. [x] Add database-backed expiring sessions, logout revocation, exact CORS, and
   a configurable process-local rate-limit baseline for login, upload,
   reprocessing, and export routes. Shared multi-instance enforcement, idle
   timeout, active-session inventory, and secure-cookie transport remain
   explicit production gates above.
6. [ ] In progress: introduce the storage abstraction and private object-storage
   backend. Completed locally: tenant-scoped keys, traversal-safe local storage,
   and original/preview/reprocess/mask integration. Remaining: S3 implementation,
   signed preview URLs, encryption configuration, runtime verification, and merge.
7. [ ] Add quarantine plus the versioned DICOM/NIfTI de-identification gate.
8. [ ] Add immutable security audit events.
9. [ ] Add dataset releases and annotation revision manifests.
10. [ ] Implement backup/restore drills, retention, legal hold, and deletion.
11. [ ] Complete GDPR/DPIA/processor evidence for the target deployment.
12. [ ] Run a production-readiness review and close every applicable gate.

## Phase 4 Exit Criteria

- [ ] Production configuration fails closed on missing secrets and unsafe
  defaults.
- [ ] PostgreSQL migrations, backup, restore, and rollback are rehearsed.
- [ ] Private encrypted storage and tenant-safe access are implemented.
- [ ] Health, logs, alerts, error tracking, and rate limits are operational.
- [ ] Sensitive image intake is quarantined until approved de-identification
  checks complete.
- [ ] Audit records are immutable and dataset releases are reproducible.
- [ ] Retention/deletion and external-AI egress policies are enforceable.
- [ ] Required privacy, security, and legal evidence is approved for the target
  data classification.
