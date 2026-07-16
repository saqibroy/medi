import { FormEvent, useEffect, useState } from "react";

import { approveDeletionRequest, cancelDeletionRequest, createDeletionRequest, createLegalHold, createRetentionPolicy, listDeletionRequests, listLegalHolds, listRetentionPolicies, releaseLegalHold } from "../api/governanceApi";
import type { DeletionRequest, LegalHold, RetentionPolicy, RetentionPolicyPayload } from "../types/governance";

interface Props {
  projectId?: string;
  csrfToken: string;
}

const emptyPolicy: Record<keyof Omit<RetentionPolicyPayload, "approval_reference">, string> = {
  original_minimum_days: "",
  mask_minimum_days: "",
  metadata_minimum_days: "",
  dataset_release_minimum_days: "",
  audit_minimum_days: "",
  backup_retention_days: "",
  rpo_hours: "",
  rto_hours: "",
};

export function DataGovernancePanel({ projectId, csrfToken }: Props) {
  const [policies, setPolicies] = useState<RetentionPolicy[]>([]);
  const [holds, setHolds] = useState<LegalHold[]>([]);
  const [deletions, setDeletions] = useState<DeletionRequest[]>([]);
  const [policyValues, setPolicyValues] = useState(emptyPolicy);
  const [policyReference, setPolicyReference] = useState("");
  const [holdReference, setHoldReference] = useState("");
  const [deletionReference, setDeletionReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh(): Promise<void> {
    if (!csrfToken) return;
    try {
      const [loadedPolicies, loadedHolds, loadedDeletions] = await Promise.all([
        listRetentionPolicies(csrfToken), listLegalHolds(csrfToken), listDeletionRequests(csrfToken),
      ]);
      setPolicies(loadedPolicies);
      setHolds(loadedHolds);
      setDeletions(loadedDeletions);
      setError(null);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not load governance controls");
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
      setError(apiError instanceof Error ? apiError.message : "Governance operation failed");
    } finally {
      setLoading(false);
    }
  }

  function handlePolicy(event: FormEvent): void {
    event.preventDefault();
    const numeric = Object.fromEntries(Object.entries(policyValues).map(([key, value]) => [key, Number(value)]));
    void run(() => createRetentionPolicy(csrfToken, { approval_reference: policyReference, ...numeric } as RetentionPolicyPayload));
  }

  const projectHolds = holds.filter((hold) => hold.scope_type === "project" && hold.scope_id === projectId);
  const projectDeletions = deletions.filter((request) => request.scope_type === "project" && request.scope_id === projectId);

  return (
    <details className="border-b border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-slate-500">Data Governance</summary>
      <p className="mt-2 text-xs text-slate-500">References must be approved ticket IDs, never patient identifiers. Destructive execution is operator-only.</p>
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
      <form className="mt-3 space-y-2" onSubmit={handlePolicy}>
        <p className="text-xs font-semibold text-slate-700">Retention policy {policies[0] ? `(current v${policies[0].version})` : "(required)"}</p>
        <input required pattern="[A-Za-z0-9][A-Za-z0-9._:/-]*" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" placeholder="Approved policy ticket" value={policyReference} onChange={(event) => setPolicyReference(event.target.value)} />
        <div className="grid grid-cols-2 gap-1">
          {Object.entries(policyValues).map(([key, value]) => (
            <label className="text-[10px] text-slate-500" key={key}>{key.split("_").join(" ")}
              <input required min={key === "backup_retention_days" || key.endsWith("hours") ? 1 : 0} type="number" className="mt-0.5 w-full rounded border border-slate-300 px-1 py-1 text-xs" value={value} onChange={(event) => setPolicyValues((current) => ({ ...current, [key]: event.target.value }))} />
            </label>
          ))}
        </div>
        <button disabled={loading} className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Create new policy version</button>
      </form>
      <div className="mt-4 space-y-2">
        <p className="text-xs font-semibold text-slate-700">Selected project controls</p>
        <div className="flex gap-1">
          <input className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs" placeholder="Legal-hold ticket" value={holdReference} onChange={(event) => setHoldReference(event.target.value)} />
          <button disabled={!projectId || !holdReference || loading} className="rounded border border-amber-400 px-2 py-1 text-xs text-amber-800" onClick={() => void run(() => createLegalHold(csrfToken, projectId ?? "", holdReference))}>Hold</button>
        </div>
        {projectHolds.map((hold) => <div className="flex items-center justify-between text-xs" key={hold.id}><span>{hold.approval_reference}: {hold.status}</span>{hold.status === "active" ? <button className="text-amber-800 underline" disabled={loading} onClick={() => void run(() => releaseLegalHold(csrfToken, hold.id))}>Release by second admin</button> : null}</div>)}
        <div className="flex gap-1">
          <input className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs" placeholder="Deletion approval ticket" value={deletionReference} onChange={(event) => setDeletionReference(event.target.value)} />
          <button disabled={!projectId || !deletionReference || !policies[0] || loading} className="rounded border border-red-400 px-2 py-1 text-xs text-red-700" onClick={() => void run(() => createDeletionRequest(csrfToken, projectId ?? "", deletionReference))}>Request</button>
        </div>
        {projectDeletions.map((request) => <div className="rounded border border-slate-200 p-2 text-xs" key={request.id}><p>{request.approval_reference}: {request.status}</p><p className="text-[10px] text-slate-500">Earliest: {new Date(request.earliest_execute_at).toLocaleString()}</p>{request.status === "requested" ? <div className="mt-1 flex gap-2"><button className="text-red-700 underline" disabled={loading} onClick={() => void run(() => approveDeletionRequest(csrfToken, request.id))}>Approve as second admin</button><button className="text-slate-600 underline" disabled={loading} onClick={() => void run(() => cancelDeletionRequest(csrfToken, request.id))}>Cancel</button></div> : null}{request.receipt ? <p className="mt-1 truncate font-mono text-[10px]" title={request.receipt.receipt_sha256}>{request.receipt.receipt_sha256}</p> : null}</div>)}
      </div>
    </details>
  );
}
