# External AI Governance Plan

Status: repository implementation and local verification complete on
2026-07-16; pull-request checks remain pending.

This increment establishes a deny-by-default repository boundary before any
external model integration exists. It does not approve a real provider,
contract, transfer, medical purpose, or patient-data use. Tests use synthetic
identifiers and exact environment placeholders; no credentials or medical
payloads are sent outside the application.

## Repository Controls

- [x] Keep external AI disabled by default in settings, examples, Compose, and
  production unless an exact HTTPS gateway origin is explicitly allowlisted.
- [x] Store append-only, tenant-scoped provider approvals with exact provider,
  model/version, purpose, region, allowed data classes, retention/training
  terms, subprocessors, transfer mechanism, contract owner, and approval ID.
- [x] Store append-only project-level data-flow approvals pinned to an exact
  provider approval; require a second administrator for revocation.
- [x] Permanently prohibit raw DICOM, direct identifiers, raw DICOM metadata,
  and free-text clinical notes from this repository's external-AI boundary.
- [x] Deny authorization unless the global feature gate, deployment allowlist,
  active provider, active project flow, exact purpose/data classes, project
  lifecycle, expiry, and de-identification checks all pass.
- [x] Record every authorization decision as value-free append-only evidence
  and a signed security-audit event; never persist prompts, pixels, annotations,
  filenames, patient identifiers, credentials, or response content.
- [x] Expose administrator-only status, registry, flow, revoke, and dry-run
  decision controls. This increment must implement no provider network call.
- [x] Add a static CI policy that rejects ungoverned HTTP/vendor-AI clients in
  backend runtime code.

## Verification Evidence

- [x] Focused governance, configuration, audit, tenant, and policy tests pass.
- [x] Full backend tests pass (124 tests) and the frontend production build
  passes (675 modules) on 2026-07-16.
- [x] Fresh SQLite migration and PostgreSQL upgrade/rollback rehearsals pass at
  `20260716_0012`; encrypted recovery also restores at that revision.
- [x] Static egress policy and infrastructure lint pass.
- [x] Rebuilt Compose services are healthy with external AI disabled and a live
  dry-run decision is denied without making a network call.
- [ ] GitHub pull-request checks pass before merge.

## Deployment Gates

- [ ] Legal/privacy/security approve the provider contract, purpose, data
  classes, controller/processor roles, Article 9 condition, DPIA, retention,
  subprocessors, locations, and transfer mechanism.
- [ ] Deploy and verify a network egress proxy/firewall that allows only the
  approved gateway origin and blocks direct provider access and DNS bypass.
- [ ] Validate provider zero-training/retention behavior, private networking,
  regional processing, incident obligations, deletion evidence, and key
  management in the target account.
- [ ] Add a separately reviewed provider adapter, output versioning, human/AI
  provenance, monitoring, and signed target-environment test evidence before
  enabling a real call.

## Primary References

- [GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj), including
  health data, processor contracts, security, and international transfers.
- [EU Artificial Intelligence Act official text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj).
- [EDPB Guidelines 05/2021 on Chapter V transfers](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052021-interplay-between-application-article-3_en).

This plan is an engineering control record, not legal advice or provider
approval.

The live smoke proof stores only clearly marked `SYNTHETIC-QA-*` approval
references, stable IDs, controlled classes, and a denied decision. It does not
represent a real provider or legal approval.
