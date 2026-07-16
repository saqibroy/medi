import { FormEvent, useEffect, useMemo, useState } from "react";

import { listDeletionRequests, listRetentionPolicies } from "../api/governanceApi";
import {
  acceptPrivacyRequest,
  cancelPrivacyRequest,
  createPrivacyProcessingRecord,
  createPrivacyRequest,
  denyPrivacyRequest,
  extendPrivacyRequest,
  fulfillPrivacyRequest,
  listPrivacyProcessingRecords,
  listPrivacyRequests,
  revokePrivacyProcessingRecord,
  verifyPrivacyIdentity,
} from "../api/privacyGovernanceApi";
import type { DeletionRequest, RetentionPolicy } from "../types/governance";
import type { PrivacyProcessingRecord, PrivacyProcessingRecordPayload, PrivacyRequest, PrivacyRequestType } from "../types/privacyGovernance";

interface Props {
  projectId?: string;
  csrfToken: string;
}

const outcomeByType: Record<PrivacyRequestType, string> = {
  access: "secure_delivery",
  rectification: "record_corrected",
  restriction: "processing_restricted",
  objection: "objection_applied",
  portability: "secure_delivery",
  erasure: "erasure_verified",
};

const emptyProcessing = {
  activity_key: "",
  organization_role: "",
  purpose_code: "",
  lawful_basis: "",
  health_data_processed: "",
  article9_condition: "",
  data_subject_categories: "",
  personal_data_categories: "",
  recipient_categories: "",
  processor_references: "",
  processing_locations: "",
  transfer_mechanism: "",
  transfer_safeguard_reference: "",
  retention_policy_id: "",
  security_measure_references: "",
  dpia_required: "",
  dpia_outcome: "",
  dpia_reference: "",
  dpo_review_reference: "",
  approval_reference: "",
};

function codes(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function PrivacyGovernancePanel({ projectId, csrfToken }: Props) {
  const [records, setRecords] = useState<PrivacyProcessingRecord[]>([]);
  const [requests, setRequests] = useState<PrivacyRequest[]>([]);
  const [policies, setPolicies] = useState<RetentionPolicy[]>([]);
  const [deletions, setDeletions] = useState<DeletionRequest[]>([]);
  const [processing, setProcessing] = useState(emptyProcessing);
  const [caseReference, setCaseReference] = useState("");
  const [subjectReference, setSubjectReference] = useState("");
  const [requestType, setRequestType] = useState<PrivacyRequestType | "">("");
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [reason, setReason] = useState<Record<string, string>>({});
  const [deletionLink, setDeletionLink] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(): Promise<void> {
    if (!csrfToken) return;
    try {
      const [loadedRecords, loadedRequests, loadedPolicies, loadedDeletions] = await Promise.all([
        listPrivacyProcessingRecords(csrfToken),
        listPrivacyRequests(csrfToken),
        listRetentionPolicies(csrfToken),
        listDeletionRequests(csrfToken),
      ]);
      setRecords(loadedRecords);
      setRequests(loadedRequests);
      setPolicies(loadedPolicies);
      setDeletions(loadedDeletions);
      setProcessing((current) => ({ ...current, retention_policy_id: current.retention_policy_id || loadedPolicies[0]?.id || "" }));
      setError(null);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not load privacy governance");
    }
  }

  useEffect(() => { void refresh(); }, [csrfToken, projectId]);

  async function run(action: () => Promise<unknown>): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Privacy governance operation failed");
    } finally {
      setLoading(false);
    }
  }

  function handleProcessingRecord(event: FormEvent): void {
    event.preventDefault();
    const payload: PrivacyProcessingRecordPayload = {
      activity_key: processing.activity_key,
      organization_role: processing.organization_role as PrivacyProcessingRecordPayload["organization_role"],
      purpose_code: processing.purpose_code as PrivacyProcessingRecordPayload["purpose_code"],
      lawful_basis: processing.lawful_basis as PrivacyProcessingRecordPayload["lawful_basis"],
      health_data_processed: processing.health_data_processed === "true",
      article9_condition: processing.article9_condition as PrivacyProcessingRecordPayload["article9_condition"],
      data_subject_categories: codes(processing.data_subject_categories),
      personal_data_categories: codes(processing.personal_data_categories),
      recipient_categories: codes(processing.recipient_categories),
      processor_references: codes(processing.processor_references),
      processing_locations: codes(processing.processing_locations),
      transfer_mechanism: processing.transfer_mechanism as PrivacyProcessingRecordPayload["transfer_mechanism"],
      transfer_safeguard_reference: processing.transfer_safeguard_reference || null,
      retention_policy_id: processing.retention_policy_id,
      security_measure_references: codes(processing.security_measure_references),
      dpia_required: processing.dpia_required === "true",
      dpia_outcome: processing.dpia_outcome as PrivacyProcessingRecordPayload["dpia_outcome"],
      dpia_reference: processing.dpia_reference,
      dpo_review_reference: processing.dpo_review_reference,
      approval_reference: processing.approval_reference,
    };
    void run(async () => {
      await createPrivacyProcessingRecord(csrfToken, payload);
      setProcessing({ ...emptyProcessing, retention_policy_id: policies[0]?.id ?? "" });
    });
  }

  function handlePrivacyRequest(event: FormEvent): void {
    event.preventDefault();
    if (!projectId || !requestType) return;
    void run(async () => {
      await createPrivacyRequest(csrfToken, {
        case_reference: caseReference,
        external_subject_reference: subjectReference,
        request_type: requestType,
        scope_type: "project",
        scope_id: projectId,
      });
      setCaseReference("");
      setSubjectReference("");
      setRequestType("");
    });
  }

  const projectRequests = requests.filter((request) => request.scope_type === "project" && request.scope_id === projectId);
  const erasureDeletions = useMemo(
    () => deletions.filter((item) => item.scope_type === "project" && item.scope_id === projectId && item.reason_code === "erasure_request"),
    [deletions, projectId],
  );

  function evidenceFor(requestId: string): string {
    return evidence[requestId] ?? "";
  }

  return (
    <details className="border-b border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-slate-500">Privacy Operations</summary>
      <p className="mt-2 text-xs text-slate-500">Engineering evidence only—not legal approval. Never enter names, emails, patient IDs, identity documents, request narratives, or delivered data. Subject references are keyed-digested before storage.</p>
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}

      <details className="mt-3 rounded border border-slate-200 p-2">
        <summary className="cursor-pointer text-xs font-semibold text-slate-700">Processing and DPIA evidence</summary>
        <form className="mt-2 grid grid-cols-2 gap-1" onSubmit={handleProcessingRecord}>
          <input required pattern="[a-z0-9][a-z0-9-]*" className="rounded border px-2 py-1 text-xs" placeholder="Activity key" value={processing.activity_key} onChange={(event) => setProcessing({ ...processing, activity_key: event.target.value })} />
          <select required className="rounded border px-1 py-1 text-xs" value={processing.organization_role} onChange={(event) => setProcessing({ ...processing, organization_role: event.target.value })}><option value="">Controller role</option><option value="controller">Controller</option><option value="processor">Processor</option><option value="joint_controller">Joint controller</option></select>
          <select required className="rounded border px-1 py-1 text-xs" value={processing.purpose_code} onChange={(event) => setProcessing({ ...processing, purpose_code: event.target.value })}><option value="">Purpose</option><option value="research_dataset_annotation">Research annotation</option><option value="imaging_quality_assurance">Imaging QA</option><option value="ml_dataset_export">ML export</option><option value="security_and_audit">Security/audit</option><option value="service_operations">Service operations</option><option value="customer_support">Customer support</option><option value="external_ai_inference">External AI inference</option></select>
          <select required className="rounded border px-1 py-1 text-xs" value={processing.lawful_basis} onChange={(event) => setProcessing({ ...processing, lawful_basis: event.target.value })}><option value="">Article 6 basis</option>{["consent", "contract", "legal_obligation", "vital_interests", "public_task", "legitimate_interests"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
          <select required className="rounded border px-1 py-1 text-xs" value={processing.health_data_processed} onChange={(event) => setProcessing({ ...processing, health_data_processed: event.target.value })}><option value="">Health data?</option><option value="true">Yes</option><option value="false">No</option></select>
          <select required className="rounded border px-1 py-1 text-xs" value={processing.article9_condition} onChange={(event) => setProcessing({ ...processing, article9_condition: event.target.value })}><option value="">Article 9 condition</option>{["not_applicable", "explicit_consent", "employment_social_security", "vital_interests", "nonprofit", "made_public", "legal_claims", "substantial_public_interest", "healthcare", "public_health", "research_statistics"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
          <input required className="rounded border px-2 py-1 text-xs" placeholder="Subject categories, comma-separated" value={processing.data_subject_categories} onChange={(event) => setProcessing({ ...processing, data_subject_categories: event.target.value })} />
          <input required className="rounded border px-2 py-1 text-xs" placeholder="Data categories, comma-separated" value={processing.personal_data_categories} onChange={(event) => setProcessing({ ...processing, personal_data_categories: event.target.value })} />
          <input required className="rounded border px-2 py-1 text-xs" placeholder="Recipient categories, comma-separated" value={processing.recipient_categories} onChange={(event) => setProcessing({ ...processing, recipient_categories: event.target.value })} />
          <input className="rounded border px-2 py-1 text-xs" placeholder="Processor ticket refs, comma-separated" value={processing.processor_references} onChange={(event) => setProcessing({ ...processing, processor_references: event.target.value })} />
          <input required className="rounded border px-2 py-1 text-xs" placeholder="Location codes, comma-separated" value={processing.processing_locations} onChange={(event) => setProcessing({ ...processing, processing_locations: event.target.value })} />
          <select required className="rounded border px-1 py-1 text-xs" value={processing.transfer_mechanism} onChange={(event) => setProcessing({ ...processing, transfer_mechanism: event.target.value })}><option value="">Transfer mechanism</option>{["not_applicable", "adequacy_decision", "standard_contractual_clauses", "binding_corporate_rules", "approved_derogation"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
          <input className="rounded border px-2 py-1 text-xs" placeholder="Transfer safeguard ref" value={processing.transfer_safeguard_reference} onChange={(event) => setProcessing({ ...processing, transfer_safeguard_reference: event.target.value })} />
          <select required className="rounded border px-1 py-1 text-xs" value={processing.retention_policy_id} onChange={(event) => setProcessing({ ...processing, retention_policy_id: event.target.value })}><option value="">Retention policy</option>{policies.map((policy) => <option key={policy.id} value={policy.id}>v{policy.version} · {policy.approval_reference}</option>)}</select>
          <input required className="rounded border px-2 py-1 text-xs" placeholder="Security control refs, comma-separated" value={processing.security_measure_references} onChange={(event) => setProcessing({ ...processing, security_measure_references: event.target.value })} />
          <select required className="rounded border px-1 py-1 text-xs" value={processing.dpia_required} onChange={(event) => setProcessing({ ...processing, dpia_required: event.target.value })}><option value="">DPIA required?</option><option value="true">Yes</option><option value="false">No</option></select>
          <select required className="rounded border px-1 py-1 text-xs" value={processing.dpia_outcome} onChange={(event) => setProcessing({ ...processing, dpia_outcome: event.target.value })}><option value="">DPIA outcome</option><option value="not_required">Not required</option><option value="approved">Approved</option><option value="consultation_required">Consultation required</option></select>
          {(["dpia_reference", "dpo_review_reference", "approval_reference"] as const).map((key) => <input required key={key} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]*" className="rounded border px-2 py-1 text-xs" placeholder={key.split("_").join(" ")} value={processing[key]} onChange={(event) => setProcessing({ ...processing, [key]: event.target.value })} />)}
          <button disabled={loading || !policies.length} className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Create immutable version</button>
        </form>
        <div className="mt-2 space-y-1">{records.map((record) => <div key={record.id} className="flex items-center justify-between rounded bg-slate-50 p-2 text-[10px]"><span>{record.activity_key} v{record.version} · {record.status} · {record.purpose_code}</span>{record.status !== "revoked" && record.status !== "superseded" ? <button disabled={loading} className="text-red-700 underline" onClick={() => void run(() => revokePrivacyProcessingRecord(csrfToken, record.id))}>Revoke by second admin</button> : null}</div>)}</div>
      </details>

      <form className="mt-3 space-y-2 rounded border border-slate-200 p-2" onSubmit={handlePrivacyRequest}>
        <p className="text-xs font-semibold text-slate-700">Selected-project privacy request</p>
        <input required pattern="[A-Za-z0-9][A-Za-z0-9._:/-]*" className="w-full rounded border px-2 py-1 text-xs" placeholder="Opaque privacy case ticket" value={caseReference} onChange={(event) => setCaseReference(event.target.value)} />
        <input required className="w-full rounded border px-2 py-1 text-xs" placeholder="External subject reference (keyed-digested; never returned)" value={subjectReference} onChange={(event) => setSubjectReference(event.target.value)} />
        <select required className="w-full rounded border px-2 py-1 text-xs" value={requestType} onChange={(event) => setRequestType(event.target.value as PrivacyRequestType | "")}><option value="">Request type</option>{Object.keys(outcomeByType).map((value) => <option key={value} value={value}>{value}</option>)}</select>
        <button disabled={loading || !projectId} className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Record request</button>
      </form>

      <div className="mt-3 space-y-2">
        {projectRequests.map((privacyRequest) => {
          const currentEvidence = evidenceFor(privacyRequest.id);
          const currentReason = reason[privacyRequest.id] ?? "";
          const open = !["fulfilled", "denied", "cancelled"].includes(privacyRequest.status);
          return <div key={privacyRequest.id} className="rounded border border-slate-200 p-2 text-xs">
            <p className="font-semibold">{privacyRequest.case_reference} · {privacyRequest.request_type} · {privacyRequest.status}</p>
            <p className={privacyRequest.deadline_status.includes("late") || privacyRequest.deadline_status === "overdue" ? "text-red-700" : "text-slate-500"}>Due {new Date(privacyRequest.effective_due_at).toLocaleDateString()} · {privacyRequest.deadline_status} · {privacyRequest.subject_reference_token}</p>
            {open ? <input className="mt-1 w-full rounded border px-2 py-1 text-xs" placeholder="Approved evidence ticket for next action" value={currentEvidence} onChange={(event) => setEvidence({ ...evidence, [privacyRequest.id]: event.target.value })} /> : null}
            {privacyRequest.request_type === "erasure" && privacyRequest.status === "identity_verified" ? <select className="mt-1 w-full rounded border px-2 py-1 text-xs" value={deletionLink[privacyRequest.id] ?? ""} onChange={(event) => setDeletionLink({ ...deletionLink, [privacyRequest.id]: event.target.value })}><option value="">Matching erasure deletion request</option>{erasureDeletions.map((item) => <option key={item.id} value={item.id}>{item.approval_reference} · {item.status}</option>)}</select> : null}
            {privacyRequest.status === "identity_verified" ? <select className="mt-1 w-full rounded border px-2 py-1 text-xs" value={currentReason} onChange={(event) => setReason({ ...reason, [privacyRequest.id]: event.target.value })}><option value="">Optional denial reason</option>{["request_not_applicable", "legal_exception", "insufficient_scope", "manifestly_unfounded_or_excessive"].map((value) => <option key={value} value={value}>{value}</option>)}</select> : null}
            {open ? <div className="mt-2 flex flex-wrap gap-2">
              {privacyRequest.status === "received" ? <><button disabled={loading || !currentEvidence} className="underline" onClick={() => void run(() => verifyPrivacyIdentity(csrfToken, privacyRequest.id, currentEvidence))}>Verify identity as second admin</button><button disabled={loading || !currentEvidence} className="text-red-700 underline" onClick={() => void run(() => denyPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence, "identity_not_verified"))}>Deny identity</button></> : null}
              {privacyRequest.status === "identity_verified" ? <><button disabled={loading || !currentEvidence || (privacyRequest.request_type === "erasure" && !deletionLink[privacyRequest.id])} className="underline" onClick={() => void run(() => acceptPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence, deletionLink[privacyRequest.id]))}>Accept</button><button disabled={loading || !currentEvidence || !currentReason} className="text-red-700 underline" onClick={() => void run(() => denyPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence, currentReason))}>Deny</button></> : null}
              {privacyRequest.status === "accepted" ? <button disabled={loading || !currentEvidence} className="underline" onClick={() => void run(() => fulfillPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence, outcomeByType[privacyRequest.request_type]))}>Record fulfillment evidence</button> : null}
              {!privacyRequest.events.some((event) => event.action === "deadline_extended") ? <select className="rounded border text-[10px]" value={currentReason} onChange={(event) => setReason({ ...reason, [privacyRequest.id]: event.target.value })}><option value="">Extension reason</option><option value="complexity">Complexity</option><option value="request_volume">Request volume</option></select> : null}
              {!privacyRequest.events.some((event) => event.action === "deadline_extended") ? <button disabled={loading || !currentEvidence || !["complexity", "request_volume"].includes(currentReason)} className="underline" onClick={() => void run(() => extendPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence, currentReason))}>Extend once</button> : null}
              <button disabled={loading || !currentEvidence} className="text-slate-600 underline" onClick={() => void run(() => cancelPrivacyRequest(csrfToken, privacyRequest.id, currentEvidence))}>Record withdrawal</button>
            </div> : null}
          </div>;
        })}
      </div>
    </details>
  );
}
