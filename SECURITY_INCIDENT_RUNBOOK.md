# Security Incident Runbook

Status: repository mechanics defined; target owners, contacts, severity rules,
notification decisions, and exercise evidence remain deployment inputs.

Use this runbook for suspected unauthorized access, disclosure, alteration,
loss, malicious deletion, credential misuse, malware, public object exposure,
tenant-boundary failure, or integrity failure involving Medi. A security
incident is not automatically a legally notifiable personal-data breach. The
appointed controller/processor, privacy/DPO, legal, and security owners must
make and document that assessment.

Read [OPERATOR_RUNBOOKS.md](OPERATOR_RUNBOOKS.md) first and apply its evidence
rules throughout.

## Declare And Stabilize

1. Open the approved incident record and assign a UTC start time, incident
   commander, security lead, operations lead, and decision log.
2. Record the detection source, affected environment/services, current release
   commit/image digest, and safe symptoms. Use request IDs and controlled Medi
   IDs; do not copy payloads, image data, metadata, or credentials.
3. Classify the incident using the target severity policy. If that policy or an
   owner is missing, escalate internally and keep sensitive-data access closed.
4. Preserve the original alert and relevant immutable log references. Restrict
   incident access to the approved response group.
5. If active harm is plausible, isolate affected traffic or workloads using the
   target procedure. Keep health/status communication separate from evidence.

## Privacy-Safe Evidence Preservation

- Preserve UTC time ranges, request IDs, audit-event IDs, identity/workload
  identifiers, release and configuration versions, database transaction/log
  references, object version IDs, KMS event IDs, counts, and hashes.
- Export only through the approved evidence path with access logging,
  encryption, retention, and chain-of-custody controls.
- Do not run broad database queries or object downloads merely to investigate.
  Narrow collection by tenant-safe IDs, time window, and approved hypothesis.
- Do not paste raw application exceptions: validation details can contain
  patient-related values. Medi request logs intentionally omit headers, bodies,
  queries, and exception text.
- Do not mutate or delete append-only audit rows. If audit integrity is in
  question, preserve a database snapshot and the relevant verification-key
  custody records before remediation.

## Scope The Incident

Answer with evidence, marking unknowns explicitly:

1. Which organizations, projects, scans, release IDs, services, regions, and
   UTC intervals may be affected?
2. Was confidentiality, integrity, or availability affected? Was access merely
   attempted, or is successful access supported by evidence?
3. Which identity, role, session, workload, credential, key, or software
   version was involved?
4. Could the scope include pixels, raw DICOM/NIfTI, metadata, annotations,
   notes, derived previews, exports, audit records, or privacy-case references?
5. Are legal holds, deletion requests, backup restores, dataset releases, or
   external-AI approvals affected?
6. Are other tenants demonstrably isolated? Do not infer isolation from an
   absence of alerts alone.

## Containment Paths

Choose the smallest effective, reversible action and record approval:

- **Session or application secret:** follow
  [KEY_COMPROMISE_RUNBOOK.md](KEY_COMPROMISE_RUNBOOK.md). Revoke affected
  sessions or access at the trusted control plane.
- **Database:** remove application traffic/writes, preserve database evidence,
  and use the managed database incident procedure. Do not modify schema or
  restore over the source during investigation.
- **Redis:** keep production fail-closed behavior. Do not switch to process
  memory to bypass an outage or investigation.
- **Private storage/KMS:** block the affected principal or access path without
  deleting objects/versions, preserve access-policy and object-version
  evidence, then use [STORAGE_OPERATIONS_RUNBOOK.md](STORAGE_OPERATIONS_RUNBOOK.md).
- **Tenant-boundary defect:** remove the vulnerable route or release from
  service. Do not rely only on UI hiding.
- **External egress:** keep `EXTERNAL_AI_ENABLED=false`, disable the target
  network route/provider identity, and preserve value-free gateway decision
  evidence. Never send suspected data to another provider for analysis.
- **Malicious release or image:** stop new rollout, retain the digest and build
  evidence, and use [DEPLOYMENT_ROLLBACK_RUNBOOK.md](DEPLOYMENT_ROLLBACK_RUNBOOK.md).

## Personal-Data Breach Assessment Handoff

Immediately notify the target privacy/DPO, legal, controller/processor, and
security owners through the approved private channel when personal data may be
in scope. Supply the evidence record, not raw patient data.

The owner must document the facts, affected data/subjects at an appropriate
level, likely consequences, mitigations, controller/processor role, awareness
time, risk assessment, and notification/communication decision. GDPR Article
33 assigns different duties to controllers and processors and requires breach
documentation; it does not make every security incident automatically
notifiable. See the [official GDPR text](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
and [EDPB breach guidance](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-92022-personal-data-breach-notification-under_en).

Engineering operators must not decide the legal outcome, silently start a
deadline from an unreviewed timestamp, contact an authority/data subject, or
promise notification timing unless the appointed owner authorizes it.

## Eradicate, Recover, And Verify

1. Identify the root cause and exact compromised boundary before rebuilding.
2. Patch or remove the cause; rotate/revoke only the affected identities and
   keys using the key-compromise procedure.
3. Recover from reviewed artifacts/backups into an isolated target when data or
   integrity may be affected. Verify checksums and revisions before cutover.
4. Restore traffic gradually under the approved monitoring window.
5. Verify liveness/readiness, tenant authorization, the affected data flow,
   audit-event creation/integrity, rate-limit enforcement, private storage/KMS
   behavior, and backup continuity.
6. Obtain incident commander, security, operations, and privacy/legal closure
   decisions. Record residual risk and follow-up tasks.

## Exercise

At least annually and after material identity/storage changes, rehearse one
synthetic scenario covering detection, traffic isolation, evidence collection,
key decision-making, privacy handoff, recovery, and closure. Do not mark the
target gate complete until owners, elapsed times, evidence access, deviations,
and corrective actions are recorded and approved.
