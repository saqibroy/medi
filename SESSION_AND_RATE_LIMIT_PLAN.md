# Session And Shared Rate-Limit Plan

Status: complete for the repository-controlled increment. Target-environment
deployment gates remain open below.

This increment removes browser-accessible bearer tokens and replaces the
single-process rate-limit baseline with a production-safe shared backend. It
does not claim that TLS ingress, managed Redis, or a production deployment has
been verified until target-environment evidence exists.

## Security Requirements

- [x] Store the opaque session token only in an `HttpOnly`, `SameSite` cookie;
  require `Secure` and the `__Host-` prefix in production.
- [x] Never return the raw session token in API JSON or persist it in browser
  local/session storage.
- [x] Require a signed, session-bound double-submit token for cookie-authenticated
  state changes, including logout; use constant-time comparisons.
- [x] Permit explicit bearer authentication for non-browser API compatibility
  without weakening cookie-authenticated CSRF enforcement.
- [x] Use a shared Redis rate-limit backend in production, hash network
  identities before creating keys, and fail closed when the backend is down.
- [x] Do not trust forwarded client-address headers until an ingress proxy trust
  policy is explicitly configured.
- [x] Require encrypted Redis transport for production connections outside a
  private same-host boundary.
- [x] Enforce sliding idle expiry without extending the absolute session limit;
  require an explicit production idle duration.
- [x] Expose organization-scoped active-session inventory and revocation only
  to administrators, with no token, network-address, or user-agent data.

## Implementation

- [x] Add validated cookie, CSRF, and rate-limit configuration.
- [x] Add cookie session issuance, resolution, revocation, and CSRF middleware.
- [x] Add atomic Redis rate limiting with a development/test memory fallback.
- [x] Add Redis to the local production-like Compose stack.
- [x] Convert the frontend to credentialed cookies and in-memory CSRF state.
- [x] Add backend and frontend regression coverage.
- [x] Add last-activity migration, idle enforcement, administrator inventory/
  revocation APIs, audit events, and an admin UI panel.

## Verification Evidence

- [x] All 136 backend tests pass, including idle-expiry, tenant isolation,
  administrator authorization, credential minimization, revocation, and audit
  coverage.
- [x] Frontend production build passes and contains no `medi_token` storage.
- [x] PostgreSQL migration upgrade/downgrade/upgrade rehearsal passes at
  `20260722_0014`.
- [x] Infrastructure templates/configuration lint successfully.
- [x] Rebuilt Compose services are healthy, use Redis, and pass live cookie,
  CSRF-rejection, logout-revocation, rate-limit, administrator session-list,
  role-denial, and revoked-session rejection smoke tests.

## Remaining Deployment Gates

- [ ] Terminate TLS and verify production `Secure` cookies at the real ingress.
- [ ] Provision authenticated, encrypted, highly available managed Redis and
  exercise outage alerts/failover.
- [ ] Approve trusted-proxy address handling, the target production idle
  duration, and organization-shutdown operator policy. The repository now
  revokes every tenant session before governed organization purge; approval and
  target exercise evidence remain in `ORGANIZATION_DELETION_PLAN.md`.
