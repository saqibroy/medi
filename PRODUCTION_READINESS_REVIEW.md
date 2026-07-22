# Production Readiness Review

Status: active on 2026-07-16; P0 supply-chain remediation and the repository
operator-runbook package, repository session controls, database-runtime
controls, application-container hardening, and the object-authorization matrix
completed on 2026-07-22. The remaining Phase 4 gates are classified below.

This review prevents two unsafe shortcuts: treating unfinished engineering as
somebody else's approval problem, or inventing legal/deployment evidence that
does not exist. A repository control is complete only when it is implemented
and tested. A target gate is complete only when the real operator, environment,
contract, or approver supplies verifiable evidence.

## Responsibility Classes

- **Repository**: code, tests, configuration validation, CI, or runbooks that
  can be completed in this repository.
- **Deployment**: evidence from the real ingress, cloud account, managed
  database/Redis, object store, keys, monitoring, backup vault, or network.
- **Organization**: a decision or approval by the controller/processor,
  privacy/DPO, legal, security, clinical/research, or operations owner.
- **Integration**: an approved external identity, case-management, SSO,
  monitoring, WORM, egress-control, or inference service.

## Remaining-Gate Inventory

| Area | Remaining evidence or control | Class | Repository disposition |
| --- | --- | --- | --- |
| Image intake | Per-organization `synthetic_only`, `anonymized_only`, or `approved_sensitive` policy | Organization + repository | Add enforcement only after approved policy semantics exist. Until then the product boundary remains synthetic/anonymized research data. |
| De-identification | Validated DICOM rewrite profile, UID pseudonymization, burned-in-text OCR/defacing, and human-review protocol | Repository + organization | Screening/quarantine is implemented; transformation and formal validation remain separate work and must not be claimed as anonymization. |
| Transport | HTTPS ingress redirect and TLS for PostgreSQL, Redis, storage, monitoring, and other service links | Deployment | Production configuration can require secure schemes; the real certificates, endpoints, and ingress tests must come from the target environment. |
| Encryption and keys | Managed encryption for volumes/storage/backups plus ownership, rotation, access logs, and revocation | Deployment + organization | S3/KMS write controls and encrypted disposable drills exist; target KMS and policy evidence remain external. |
| Application secrets | Reject missing, reused, weak, or documented development secrets | Repository | Implemented and tested; the Phase 4 tracker is reconciled in this review. |
| Secret delivery | Load runtime secrets from an approved secret manager | Deployment | No secret values belong in this repository, images, frontend bundles, logs, or samples. |
| Supply chain | Secret, Python, npm, container, and workflow-integrity scanning | Repository | **P0 complete:** known high/critical Python/npm/container findings are remediated, every PR/main run scans secrets/dependencies/images, and GitHub Actions are pinned by immutable commit. Moderate Cornerstone/VTK advisories remain until a planned major viewer upgrade. |
| Sessions | Approved production idle duration and any forced organization-wide revocation policy | Repository + organization | **Repository complete:** sliding idle expiry, explicit production configuration, credential-free administrator inventory, per-session revocation, UI, audit, migration, and tenant tests are implemented. Target owners must approve the duration and any bulk policy. |
| Authorization | Project-level membership if required | Organization + repository | **Repository route matrix complete:** all 88 routes have explicit policies; every parameterized path, collection, query reference, and body reference has cross-tenant coverage. Decide same-organization project isolation separately before implementing membership semantics. |
| SSO/MFA | Approved SSO and MFA for sensitive-data deployments | Integration + organization | Do not add a provider until tenant, assurance, recovery, and contract requirements are approved. |
| Shared rate limits | Authenticated, encrypted, highly available Redis with failover/alert evidence | Deployment | Application fail-closed Redis enforcement exists; target service evidence remains. |
| Audit context | Trusted-proxy-derived network context and an approved privacy retention rule | Organization + repository | Raw IP/user-agent storage remains intentionally absent until both policies exist. |
| Independent audit retention | Append-only/WORM export, integrity monitoring, retention, and alerting | Integration + deployment | Database immutability exists; independent retention still requires a target sink and operator. |
| Annotation history | Replace cascade removal with retained tombstones or references | Repository | P1 repository task before claiming annotation-history immutability. |
| Private objects | Retained private export artifacts and deleted-data tombstones | Repository + deployment | Original/preview/mask storage is tenant-scoped; retained export/tombstone semantics and target S3 evidence remain. |
| Recovery | Automated managed backups, separate credentials, failure alerts, and signed target drills | Deployment + organization | CI restore drills are evidence of repository behavior, not evidence of target backup operations. |
| Deletion | Organization-wide execution plus queue/cache/export/backup enumeration | Repository + deployment | Project/scan deletion and receipts exist; organization scope and target-service propagation remain. |
| Privacy operations | Approved roles/lawful bases, Article 9 conditions, ROPA, DPIA, contracts/transfers, identity/case tooling, secure delivery, and rights exercises | Organization + integration + deployment | Medi stores controlled references and workflows only. Actual approvals, identity proof, correspondence, and delivered data remain outside the repository. |
| Incident response | Breach assessment, notification ownership, evidence preservation, and target exercises | Organization + repository | **Repository complete:** `SECURITY_INCIDENT_RUNBOOK.md` defines safe mechanics and legal handoff. Named people, legal decisions, severity/contact rules, and signed target exercises still require approval. |
| External AI | Local/private inference preference and proxy/firewall/DNS enforcement | Deployment + integration | Default application egress is denied. No provider or patient-data flow may be inferred from a feature flag. |
| Model outputs | Version outputs and distinguish them from human annotations | Repository | Deferred until an approved inference path exists; the schema must precede actual model output ingestion. |
| Reliability | Deployment probes/alerts and privacy-safe error tracking | Deployment + integration + repository | Local/Compose health and safe request logs exist; target alert and error-provider evidence remains. |
| Capacity | Per-user/per-organization quotas | Organization + repository | Implement after tier, service-account, and trusted identity rules are approved. |
| Database runtime | Approved connection budget, replica/worker sizing, thresholds, monitoring, and exercises | Deployment + organization | **Repository complete:** explicit pool/overflow bounds, acquisition/statement timeouts, pre-ping, privacy-safe slow-query signals, configuration validation, and disposable PostgreSQL proofs are implemented. Target sizing and alerts remain external. |
| Containers | Immutable digests, target admission/runtime policy, and rollout evidence | Deployment | **Repository complete:** backend/frontend use fixed non-root UIDs, read-only roots, dropped capabilities, no privilege escalation, restricted tmpfs mounts, and only the backend development storage volume writable. CI proves required and denied writes. Target evidence remains in `CONTAINER_HARDENING_PLAN.md`. |
| Operations | Deploy, rollback, degraded storage, database/Redis outage, key compromise, and security-incident runbooks | Repository + organization | **Repository complete:** `OPERATOR_RUNBOOKS.md` indexes the CI-verified package. Real contacts, provider commands, thresholds, and exercise evidence must be supplied for the target. |

## Prioritized Repository Backlog

1. **P0 complete:** upgrade vulnerable backend/frontend dependencies, preserve
   behavior through the test/build suite, add secret/dependency/container scans
   to CI, and pin GitHub Actions to immutable commits.
2. **P0/P1 complete:** add privacy-safe incident, degraded-service,
   key-compromise, deployment, and rollback runbooks without inventing target
   contacts, provider commands, thresholds, or legal decisions.
3. **P1 complete:** add session idle expiry plus credential-free administrator
   active-session inventory and per-session revocation.
4. **P1 complete:** add bounded database pools, acquisition/statement timeouts,
   pre-ping, and privacy-safe slow-query signals.
5. **P1 complete:** run application containers as non-root with read-only roots,
   dropped capabilities, disabled privilege escalation, and verified writable
   paths.
6. **P1 complete:** close the 88-route object-authorization matrix, including
   every parameterized path plus collection, query, and body references.
7. **P1 next:** replace annotation-history cascade deletion with retained
   tombstones or durable references.
8. **P2:** address organization deletion, retained export artifacts, quotas,
   and model-output lineage when their prerequisite product policies exist.

## What The Deployment Owner Must Eventually Do

Nothing in this section blocks synthetic local development. Before real patient
or pseudonymized data is enabled, the deployment owner must:

1. Appoint the controller/processor, privacy/DPO, legal, security, and
   operations owners and approve the data classification and processing purpose.
2. Complete the real ROPA/DPIA, lawful-basis and Article 9 analysis, agreements,
   retention values, request procedures, incident ownership, and any required
   authority consultation.
3. Provision the approved target services: TLS ingress, managed database and
   Redis, KMS/private object storage, secret manager, backup vault, monitoring,
   WORM audit sink, and any approved identity/case/SSO or AI integration.
4. Execute synthetic target-environment restore, deletion, access-rights,
   outage, key-revocation, and incident exercises; retain signed evidence.
5. Open real-data access only after every applicable Phase 4 exit gate has
   evidence. Until then, use synthetic or properly anonymized samples only.

## Review Evidence

- Current Compose database, Redis, backend, and frontend are healthy; backend
  readiness reports the database reachable, the frontend returns HTTP 200, and
  PostgreSQL is at `20260722_0014`.
- The initial repository-history secret scan covered 33 commits with no leak
  finding.
- The initial Python audit found known advisories in the old FastAPI/Starlette,
  Pillow, multipart, and pytest stack. The P0 change must reduce that result to
  zero known vulnerabilities before completion.
- The production configuration already rejects development database/secret
  defaults, missing/distinct signing keys, demo seeding, insecure cookies,
  memory-only rate limiting, unencrypted Redis URLs, local storage, and
  non-KMS S3 writes.
- P0 completion evidence on 2026-07-22: `pip-audit` reported no known
  backend requirement vulnerabilities; `npm audit --omit=dev
  --audit-level=high` passed with only moderate Cornerstone/VTK advisories
  requiring a major viewer upgrade; the latest Gitleaks run scanned 38 commits
  with no leaks;
  Trivy found zero high/critical vulnerabilities in the rebuilt backend and
  frontend images.
- Operator-runbook completion evidence on 2026-07-22: five documents define a
  target worksheet, safe evidence boundary, incident/privacy handoff,
  PostgreSQL/Redis/storage degradation, key-specific rotation limitations,
  immutable deployment/rollback procedure, and synthetic exercises. The CI
  verifier confirms required sections and local Markdown links; target drills
  and approvals remain external evidence.
- Session-control completion evidence on 2026-07-22: all 136 backend tests pass;
  the frontend production build passes; the PostgreSQL
  upgrade/downgrade/upgrade rehearsal reaches `20260722_0014`; and a rebuilt
  Compose smoke test proves admin-only inventory, credential-minimized response
  fields, per-session revocation, and subsequent `401` rejection of the revoked
  session. Supply-chain checks still report no Python advisories, no secret
  leaks, and zero high/critical image findings; the three moderate viewer-chain
  advisories remain tracked for a deliberate major upgrade.
- Database-runtime completion evidence on 2026-07-22: all 148 backend tests and
  the frontend production build pass; production configuration requires
  explicit bounded values and the supported PostgreSQL driver; the disposable
  PostgreSQL rehearsal proves pool/overflow limits, acquisition timeout,
  effective statement timeout, and synthetic statement cancellation; and the
  rebuilt Compose backend reports the configured `5 + 5` per-process bound,
  five-second acquisition timeout, 30-second statement timeout, and a
  duration-only correlated slow-query event. SQLAlchemy failures return a
  generic `503` without exposing exception content. Target sizing, thresholds,
  alerts, and exercises remain deployment evidence.
- Container-hardening completion evidence on 2026-07-22: the backend runs as
  `10001:10001` and Nginx as `101:101`; both roots are read-only, all
  capabilities are dropped, privilege escalation is disabled, and only
  restricted `/tmp` plus the backend scan volume are writable. The runtime
  verifier passes against both the preserved local stack and a fully disposable
  fresh-volume stack, proving denied application-path writes, required
  temporary/storage writes, and all health endpoints. All 148 backend tests,
  the frontend build, migration/runtime rehearsal, encrypted recovery drill,
  policy/runbook checks, and supply-chain gate pass. Python and rebuilt images
  have no known high/critical findings; the three moderate viewer-chain
  advisories remain tracked. Target admission, runtime, digest, and rollout
  evidence remains external.
- Object-authorization completion evidence on 2026-07-22: all 88 API routes
  have an exact fail-closed authentication/role entry; all parameterized paths,
  collections, scan query references, and request-body references are tested
  with a synthetic second organization and return opaque results. Annotation
  project, label, and assignee references are organization-scoped before
  consistency validation, and annotation updates cannot reparent away from the
  scan. All 151 backend tests, the frontend build, backend compilation, external-
  AI egress check, operator-runbook verifier, and diff check pass. Project
  membership within one organization remains a separate policy decision. The
  rebuilt Compose stack is healthy; live/readiness, frontend HTTP `200`, and
  container-hardening verification pass.

## Primary References

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj).
- [EDPB data-subject rights](https://www.edpb.europa.eu/topics/key-gdpr-concepts/data-subject-rights_en).
- [European Commission DPIA guidance](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/when-data-protection-impact-assessment-dpia-required_en).
- [GitHub Actions secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).
