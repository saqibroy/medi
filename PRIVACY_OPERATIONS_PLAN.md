# Privacy Operations Plan

Status: repository implementation, local verification, and pull-request checks
complete on 2026-07-16; merge/main verification and target deployment evidence
remain.

This increment creates data-minimized operational evidence for privacy review
and data-subject requests. It does not decide lawful basis, approve a DPIA,
identify a person, or make Medi legally compliant by itself. Deployment owners
must supply approved references and keep identity proof, request correspondence,
and delivered personal-data copies in a separately approved case-management
system.

## Repository Boundary

- [x] Store immutable, monotonic processing-activity versions covering the
  controller/processor role, purpose, lawful basis, Article 9 condition, data
  subject/data/recipient categories, processors, locations, transfers,
  retention-policy snapshot, security controls, and approval references.
- [x] Record DPIA screening/outcome and evidence references without storing the
  assessment narrative; block an activity from an active status when prior
  consultation is recorded as required.
- [x] Keep processing records and their lifecycle events append-only in both the
  ORM and database.
- [x] Provide admin-only privacy request workflows for access, rectification,
  restriction, objection, portability, and erasure.
- [x] Convert the external subject reference immediately to a keyed digest;
  never persist or return the raw reference and never place it in logs/audits.
- [x] Require a second administrator to record identity verification before a
  request can be accepted, denied on substantive grounds, or fulfilled.
- [x] Track a one-calendar-month response target, controlled extension evidence,
  and overdue state without claiming that software replaces legal review.
- [x] Keep request/event fields controlled and value-free. Personal-data copies,
  identity documents, correspondence, and free-text explanations stay outside
  Medi.
- [x] Require an executed, same-tenant/same-scope governed deletion request
  before an erasure request can be marked fulfilled.
- [x] Sign audit events for every governance operation using stable IDs and
  controlled outcome fields only.

## Product And Verification

- [x] Add administrator UI for processing evidence and privacy-request status.
- [x] Add tenant, role, versioning, workflow, keyed-digest, deadline, erasure
  handoff, audit-minimization, and ORM/database immutability tests.
- [x] Pass the full backend suite and frontend production build.
- [x] Pass fresh SQLite and PostgreSQL migration rehearsals, encrypted recovery,
  infrastructure linting, and rebuilt Compose health checks.
- [x] Record a live synthetic-only governance smoke test; do not enter a real
  patient, participant, staff, or customer identifier.
- [~] Pull-request #14 checks passed; post-merge `main` verification remains.

Local evidence:

- 129 backend tests passed, including role/tenant isolation, processing-record
  versioning/revocation, DPIA consistency, subject-reference digesting,
  two-person identity verification, deadline extension, erasure linkage,
  audit minimization/integrity, and ORM/database append-only enforcement.
- The frontend production build passed with 677 transformed modules.
- Fresh SQLite upgrade and `0013 -> 0012 -> 0013` passed; PostgreSQL completed
  the full upgrade-to-head, downgrade-to-base, and second upgrade at
  `20260716_0013`.
- The encrypted PostgreSQL/synthetic-object recovery drill restored migration
  `20260716_0013`; the CloudFormation template passed `cfn-lint 1.53.0`, and the
  external-AI static egress policy remained green.
- The recovery drill now requires three consecutive successful SQL queries
  before destructive rehearsal steps, preventing the transient PostgreSQL
  bootstrap shutdown from being mistaken for stable readiness in CI.
- Rebuilt database, Redis, backend, and frontend containers are healthy. Backend
  readiness reports the database reachable and the frontend returns HTTP 200.
- An authenticated synthetic-only smoke created processing/request evidence,
  returned only a `sha256` subject token, reported an on-time request, and
  produced a signed audit event. Two-person and deletion execution paths stayed
  isolated to automated tests.
- GitHub pull-request #14 passed backend, frontend, PostgreSQL migration,
  encrypted recovery, and infrastructure jobs before merge.

## Remaining Deployment Gates

- [ ] Obtain legal/privacy approval for controller, processor, joint-controller,
  lawful-basis, Article 9, research-exemption, and rights-applicability decisions.
- [ ] Complete and approve target processing records, DPIAs, processor terms,
  subprocessor inventory, data-location evidence, and transfer safeguards.
- [ ] Integrate an approved identity-verification and privacy case-management
  system; define secure delivery, correction, restriction, and objection
  operator procedures.
- [ ] Approve request ownership, calendar/deadline rules, exception handling,
  supervisory-authority consultation, and evidence retention.
- [ ] Exercise access, correction, restriction, objection, portability, and
  erasure end to end with synthetic evidence in the target environment.

## Primary References

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj), especially
  Articles 5, 9, 12, 15-21, 25, 30, 32, and 35.
- [EDPB data-subject rights overview](https://www.edpb.europa.eu/topics/key-gdpr-concepts/data-subject-rights_en).
- [European Commission DPIA guidance](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/when-data-protection-impact-assessment-dpia-required_en).
