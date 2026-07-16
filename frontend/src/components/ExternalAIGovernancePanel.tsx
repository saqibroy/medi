import { FormEvent, useEffect, useMemo, useState } from "react";

import { createExternalAIDataFlow, createExternalAIProvider, evaluateExternalAIEgress, getExternalAIStatus, listExternalAIDataFlows, listExternalAIDecisions, listExternalAIProviders, revokeExternalAIDataFlow, revokeExternalAIProvider } from "../api/externalAiGovernanceApi";
import type { ExternalAIDataClass, ExternalAIDataFlow, ExternalAIDecision, ExternalAIProvider, ExternalAIPurpose, ExternalAIStatus, ExternalAITransferMechanism } from "../types/externalAiGovernance";

interface Props { projectId?: string; csrfToken: string }

const dataClassOptions: ExternalAIDataClass[] = ["label_taxonomy", "annotation_geometry", "derived_previews", "deidentified_metadata", "deidentified_pixels"];
const purposes: ExternalAIPurpose[] = ["annotation_assistance", "quality_assurance", "research_inference"];
const transferOptions: ExternalAITransferMechanism[] = ["not_applicable", "adequacy_decision", "standard_contractual_clauses", "approved_derogation"];

export function ExternalAIGovernancePanel({ projectId, csrfToken }: Props) {
  const [status, setStatus] = useState<ExternalAIStatus | null>(null);
  const [providers, setProviders] = useState<ExternalAIProvider[]>([]);
  const [flows, setFlows] = useState<ExternalAIDataFlow[]>([]);
  const [decisions, setDecisions] = useState<ExternalAIDecision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [providerForm, setProviderForm] = useState({ provider_key: "", display_name: "", model_name: "", model_version: "", purpose_code: "", endpoint_origin: "", region_code: "", retention_days: "", subprocessors: "", transfer_mechanism: "", contract_owner_reference: "", approval_reference: "" });
  const [providerClasses, setProviderClasses] = useState<ExternalAIDataClass[]>([]);
  const [flowProviderId, setFlowProviderId] = useState("");
  const [flowClasses, setFlowClasses] = useState<ExternalAIDataClass[]>([]);
  const [flowReference, setFlowReference] = useState("");

  const activeProviders = providers.filter((provider) => provider.status === "active");
  const selectedProvider = useMemo(() => activeProviders.find((provider) => provider.id === flowProviderId), [activeProviders, flowProviderId]);
  const projectFlows = flows.filter((flow) => flow.project_id === projectId);

  async function refresh(): Promise<void> {
    if (!csrfToken) return;
    try {
      const [loadedStatus, loadedProviders, loadedFlows, loadedDecisions] = await Promise.all([
        getExternalAIStatus(csrfToken), listExternalAIProviders(csrfToken), listExternalAIDataFlows(csrfToken), listExternalAIDecisions(csrfToken),
      ]);
      setStatus(loadedStatus); setProviders(loadedProviders); setFlows(loadedFlows); setDecisions(loadedDecisions); setError(null);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not load external AI governance");
    }
  }

  useEffect(() => { void refresh(); }, [csrfToken, projectId]);

  async function run(action: () => Promise<unknown>): Promise<void> {
    setLoading(true); setError(null);
    try { await action(); await refresh(); }
    catch (apiError) { setError(apiError instanceof Error ? apiError.message : "External AI governance operation failed"); }
    finally { setLoading(false); }
  }

  function toggle(value: ExternalAIDataClass, current: ExternalAIDataClass[], update: (next: ExternalAIDataClass[]) => void): void {
    update(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function submitProvider(event: FormEvent): void {
    event.preventDefault();
    if (!providerForm.purpose_code || !providerForm.transfer_mechanism || providerClasses.length === 0) return;
    void run(() => createExternalAIProvider(csrfToken, {
      ...providerForm,
      purpose_code: providerForm.purpose_code as ExternalAIPurpose,
      transfer_mechanism: providerForm.transfer_mechanism as ExternalAITransferMechanism,
      retention_days: Number(providerForm.retention_days),
      training_use_allowed: false,
      subprocessors: providerForm.subprocessors.split(",").map((item) => item.trim()).filter(Boolean),
      data_classes: providerClasses,
    }));
  }

  function submitFlow(event: FormEvent): void {
    event.preventDefault();
    if (!projectId || !selectedProvider || flowClasses.length === 0) return;
    void run(() => createExternalAIDataFlow(csrfToken, {
      project_id: projectId,
      provider_approval_id: selectedProvider.id,
      purpose_code: selectedProvider.purpose_code,
      data_classes: flowClasses,
      approval_reference: flowReference,
      expires_at: null,
    }));
  }

  return (
    <details className="border-b border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-slate-500">External AI Governance</summary>
      <p className="mt-2 text-xs text-slate-500">No prompt or image is sent here. References must be approved IDs, never patient or staff identifiers.</p>
      <p className={`mt-2 rounded p-2 text-xs ${status?.enabled ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
        Runtime: {status?.enabled ? "enabled behind exact origin allowlist" : "disabled (safe default)"}; provider call: not implemented.
      </p>
      {status ? <p className="mt-1 text-[10px] text-slate-500">Always prohibited: {status.permanently_prohibited_data_classes.join(", ")}</p> : null}
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}

      <form className="mt-3 space-y-2" onSubmit={submitProvider}>
        <p className="text-xs font-semibold text-slate-700">Register exact provider approval</p>
        {(["provider_key", "display_name", "model_name", "model_version", "endpoint_origin", "region_code", "contract_owner_reference", "approval_reference"] as const).map((key) => (
          <input key={key} required className="w-full rounded border border-slate-300 px-2 py-1 text-xs" placeholder={key.split("_").join(" ")} value={providerForm[key]} onChange={(event) => setProviderForm((current) => ({ ...current, [key]: event.target.value }))} />
        ))}
        <div className="grid grid-cols-2 gap-1">
          <select required className="rounded border border-slate-300 px-1 py-1 text-xs" value={providerForm.purpose_code} onChange={(event) => setProviderForm((current) => ({ ...current, purpose_code: event.target.value }))}><option value="">Purpose</option>{purposes.map((value) => <option key={value}>{value}</option>)}</select>
          <select required className="rounded border border-slate-300 px-1 py-1 text-xs" value={providerForm.transfer_mechanism} onChange={(event) => setProviderForm((current) => ({ ...current, transfer_mechanism: event.target.value }))}><option value="">Transfer mechanism</option>{transferOptions.map((value) => <option key={value}>{value}</option>)}</select>
        </div>
        <input required min="0" max="3650" type="number" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" placeholder="provider retention days" value={providerForm.retention_days} onChange={(event) => setProviderForm((current) => ({ ...current, retention_days: event.target.value }))} />
        <input className="w-full rounded border border-slate-300 px-2 py-1 text-xs" placeholder="subprocessor registry IDs, comma-separated" value={providerForm.subprocessors} onChange={(event) => setProviderForm((current) => ({ ...current, subprocessors: event.target.value }))} />
        <div className="space-y-1">{dataClassOptions.map((value) => <label className="block text-[10px] text-slate-600" key={value}><input type="checkbox" checked={providerClasses.includes(value)} onChange={() => toggle(value, providerClasses, setProviderClasses)} /> {value}</label>)}</div>
        <p className="text-[10px] text-slate-500">Provider training is always prohibited by this repository policy.</p>
        <button disabled={loading || providerClasses.length === 0} className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Create approval version</button>
      </form>

      <div className="mt-3 space-y-1">{providers.map((provider) => <div className="rounded border border-slate-200 p-2 text-xs" key={provider.id}><p>{provider.display_name} / {provider.model_name} {provider.model_version} (v{provider.version})</p><p className="text-[10px] text-slate-500">{provider.status}; {provider.endpoint_origin}; retention {provider.retention_days}d</p>{provider.status === "active" ? <button type="button" disabled={loading} className="text-red-700 underline" onClick={() => void run(() => revokeExternalAIProvider(csrfToken, provider.id))}>Revoke as second admin</button> : null}</div>)}</div>

      <form className="mt-4 space-y-2" onSubmit={submitFlow}>
        <p className="text-xs font-semibold text-slate-700">Selected project data flow</p>
        <select required className="w-full rounded border border-slate-300 px-2 py-1 text-xs" value={flowProviderId} onChange={(event) => { setFlowProviderId(event.target.value); setFlowClasses([]); }}><option value="">Approved provider version</option>{activeProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.display_name} / {provider.model_version}</option>)}</select>
        <input required className="w-full rounded border border-slate-300 px-2 py-1 text-xs" placeholder="dataset-flow approval ID" value={flowReference} onChange={(event) => setFlowReference(event.target.value)} />
        {selectedProvider?.data_classes.map((value) => <label className="block text-[10px] text-slate-600" key={value}><input type="checkbox" checked={flowClasses.includes(value)} onChange={() => toggle(value, flowClasses, setFlowClasses)} /> {value}</label>)}
        <button disabled={!projectId || !selectedProvider || flowClasses.length === 0 || loading} className="rounded border border-slate-400 px-2 py-1 text-xs">Approve project flow</button>
      </form>

      <div className="mt-3 space-y-2">{projectFlows.map((flow) => {
        const latest = decisions.find((decision) => decision.data_flow_id === flow.id);
        return <div className="rounded border border-slate-200 p-2 text-xs" key={flow.id}><p>{flow.approval_reference}: {flow.status}</p><p className="text-[10px] text-slate-500">{flow.data_classes.join(", ")}</p><div className="mt-1 flex gap-2">{flow.status === "active" ? <><button type="button" disabled={loading} className="text-slate-700 underline" onClick={() => void run(() => evaluateExternalAIEgress(csrfToken, flow))}>Dry-run decision</button><button type="button" disabled={loading} className="text-red-700 underline" onClick={() => void run(() => revokeExternalAIDataFlow(csrfToken, flow.id))}>Revoke as second admin</button></> : null}</div>{latest ? <p className={`mt-1 text-[10px] ${latest.result === "allowed" ? "text-amber-800" : "text-emerald-700"}`}>Latest: {latest.result} / {latest.reason_code}</p> : null}</div>;
      })}</div>
    </details>
  );
}
