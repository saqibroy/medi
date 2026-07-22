# Key And Credential Compromise Runbook

Status: repository response paths defined; target secret manager, identity/KMS
commands, owners, recovery contacts, and exercise evidence remain deployment
inputs.

Activate this runbook for suspected disclosure, unauthorized use, accidental
logging, repository/image inclusion, weak custody, or loss of control over a
secret, password, token, workload identity, signing key, or encryption key.
Read [OPERATOR_RUNBOOKS.md](OPERATOR_RUNBOOKS.md) and
[SECURITY_INCIDENT_RUNBOOK.md](SECURITY_INCIDENT_RUNBOOK.md) first.

## Immediate Actions

1. Open a restricted security incident and record the suspected credential
   type, owner, environment, first/last possible exposure times, and detection
   source. Never copy the value into the record.
2. Disable or revoke the affected credential/identity at its trusted control
   plane when this will not destroy the only recovery path. For KMS, database,
   or break-glass access, coordinate containment with the service owner.
3. Block new releases and deletion operations while scope is unknown.
4. Preserve access-log, secret-version, workload, release, and request/audit ID
   references. Search by fingerprints or version IDs, never by printing values.
5. Determine every consumer and environment before issuing a replacement.
   Do not leave an old consumer silently retrying a revoked secret.

## Medi Secret Inventory And Effects

| Credential or key | Compromise impact | Rotation/recovery boundary |
| --- | --- | --- |
| `TOKEN_SECRET` | Session-token digest protection and rate-limit identity hashing | Replace through the secret manager and restart all API instances together; expect all existing sessions to become invalid and require reauthentication |
| `CSRF_SECRET` | Browser CSRF token signatures | Replace and restart all API instances together; existing CSRF cookies/tokens stop validating and must be refreshed |
| `AUDIT_SIGNING_KEY` | Integrity hashes for append-only audit events | Do not simply overwrite: current rows have no key-version field, so historical verification needs the retired key under restricted evidence custody or a reviewed versioned-key migration |
| `PRIVACY_REFERENCE_KEY` | Stable digests for external subject references | Do not simply overwrite: existing requests cannot be correlated from the original reference with a new key; implement a reviewed versioned-key/migration strategy first |
| `DATABASE_URL` credential | Database read/write access | Revoke/replace at the database control plane, update secret manager, restart consumers, verify least privilege and audit continuity |
| `RATE_LIMIT_REDIS_URL` credential | Shared limiter access | Revoke/replace, restore encrypted Redis connectivity, restart consumers, and keep rate-limited routes fail-closed until verified |
| Storage workload identity | Private object and KMS use within granted scope | Disable principal, review access events/policy changes, issue least-privilege replacement, verify tenant boundary and storage controls |
| `SCAN_STORAGE_KMS_KEY_ID` / KMS authority | Availability/confidentiality of encrypted objects | Follow approved KMS incident procedure; do not schedule deletion, disable the only decrypt path, or re-encrypt production data without recovery proof |
| CI/GitHub/deployment credential | Code, artifact, workflow, or release authority | Revoke at source, review commits/runs/artifacts/deployments, replace with least privilege, and rebuild from reviewed source |

`EXTERNAL_AI_ALLOWED_ORIGINS` is configuration, not a credential. If an egress
gateway/provider credential is compromised, keep `EXTERNAL_AI_ENABLED=false`,
disable the external principal/network path, and investigate under the approved
provider contract without transmitting samples.

## Rotation Sequence

1. Map producers, consumers, secret versions, workloads, and restart order.
2. Decide whether the service supports overlapping old/new versions. Use overlap
   only when the target design is approved and does not prolong attacker access.
3. Create a replacement in the secret manager; never pass it in shell history,
   command-line arguments, Git, images, frontend variables, or tickets.
4. Update consumers using the target rollout mechanism and verify they read the
   intended secret version.
5. Revoke the old version, restart stale consumers, and confirm no old-version
   access remains.
6. Verify health, authentication/authorization, rate limits, storage/KMS,
   tenant isolation, and new audit-event creation as applicable.
7. Record version IDs, timestamps, operators, approvals, invalidated sessions,
   verification results, and residual work without recording secret values.

## Audit And Privacy Key Limitation

The current schema stores an integrity hash or subject-reference digest but **no key identifier**. Therefore:

- an `AUDIT_SIGNING_KEY` replacement makes one current-key verifier unable to
  verify historical rows signed by the retired key;
- a `PRIVACY_REFERENCE_KEY` replacement changes the digest of the same external
  reference and can break request correlation;
- retaining a compromised key in normal runtime is unsafe, while destroying it
  can destroy verification/correlation capability.

Contain the runtime, preserve a protected evidence snapshot and key-custody
record, and require a reviewed schema/application migration for versioned keys
before routine rotation is claimed. This is an explicit production-readiness
gap, not a reason to expose key material or delay incident containment.

## KMS Or Storage Identity Compromise

1. Disable the affected workload identity/policy path, preserving control-plane
   evidence and an independent recovery identity.
2. Check for policy, grant, alias, deletion-schedule, public-access, encryption,
   versioning, lifecycle, and object-access changes using safe event IDs.
3. Cancel unauthorized destructive key actions through the approved owner. Do
   not improvise provider commands from this repository.
4. Verify backup/vault keys and credentials are isolated from the affected
   identity.
5. Recover/test with synthetic data in an isolated prefix/account before any
   re-encryption or production cutover. Follow
   [STORAGE_OPERATIONS_RUNBOOK.md](STORAGE_OPERATIONS_RUNBOOK.md).

## Closure And Exercise

Close only after the old authority is revoked, all consumers use the approved
replacement, logs show no continuing unauthorized use, dependent sessions or
artifacts are invalidated/rebuilt, and privacy/legal owners complete any breach
assessment. Rehearse session-secret, database/Redis credential, workload
identity, and KMS scenarios with synthetic data; retain elapsed times and
corrective actions.
