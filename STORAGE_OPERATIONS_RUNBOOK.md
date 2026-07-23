# Production Storage Operations Runbook

Status: deployable controls implemented; target-account deployment and drills
require an approved AWS account, KMS key, retention schedule, and operators.

This runbook covers Medi's private medical-image object storage. It is not an
authorization to upload identifiable patient data. Use synthetic or approved
anonymized fixtures for deployment and recovery tests.

## Required Approvals Before Deployment

Record these values in the deployment change ticket without placing secrets in
the repository:

- AWS account, region, environment, and globally unique bucket name;
- customer-managed KMS key ARN and reviewed key administrators/users;
- Medi runtime role and the person approving its least-privilege policy;
- current-version retention for quarantine, previews, and exports;
- noncurrent-version retention for originals, masks, metadata, quarantine,
  previews, and exports;
- PostgreSQL and object-storage RPO/RTO;
- backup vault/account, backup operator role, restore operator role, and alert
  destination;
- legal-hold owner and customer-deletion approvers;
- CloudTrail S3 data-event destination and security-monitoring owner.

Retention parameters in the template intentionally have no defaults. Never
copy sample durations from tests into production without legal, privacy,
security, and customer approval.

## Deploy The Control Plane

The CloudFormation template creates a retained bucket, KMS default encryption,
S3 Bucket Keys, versioning, disabled ACLs, full public-access blocking, TLS/KMS
deny policies, required allowlisted data-class tags, tag-specific lifecycle
rules, and a least-privilege runtime managed policy.

```bash
aws cloudformation deploy \
  --template-file infrastructure/aws/medi-private-storage.json \
  --stack-name medi-storage-production \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketName=<approved-bucket-name> \
    KmsKeyArn=<approved-kms-key-arn> \
    QuarantineExpirationDays=<approved-days> \
    PreviewExpirationDays=<approved-days> \
    ExportExpirationDays=<approved-days> \
    NoncurrentVersionExpirationDays=<approved-days>
```

After review, attach the stack's `ApplicationStoragePolicyArn` output to only
the Medi runtime role. The KMS key policy must separately authorize that role;
do not grant wildcard KMS principals. The runtime policy deliberately excludes
`s3:DeleteObjectVersion`, bucket-policy mutation, lifecycle mutation, and KMS
administration.

AWS notes that initial versioning enablement can take time to propagate. Wait
for the stack and versioning control to stabilize before any application write.

## Verify Before Application Access

The verifier performs control-plane reads only. It does not list object keys or
download objects.

```bash
.venv/bin/python scripts/verify_s3_controls.py \
  --bucket <approved-bucket-name> \
  --region <approved-region> \
  --kms-key-arn <approved-kms-key-arn> \
  --quarantine-expiration-days <approved-days> \
  --preview-expiration-days <approved-days> \
  --export-expiration-days <approved-days> \
  --noncurrent-expiration-days <approved-days>
```

Store the JSON output with the change ticket. A nonzero exit blocks deployment.
Also verify separately:

- the runtime role can access only this bucket's `org/*` objects;
- a different tenant cannot receive a signed URL through the Medi API;
- CloudTrail S3 data events reach the approved immutable log destination;
- AWS Config/Security Hub findings for public access, encryption, and TLS are
  clear;
- the KMS key policy, rotation decision, deletion window, and alerts are
  approved;
- the application audit ledger records signed-URL issuance and sensitive reads.

Configure the application only after verification:

```text
SCAN_STORAGE_BACKEND=s3
SCAN_STORAGE_BUCKET=<approved-bucket-name>
SCAN_STORAGE_REGION=<approved-region>
SCAN_STORAGE_SSE=aws:kms
SCAN_STORAGE_KMS_KEY_ID=<approved-kms-key-arn>
```

Use workload identity for AWS credentials. Do not create repository `.env`
credentials or long-lived access keys for containers.

## Lifecycle Semantics

The S3 backend applies `medi-data-class` from trusted object keys:

- `quarantine`: uploads awaiting or failing de-identification;
- `original`: approved or synthetic source volumes;
- `preview`: reproducible derived viewer PNGs;
- `mask`: segmentation-mask objects;
- `metadata`: ingestion/mask metadata objects;
- `export`: generated export artifacts;
- `dataset-release`: retained canonical release manifests;
- `unclassified`: fail-visible category with no destructive lifecycle rule.

Current quarantine, preview, and export versions use separately approved expiry
periods. Current originals, masks, and metadata do not expire automatically.
Noncurrent versions use the separately approved noncurrent period.
`dataset-release` current and noncurrent versions have no automatic expiration;
the control verifier rejects a destructive lifecycle rule for that class.
Approved retention, legal hold, organization deletion, and Object Lock/WORM
replication still require target policy and evidence. Any future tombstone class
requires its own explicit policy and tests.

## Backup And Restore Drill

S3 versioning is a recovery layer, not an independent backup. Before production
data is accepted, configure AWS Backup or approved cross-account replication
with a separate vault/key, credentials, failure alerts, and retention policy.

The repository provides a disposable proof of the recovery sequence:

```bash
bash scripts/verify_backup_restore_drill.sh
```

It creates only guarded `medi_recovery_*` databases, waits for database
readiness, migrates and seeds the source with synthetic data, encrypts a
custom-format PostgreSQL dump and a
synthetic private-object tree with an ephemeral restricted key, restores both
into isolated targets, verifies Alembic revision, selected table counts, and
object checksum, emits a value-free JSON receipt, and cleans up. CI runs the
same drill. This proves the automation path, not target backup-vault isolation,
approved retention, alerts, achieved production RPO/RTO, or operator sign-off.

At least quarterly and after material storage changes:

1. Open a restore ticket and record the approved RPO/RTO and operators.
2. Upload a synthetic test volume through Medi and record only its Medi IDs,
   object checksum, version ID, data-class tag, and timestamps.
3. Simulate the approved loss mode without touching customer objects.
4. Restore into an isolated recovery prefix/account with the backup operator;
   do not overwrite production first.
5. Verify checksum, KMS encryption, tags, tenant prefix, preview regeneration,
   database linkage, and API authorization.
6. Confirm the restored object cannot be accessed by another organization.
7. Record achieved recovery point/time, verifier output, audit-event IDs,
   deviations, cleanup state, and approver sign-off.

PostgreSQL restore evidence must be paired with the object restore because a
bucket-only recovery can leave object/database references inconsistent.

## Customer Deletion And GDPR Erasure

Application `DeleteObject` calls on a versioned bucket create delete markers;
they do not erase historical versions. Final deletion therefore requires a
separate, tightly controlled operator role that is not attached to the runtime.

1. Validate organization, project, scan, and request IDs; confirm authorization
   and whether erasure is legally applicable.
2. Check legal holds, incident preservation, contractual retention, dataset
   releases, and active backup restores. A valid hold blocks deletion.
3. Disable new writes/jobs for the deletion scope and take a value-free
   inventory of database rows, current objects, versions, delete markers,
   exports, queues, caches, and backups.
4. Require two-person approval before invoking reviewed deletion automation.
5. Delete current objects and every version/delete marker in the exact tenant
   prefix; never use an unscoped bucket deletion command.
6. Delete or tombstone database records according to the approved schema plan,
   retaining only legally permitted audit identifiers.
7. Verify the prefix has no current objects, versions, or delete markers and
   that API access returns no data.
8. Record when expiring backups will lose the data; do not silently claim
   immediate backup erasure if the approved backup policy prevents it.
9. Issue a deletion receipt containing request/scope IDs, counts, completion
   state, timestamps, backup-expiry statement, audit-event IDs, and approvals—
   never filenames, DICOM values, image data, annotation notes, or secrets.

Project and scan deletion governance is implemented through versioned
organization policies, append-only legal holds, value-free inventories,
retention checks, different requester/approver identities, and a third operator.
The web API can request, approve, or cancel but cannot execute deletion. The
operator environment must supply the database URL and separately authorized
storage workload identity, then enable and confirm one exact request:

```bash
DATA_DELETION_OPERATOR_ENABLED=true \
python -m backend.data_lifecycle_cli \
  --request-id <approved-request-uuid> \
  --operator-user-id <distinct-admin-uuid> \
  --confirm-request-id <approved-request-uuid>
```

The command derives the tenant prefix from trusted database records, rechecks
retention and all applicable organization/project/scan holds, deletes every S3
version and delete marker (or the exact local prefix), verifies absence, revokes
affected dataset releases as `source_withdrawn`, removes scan-owned rows, and
writes an append-only checksum receipt with backup expiry. Project scope retains
only a data-minimized project tombstone plus separately namespaced retained
release artifacts because immutable release/audit history uses stable IDs.
Receipts count those retained artifacts, and revoked releases deny subsequent
artifact delivery. The normal runtime policy still excludes
`s3:DeleteObjectVersion`.

Organization-wide execution remains unsupported. Target deployment must also
prove maintenance/write isolation, version-purge permissions on only the
approved bucket, independent backup expiry, queue/cache/export inventory, and
two-person operator authorization before this command is enabled.

## Evidence Record

For each deployment or drill, retain:

- change/restore/deletion ticket ID and environment;
- CloudFormation stack ID and template commit;
- approved retention values and policy owner;
- verifier JSON and AWS Config/Security Hub results;
- synthetic fixture IDs and checksums only;
- backup job, restore job, achieved RPO/RTO, and cleanup confirmation;
- audit-event IDs, approvers, deviations, and follow-up issues.

Do not store credentials, patient identifiers, object keys containing unsafe
legacy names, DICOM metadata values, pixels, or clinical free text in evidence.
