# Container Hardening Plan

Status: repository application-container controls complete on 2026-07-22;
target orchestrator, immutable image-digest, policy, and rollout evidence remain
deployment gates.

This plan covers the FastAPI backend and Nginx frontend application images. The
Compose PostgreSQL and Redis services use upstream development images and are
not a substitute for approved managed production services.

## Implemented Repository Boundary

| Control | Backend | Frontend |
| --- | --- | --- |
| Runtime identity | Fixed UID/GID `10001:10001` | Nginx UID/GID `101:101` |
| Root filesystem | Read-only | Read-only |
| Linux capabilities | All dropped | All dropped |
| Privilege escalation | `no-new-privileges` | `no-new-privileges` |
| Temporary storage | 64 MiB `/tmp` tmpfs | 16 MiB `/tmp` tmpfs |
| Persistent writable path | `scan_storage` volume only | None |
| Listening port | Unprivileged `8000` | Unprivileged `8080` |

Both temporary filesystems are `nodev`, `nosuid`, and `noexec`. The backend
uses `/tmp` for bounded imaging preview work and runtime caches. Nginx places
its PID and request/proxy temporary files under `/tmp`; its application assets
and configuration remain read-only. The backend scan volume is still required
for the development-only local storage implementation. Production continues to
require the private KMS-encrypted S3 boundary defined elsewhere in this
repository.

## Automated Evidence

`python3 scripts/verify_container_hardening.py` inspects the running Compose
containers and fails unless it can prove:

- both application processes have numeric non-root UIDs;
- both root filesystems are read-only, all capabilities are dropped, and
  privilege escalation is disabled;
- `/tmp` is the only tmpfs and carries the required mount restrictions;
- the backend scan volume is the only persistent writable application mount;
- writes to application/root paths fail while required `/tmp` and scan-volume
  writes succeed; and
- backend liveness/readiness and frontend health return HTTP 200.

CI rebuilds and starts the complete Compose stack, runs this verifier, prints
only bounded service logs on failure, and destroys its disposable volumes. The
probe creates only fixed-name, empty files and immediately removes them. It
does not inspect or print stored medical-image data.

## Existing Local Volume Ownership

New `scan_storage` volumes inherit UID/GID `10001:10001` from the backend image.
An existing development volume created by an older root-running image may need
a one-time ownership migration before the hardened backend can start. First
back up and identify the exact **local development** volume. For this Compose
project only, the migration used is:

```bash
docker run --rm --user 0:0 \
  --volume medi_scan_storage:/storage \
  medi-backend chown -R 10001:10001 /storage
```

Do not copy this command into a production procedure or guess a target volume
name. A production rollout must use the platform's approved ownership/init
mechanism, least-privilege change identity, backup, change record, and rollback
plan. Do not print filenames or object contents as evidence.

## Deployment Gates

Repository and local CI evidence do not prove the target workload is hardened.
Before sensitive-data use, the deployment owner must provide:

- immutable backend/frontend image digests and admission rules that reject
  root identities, writable roots, added capabilities, and privilege escalation;
- target workload definitions with the same or stricter writable-path and
  temporary-storage bounds;
- approved seccomp/AppArmor or equivalent runtime policy, resource limits,
  workload identity, network policy, and image-signing/provenance controls;
- a synthetic rollout and rollback exercise proving storage ownership,
  uploads/previews, probes, logs, and restart behavior; and
- monitoring/alert evidence for policy violations and repeated write or
  permission failures.

These controls reduce container privilege and persistence opportunities. They
do not provide legal approval, validate anonymization, or make the application
automatically GDPR compliant.
