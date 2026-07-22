# Production Readiness Review

Status: active on 2026-07-16; P0 supply-chain remediation completed on
2026-07-22. The remaining Phase 4 gates are classified below.

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
| Sessions | Idle expiry and administrator-visible active-session inventory | Repository + organization | Absolute expiry/revocation exists; approved idle duration and new inventory/revocation APIs remain. |
| Authorization | Project-level membership if required and exhaustive object-route authorization coverage | Repository + organization | Tenant/role tests exist. First decide whether same-organization project isolation is a product requirement, then implement it; expand the route matrix independently. |
| SSO/MFA | Approved SSO and MFA for sensitive-data deployments | Integration + organization | Do not add a provider until tenant, assurance, recovery, and contract requirements are approved. |
| Shared rate limits | Authenticated, encrypted, highly available Redis with failover/alert evidence | Deployment | Application fail-closed Redis enforcement exists; target service evidence remains. |
| Audit context | Trusted-proxy-derived network context and an approved privacy retention rule | Organization + repository | Raw IP/user-agent storage remains intentionally absent until both policies exist. |
| Independent audit retention | Append-only/WORM export, integrity monitoring, retention, and alerting | Integration + deployment | Database immutability exists; independent retention still requires a target sink and operator. |
| Annotation history | Replace cascade removal with retained tombstones or references | Repository | P1 repository task before claiming annotation-history immutability. |
| Private objects | Retained private export artifacts and deleted-data tombstones | Repository + deployment | Original/preview/mask storage is tenant-scoped; retained export/tombstone semantics and target S3 evidence remain. |
| Recovery | Automated managed backups, separate credentials, failure alerts, and signed target drills | Deployment + organization | CI restore drills are evidence of repository behavior, not evidence of target backup operations. |
| Deletion | Organization-wide execution plus queue/cache/export/backup enumeration | Repository + deployment | Project/scan deletion and receipts exist; organization scope and target-service propagation remain. |
| Privacy operations | Approved roles/lawful bases, Article 9 conditions, ROPA, DPIA, contracts/transfers, identity/case tooling, secure delivery, and rights exercises | Organization + integration + deployment | Medi stores controlled references and workflows only. Actual approvals, identity proof, correspondence, and delivered data remain outside the repository. |
| Incident response | Breach assessment, notification ownership, evidence preservation, and service-specific response runbooks | Organization + repository | P0/P1 runbook work can define safe mechanics; named people, legal deadlines, and escalation contacts require target approval. |
| External AI | Local/private inference preference and proxy/firewall/DNS enforcement | Deployment + integration | Default application egress is denied. No provider or patient-data flow may be inferred from a feature flag. |
| Model outputs | Version outputs and distinguish them from human annotations | Repository | Deferred until an approved inference path exists; the schema must precede actual model output ingestion. |
| Reliability | Deployment probes/alerts and privacy-safe error tracking | Deployment + integration + repository | Local/Compose health and safe request logs exist; target alert and error-provider evidence remains. |
| Capacity | Per-user/per-organization quotas | Organization + repository | Implement after tier, service-account, and trusted identity rules are approved. |
| Database runtime | Pool bounds, acquisition timeout, statement timeout, and slow-query visibility | Repository + deployment | P1 repository task; target sizing and alert thresholds remain deployment evidence. |
| Containers | Pinned/scanned images, non-root users, and read-only filesystems where feasible | Repository | Scanning begins in P0; user/filesystem hardening is a separate P1 change requiring writable-path tests. |
| Operations | Deploy, rollback, degraded storage, database/Redis outage, key compromise, and security-incident runbooks | Repository + organization | P1 repository package; real contacts and service commands must be supplied for the target. |

## Prioritized Repository Backlog

1. **P0 complete:** upgrade vulnerable backend/frontend dependencies, preserve
   behavior through the test/build suite, add secret/dependency/container scans
   to CI, and pin GitHub Actions to immutable commits.
2. **P0/P1 next:** add the privacy-safe security-incident and degraded-service
   operator runbooks without inventing target contacts or legal decisions.
3. **P1:** add session idle expiry plus active-session inventory and revocation.
4. **P1:** add bounded database pools, acquisition/statement timeouts, and
   privacy-safe slow-query signals.
5. **P1:** run application containers as non-root and make filesystems read-only
   except for explicitly mounted writable paths.
6. **P1:** close the object-authorization test matrix and annotation-history
   tombstone gap.
7. **P2:** address organization deletion, retained export artifacts, quotas,
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

- Current Compose database, Redis, backend, and frontend were healthy before
  this review; backend readiness reported the database reachable, the frontend
  returned HTTP 200, and PostgreSQL was at `20260716_0013`.
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
  requiring a major viewer upgrade; Gitleaks scanned 33 commits with no leaks;
  Trivy found zero high/critical vulnerabilities in the rebuilt backend and
  frontend images.

## Primary References

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj).
- [EDPB data-subject rights](https://www.edpb.europa.eu/topics/key-gdpr-concepts/data-subject-rights_en).
- [European Commission DPIA guidance](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations/when-data-protection-impact-assessment-dpia-required_en).
- [GitHub Actions secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).
