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
- Database-backed sessions have absolute expiry and logout revocation. Browser
  credentials use HttpOnly, SameSite cookies plus signed CSRF protection, and
  production configuration requires Secure host-only cookies. Real-ingress TLS
  evidence, active-session inventory, and idle timeout remain absent.
- Production configuration now requires an explicit token secret and exact CORS
  origins; local-only defaults remain available only for development.
- Production code supports private KMS-encrypted S3 storage, but target-account
  bucket policy, lifecycle, backup, and deletion evidence remains outstanding.
- A versioned metadata-screening quarantine gate is enforced, but it does not
  yet provide validated OCR/defacing, UID pseudonymization, or legal proof of
  anonymization.
- Annotation history is append-oriented but not immutable; cascade deletion can
  remove it with the annotation.
- Dataset releases are immutable and reproducible in the application database;
  target S3 VersionId evidence, retained portable artifacts, and independent
  WORM replication remain deployment gates.
- Encrypted disposable restore drills, versioned policy, legal holds, and
  project/scan deletion evidence are implemented, but approved values,
  organization deletion, target backup/vault controls, and signed drills remain
  incomplete.
- Request logging is structured and payload-safe, append-only security audit
  records exist, and Redis provides shared rate enforcement with hashed keys.
  Managed-Redis deployment evidence, monitoring, and error tracking remain
  absent.

## Medical Image Intake And De-identification

- [ ] Define an upload policy per organization: `synthetic_only`,
  `anonymized_only`, or `approved_sensitive`.
- [x] Quarantine new originals until format validation and de-identification
  checks finish; quarantined objects must not be viewable or exportable.
- [x] Store only an allowlisted metadata projection in normal application tables.
- [ ] Apply a validated DICOM transformation profile that removes or rewrites
  unsafe elements. The implemented v1 screening gate records its profile/tool
  version, timestamp, and result without storing detected values, but it does
  not rewrite quarantined payloads.
- [x] Reject or quarantine unknown/private tags unless a reviewed rule handles
  them.
- [x] Flag `BurnedInAnnotation=YES` or a missing/unknown declaration. Actual
  pixel OCR/defacing remains unimplemented and is not claimed as automatic
  anonymization.
- [ ] Pseudonymize UIDs consistently when study relationships must survive; keep
  any mapping key in a separate, access-controlled system.
- [x] Neutralize filenames, validate archive paths, and screen supported NIfTI
  header text. JSON/BIDS sidecars remain unsupported and are rejected.
- [x] Add admin-visible intake results and safe remediation messages.
- [x] Add fixtures proving patient name, ID, birth date, accession number,
  institution data, private tags, and unsafe filenames are never returned by the
  public API or written to logs.

Acceptance evidence:

- [x] A written de-identification profile and threat model.
- [ ] Automated allowlist/denylist fixtures are present; a formally validated
  human review protocol for burned-in text remains required.
- [x] An end-to-end test showing quarantined data cannot be viewed, signed, or
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
- [x] Add automated secret scanning and dependency/container vulnerability
  scanning to CI. The P0 repository boundary is complete and tracked in
  `PRODUCTION_READINESS_REVIEW.md`; moderate Cornerstone/VTK advisories remain
  deferred to a future major viewer upgrade.

## Identity, Sessions, And Authorization

- [x] Replace perpetual bearer tokens with database-backed opaque sessions that
  store only keyed token digests and enforce configurable absolute expiry.
- [x] Use `Secure`, `HttpOnly`, `SameSite` cookies for browser sessions with
  signed, session-bound double-submit CSRF protection. Production ingress
  verification remains tracked in `SESSION_AND_RATE_LIMIT_PLAN.md`.
- [ ] Add idle timeout and active-session inventory. Logout revocation,
  inactive-user enforcement, and absolute expiry are implemented.
- [x] Configure exact allowed origins from environment variables.
- [ ] Preserve deny-by-default roles and add project-level membership if users
  must not see every project in their organization.
- [ ] Add object-level authorization tests for every scan, mask, export, signed
  URL, audit, and administrative endpoint.
- [ ] Plan SSO/MFA for deployments handling sensitive or regulated data.

## Abuse Protection

- [x] Use atomic Redis counters for login and expensive upload/reprocess/export
  routes across API instances; retain process-local memory only for tests and
  explicit development use.
- [x] Hash direct peer identities before storing rate keys, do not trust proxy
  forwarding headers by default, and fail closed if production Redis is down.
- [ ] Provision authenticated, encrypted, highly available managed Redis and
  verify failover, alerting, capacity, and retention behavior in the target
  environment.

## Immutable Audit Records

- [x] Introduce a dedicated audit-event model covering every currently
  implemented authentication, sensitive scan/mask read, upload/reprocess,
  signed-URL, export, administrative, annotation, review, and deletion route.
  Future role-change/download routes must join the explicit audit map when they
  are introduced.
- [x] Store actor user/session, organization, object identifiers, action, result,
  timestamp, and request/correlation ID.
- [ ] Add safe network context after trusted-proxy and privacy policies define
  what may be retained; raw IP addresses and user agents are not stored now.
- [x] Never store tokens, removed DICOM values, raw free-text payloads, image
  pixels, or secrets in audit events.
- [x] Prevent application roles from updating or deleting audit events through
  read-only routing, ORM guards, and PostgreSQL/SQLite triggers.
- [ ] Export audit events to append-only/WORM-capable storage with integrity
  verification and an approved retention period.
- [ ] Replace annotation-history cascade deletion with a tombstone or retained
  audit reference before claiming immutability.
- [x] Add tests proving normal administrators cannot alter audit history.

Implementation and verification evidence is recorded in
`SECURITY_AUDIT_PLAN.md`. WORM export, retention approval, safe network context,
and annotation-history tombstoning remain open production gates.

## Dataset And Annotation Versioning

- [x] Add immutable dataset releases containing a manifest of scan object
  versions, checksums, metadata-profile versions, labels, and approved
  annotation versions.
- [x] Give releases stable IDs and monotonic project version numbers.
- [x] Preserve annotation revision lineage rather than overwriting the only
  training-data representation.
- [x] Record export format/tool versions and deterministic checksums.
- [x] Prevent a released dataset from silently changing when live annotations
  are edited or deleted.
- [x] Support superseding and revoking releases without erasing their audit
  trail.

## Private Object Storage

Implementation details remain in `PRODUCTION_STORAGE_PLAN.md`.

Repository-controlled increment complete: deployable AWS S3/KMS controls,
data-class lifecycle tagging, a read-only control verifier, CI linting, and
operational runbooks are implemented without claiming target-account evidence.

- [ ] Put originals, previews, masks, and export artifacts in private,
  organization-prefixed object storage.

Originals, previews, and masks use the private tenant-prefixed abstraction.
Export artifacts are still response payloads rather than retained private
objects, so the combined gate remains open.
- [x] Define a least-privilege runtime policy and bucket policy denying public,
  insecure, missing-KMS, and wrong-KMS writes. Target-account attachment and
  verification remain open.
- [x] Issue short-lived signed URLs only after object-level authorization; do
  not sign original uploads for browser access by default.
- [x] Require KMS encryption for production writes and define KMS default
  encryption plus S3 Bucket Keys for object versions.
- [x] Log signed-URL issuance and sensitive object access.
- [ ] Define lifecycle rules separately for originals, derivatives, exports,
  quarantined objects, and deleted-data tombstones.

Lifecycle tags/rules now cover originals, masks, metadata, previews, exports,
and quarantine. Deleted-data tombstones remain open until the deletion data
model is implemented. Target-account deployment evidence is still required.

## Backup, Restore, Retention, And Deletion

- [x] Store explicit versioned recovery point/time objectives per organization;
  approved target values remain a deployment gate.
- [ ] Automate encrypted backups with separate credentials and failure alerts.
- [x] Run and record encrypted disposable PostgreSQL plus synthetic-object
  restore drills in CI; signed target-vault drills remain open.
- [x] Store versioned retention by medical-data class, audit events, backups,
  and dataset releases without assuming production durations.
- [ ] Add organization/project/scan deletion workflows that enumerate database
  rows, object versions, previews, masks, exports, queues, caches, and backups.
- [x] Support append-only organization/project/scan legal holds and prevent
  approval or execution while a valid hold applies.
- [x] Produce an append-only checksum receipt containing identifiers and state,
  never deleted PHI.
- [x] Document how deletion propagates into expiring backups and how exceptions
  are communicated.

Project and scan requests, exact-prefix purge, database cleanup/tombstoning,
release revocation, and receipts are implemented. Organization-wide execution,
queue/cache/retained-export enumeration, and target backup evidence keep the
combined deletion gate open.

## GDPR And Privacy Operations

- [~] Immutable versions now record declared controller/processor role,
  processing purpose, Article 6 basis, and Article 9 condition. Target legal
  approval remains required before sensitive-data use.
- [~] DPIA screening/outcome, DPO review, and evidence references are versioned;
  `consultation_required` records cannot become active. The actual assessment,
  approval, and any authority consultation remain external deployment gates.
- [~] Processing records now cover controlled subject/data/recipient categories,
  processor references, locations, transfers, retention snapshots, and security
  controls. Target ROPA and processor/transfer evidence remain to be supplied.
- [~] Admin workflows now cover access, correction, restriction, objection,
  portability, and erasure using keyed subject-reference digests, two-person
  identity evidence, calendar deadlines, controlled outcomes, and append-only
  events. Identity/case systems, secure delivery, correction/restriction actions,
  and target operator exercises remain external gates.
- [x] The repository boundary applies controlled categories/references, excludes
  request bodies and privacy evidence from audit/log records, and requires an
  executed matching deletion receipt before erasure fulfillment. Broader target
  analytics/support review remains required.
- [~] Repository incident response, privacy-safe evidence preservation, and
  personal-data breach assessment handoff are defined in
  `SECURITY_INCIDENT_RUNBOOK.md`. Named notification owners, target severity/
  contact rules, legal decisions, and signed exercises remain deployment gates.
- [ ] Obtain privacy/security review and appropriate customer agreements before
  enabling identifiable or pseudonymized patient data.

Useful primary references:

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj), including
  Articles 5, 9, 25, 30, 32, 35, and 44-49.
- [European Data Protection Board: anonymisation and pseudonymisation](https://www.edpb.europa.eu/topics/ai-and-technology/anonymisationpseudonymisation_en).

## External AI And Model Governance

- [x] Keep `EXTERNAL_AI_ENABLED=false` as the safe default and implement no
  provider call on the default code path.
- [x] Maintain an approved-provider registry with purpose, model/version, data
  classes allowed, region, retention/training terms, subprocessors, and contract
  owner.
- [x] Block pixels, raw DICOM, metadata, annotations, and notes from external
  egress unless the exact data flow is approved.
- [ ] Prefer local or private-endpoint inference for sensitive workloads.
- [~] Enforce an exact HTTPS application allowlist, value-free decisions, and
  signed audits. Target proxy/firewall/DNS enforcement remains required.
- [x] Present clear administrator controls and dataset-level consent/policy
  checks; never silently enable a provider from a frontend feature flag.
- [ ] Version model outputs and keep them distinguishable from human annotations.

## Operational Reliability

- [x] Add database-aware backend readiness, process liveness, frontend health,
  and Compose health dependencies.
- [ ] Add health probes to deployment manifests and alert on sustained failure.
- [x] Add structured JSON request logs with server-issued correlation IDs and an
  allowlist that excludes bodies, headers, query values, and exception text.
- [ ] Add error tracking that strips sensitive request bodies and metadata.
- [x] Replace process-local login and expensive-route limits with shared,
  direct-peer Redis enforcement for multi-instance production.
- [ ] Add per-user and per-organization quotas after product tiers, service
  accounts, and trusted-proxy identity rules are approved.
- [ ] Add database connection-pool settings, statement timeouts, and slow-query
  visibility.
- [x] Define migration preflight, backup/restore rehearsal, forward deployment,
  and rollback procedures for PostgreSQL in `POSTGRES_MIGRATION_RUNBOOK.md`.
- [x] Remove automatic demo seeding from production startup; development seeding
  remains explicit through `SEED_DEMO_DATA=true`.
- [~] Pin and scan runtime images, run containers as non-root, and use read-only
  filesystems where possible. CI now scans backend/frontend images at the
  high/critical gate, the backend image upgrades vulnerable packaging tools, and
  the frontend runtime updates nginx/Alpine packages during build; non-root
  users, read-only filesystems, and digest-pinned base images remain P1 work.
- [x] Add repository operator runbooks for deploy, rollback, degraded storage,
  database/Redis outage, key compromise, and security incident. Redis is only
  the rate-limit store today; any future general queue requires its own pause,
  replay, idempotency, and dead-letter procedure. Target commands/owners and
  exercise evidence remain external gates.

## Implementation Sequence

1. [x] Establish liveness/readiness and verify Compose startup.
2. [x] Separate development and production configuration; production startup
   rejects demo seeding, development database defaults, missing/weak token
   secrets, and implicit CORS origins.
3. [x] Document and test the PostgreSQL migration/rollback procedure with an
   isolated upgrade/downgrade/upgrade cycle in CI.
4. [x] Add structured request logging, request IDs, and redaction. Error
   tracking remains a separate controlled integration.
5. [x] Add database-backed expiring sessions, logout revocation, exact CORS,
   HttpOnly/SameSite browser cookies, signed CSRF protection, and shared Redis
   rate limits for login, upload, reprocessing, and exports. Target TLS/managed
   Redis evidence, idle timeout, and active-session inventory remain gates.
6. [x] Implement the storage abstraction and private S3 backend with
   tenant-scoped keys, traversal-safe local storage, KMS-encrypted writes,
   original/preview/reprocess/mask integration, and authorized short-lived
   derived-preview URLs. Target-account bucket policy, lifecycle, backup, and
   deletion evidence remains tracked as a deployment gate.
7. [x] Add quarantine plus the versioned `medi-deid-screening-v1` DICOM/NIfTI
   gate, including neutral object names, non-viewable unsafe uploads, safe
   decision evidence, fail-safe legacy migration, and UI intake status.
8. [x] Add append-only, tenant-scoped security audit events with integrity
   hashes and database mutation guards. WORM export remains a production gate.
9. [x] Add immutable dataset releases and approved annotation revision
   manifests. Target S3, retained artifact/WORM, and retention gates remain in
   `DATASET_RELEASE_PLAN.md`.
10. [x] Complete the repository boundary for encrypted recovery drills,
    versioned retention, legal hold, source withdrawal, two-person project/scan
    deletion, every-version purge, and verified receipts. Target infrastructure,
    organization deletion, and policy approvals remain in
    `DATA_LIFECYCLE_RECOVERY_PLAN.md`. The drill requires a sustained queryable
    PostgreSQL state before starting so bootstrap restarts cannot produce a
    false-ready CI race.
11. [x] Complete the repository boundary for external-AI egress denial,
    approved-provider and dataset-flow governance, and value-free decisions.
12. [~] Repository boundary complete: versioned processing/DPIA evidence and
    governed privacy-request workflows are implemented and locally verified.
    Target controller/processor records, identity/case tooling, operator
    exercises, and legal approval remain deployment gates.
13. [x] Complete the P0 production-readiness dependency and supply-chain
    security baseline without inventing target, operator, integration, or legal
    evidence.
14. [x] Add privacy-safe operator runbooks for security incidents, degraded
    storage/database/Redis, key compromise, deploy, and rollback, plus a CI
    structure/link verifier. Target contacts, commands, thresholds, legal
    decisions, and exercises remain deployment gates.
15. [ ] Add session idle expiry and administrator-visible active-session
    inventory/revocation without exposing raw session credentials.

Current repository increment complete: shared rate enforcement and secure
browser-session transport are evidenced in `SESSION_AND_RATE_LIMIT_PLAN.md`.
Current repository increment complete: immutable dataset releases and
annotation manifests are evidenced in `DATASET_RELEASE_PLAN.md`.
Current repository increment complete: backup/restore automation plus
retention, legal-hold, source-withdrawal, and verified project/scan deletion are
evidenced in `DATA_LIFECYCLE_RECOVERY_PLAN.md`.
Current repository increment complete: external-AI egress denial and approved-
provider/data-flow governance are evidenced in
`EXTERNAL_AI_GOVERNANCE_PLAN.md`. Current repository increment complete:
processing/DPIA evidence and privacy-request governance are evidenced in
`PRIVACY_OPERATIONS_PLAN.md`. Current repository increment complete: the Phase
4 production-readiness inventory and P0 dependency/supply-chain security
baseline are evidenced in `PRODUCTION_READINESS_REVIEW.md`.
Current repository increment complete: the incident, degraded-service,
key-compromise, deployment, and rollback package is indexed in
`OPERATOR_RUNBOOKS.md` and structurally verified in CI.

## Phase 4 Exit Criteria

- [x] Production configuration fails closed on development database/secret
  defaults, missing or reused signing/reference keys, demo seeding, insecure
  cookies, memory-only rate limits, non-TLS Redis, local storage, and non-KMS S3.
- [x] PostgreSQL migrations, encrypted disposable backup/restore, and rollback
  are rehearsed. Target managed-backup evidence remains a gate above.
- [ ] Private encrypted storage and tenant-safe access are implemented.
- [ ] Health, logs, alerts, error tracking, and rate limits are operational.
- [x] Supported DICOM/NIfTI intake is quarantined until the versioned v1
  screening checks complete. Full pixel anonymization validation remains a
  separate production gate above.
- [x] Application/database audit records are immutable and dataset releases are
  reproducible. Independent WORM retention remains an explicit gate above.
- [~] Retention/deletion and application-level external-AI egress policies are
  enforceable; target backup/operator and network proxy/firewall evidence
  remains required.
- [ ] Required privacy, security, and legal evidence is approved for the target
  data classification.

Repository privacy workflows are implemented, but this exit gate remains open
until the target records, DPIA/agreements, identity/case tooling, delivery and
rights-execution procedures, and legal/privacy approvals have real evidence.
