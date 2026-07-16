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

## Implementation

- [x] Add validated cookie, CSRF, and rate-limit configuration.
- [x] Add cookie session issuance, resolution, revocation, and CSRF middleware.
- [x] Add atomic Redis rate limiting with a development/test memory fallback.
- [x] Add Redis to the local production-like Compose stack.
- [x] Convert the frontend to credentialed cookies and in-memory CSRF state.
- [x] Add backend and frontend regression coverage.

## Verification Evidence

- [x] All 102 backend tests pass.
- [x] Frontend production build passes and contains no `medi_token` storage.
- [x] PostgreSQL migration upgrade/downgrade rehearsal passes at
  `20260716_0009`.
- [x] Infrastructure templates/configuration lint successfully.
- [x] Rebuilt Compose services are healthy, use Redis, and pass live cookie,
  CSRF-rejection, logout-revocation, and rate-limit smoke tests.

## Remaining Deployment Gates

- [ ] Terminate TLS and verify production `Secure` cookies at the real ingress.
- [ ] Provision authenticated, encrypted, highly available managed Redis and
  exercise outage alerts/failover.
- [ ] Approve trusted-proxy address handling, session idle timeout, active
  session inventory, and forced organization-wide revocation policy.
