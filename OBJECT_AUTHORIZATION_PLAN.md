# Object Authorization Matrix

Status: repository boundary complete on 2026-07-22

This tracker records the Phase 4 object-level authorization increment. It does
not decide whether users in the same organization need project memberships;
that remains a product and organization policy decision.

## Implemented Controls

- [x] Inventory all 90 API routes and assign each one an explicit public,
  authenticated, administrator, annotator, or reviewer policy.
- [x] Make the route-policy test fail closed when a route is added without a
  matching matrix entry or with the wrong direct authentication dependency.
- [x] Exercise every parameterized API path with an object owned by another
  organization and require an opaque `404` response.
- [x] Prove collection routes exclude outside projects, scans, annotations,
  users, sessions, audit rows, governance records, and external-AI records.
- [x] Prove scan query filters cannot expose another organization's
  annotations.
- [x] Reject cross-organization IDs supplied through scan, annotation,
  retention/deletion, privacy, and external-AI request bodies.
- [x] Scope annotation project, label, and assignee references before
  consistency validation so missing and outside objects are indistinguishable.
- [x] Prevent an annotation update from reparenting the annotation away from
  its scan's project.
- [x] Keep same-organization consistency errors as validation errors; the
  matrix does not introduce unapproved project-membership semantics.

## Verification Evidence

Completed locally on 2026-07-22 using synthetic, two-organization fixtures:

- 151 backend tests passed, including the route inventory, all parameterized
  path probes, collection isolation, request-body references, and annotation
  reparenting regression coverage.
- The frontend TypeScript/Vite production build passed.
- Backend compilation, external-AI egress policy verification, operator-runbook
  verification, and `git diff --check` passed.
- The rebuilt Compose stack reported healthy database, Redis, backend, and
  frontend services; backend live/readiness, frontend HTTP `200`, and the
  container-hardening runtime verifier passed.

The 2026-07-23 retained-release increment extends the fail-closed inventory from
88 to 90 routes. Artifact materialization is administrator-only, artifact
download is authenticated, and both return opaque `404` across organizations.
The complete backend suite now passes all 155 tests.

Target identity-provider policy, SSO/MFA, and any same-organization project
membership requirement remain outside this completed repository increment.

## Follow-on

The annotation-history tombstone and retained-release-artifact tasks are now
complete and evidenced in `ANNOTATION_HISTORY_TOMBSTONE_PLAN.md` and
`RETAINED_RELEASE_ARTIFACT_PLAN.md`. The artifact materialization/download
routes are included in the fail-closed matrix and cross-tenant probes.
Organization-wide governed deletion and revocation is the next repository
task.
