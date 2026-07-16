/** Immutable project release controls and manifest inspection. */

import { useEffect, useState } from "react";

import { createDatasetRelease, getDatasetRelease, listDatasetReleases, revokeDatasetRelease } from "../api/projectsApi";
import type { DatasetRelease, DatasetReleaseReason, DatasetReleaseSummary } from "../types/project";

interface DatasetReleasePanelProps {
  projectId?: string;
  csrfToken: string;
  canManage: boolean;
}

export function DatasetReleasePanel({ projectId, csrfToken, canManage }: DatasetReleasePanelProps) {
  const [releases, setReleases] = useState<DatasetReleaseSummary[]>([]);
  const [selectedRelease, setSelectedRelease] = useState<DatasetRelease | null>(null);
  const [reasonCode, setReasonCode] = useState<DatasetReleaseReason>("quality_issue");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(): Promise<void> {
    if (!projectId || !csrfToken) {
      setReleases([]);
      setSelectedRelease(null);
      return;
    }
    setError(null);
    try {
      setReleases(await listDatasetReleases(projectId, csrfToken));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not load dataset releases");
    }
  }

  useEffect(() => {
    setSelectedRelease(null);
    void refresh();
  }, [projectId, csrfToken]);

  async function handleCreate(): Promise<void> {
    if (!projectId || !csrfToken) return;
    setIsLoading(true);
    setError(null);
    try {
      const created = await createDatasetRelease(projectId, csrfToken);
      setSelectedRelease(created);
      await refresh();
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not create dataset release");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleInspect(releaseId: string): Promise<void> {
    setIsLoading(true);
    setError(null);
    try {
      setSelectedRelease(await getDatasetRelease(releaseId, csrfToken));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not load release manifest");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRevoke(releaseId: string): Promise<void> {
    setIsLoading(true);
    setError(null);
    try {
      setSelectedRelease(await revokeDatasetRelease(releaseId, reasonCode, csrfToken));
      await refresh();
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not revoke dataset release");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="border-b border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Dataset Releases</h2>
        {canManage ? (
          <button className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:bg-slate-400" disabled={!projectId || !csrfToken || isLoading} onClick={() => void handleCreate()}>
            Create release
          </button>
        ) : null}
      </div>
      {!projectId ? <p className="mt-2 text-xs text-slate-500">Select a project to view immutable releases.</p> : null}
      {projectId && releases.length === 0 && !error ? <p className="mt-2 text-xs text-slate-500">No releases yet.</p> : null}
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
      <div className="mt-2 space-y-2">
        {releases.map((release) => (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-2 text-xs" key={release.id}>
            <div className="flex items-center justify-between gap-2">
              <button className="font-semibold text-slate-900 hover:underline" onClick={() => void handleInspect(release.id)}>
                v{release.version}
              </button>
              <span className={release.status === "active" ? "text-emerald-700" : release.status === "revoked" ? "text-red-700" : "text-slate-500"}>{release.status}</span>
            </div>
            <p className="mt-1 truncate font-mono text-[10px] text-slate-500" title={release.manifest_sha256}>{release.manifest_sha256}</p>
            {canManage && release.status !== "revoked" ? (
              <div className="mt-2 flex gap-1">
                <select className="min-w-0 flex-1 rounded border border-slate-300 bg-white px-1 py-1" value={reasonCode} onChange={(event) => setReasonCode(event.target.value as DatasetReleaseReason)}>
                  <option value="quality_issue">Quality issue</option>
                  <option value="source_withdrawn">Source withdrawn</option>
                  <option value="policy_change">Policy change</option>
                  <option value="other">Other</option>
                </select>
                <button className="rounded border border-red-300 px-2 py-1 text-red-700" disabled={isLoading} onClick={() => void handleRevoke(release.id)}>Revoke</button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {selectedRelease ? (
        <details className="mt-3" open>
          <summary className="cursor-pointer text-xs font-medium text-slate-700">Release v{selectedRelease.version} manifest</summary>
          <pre className="mt-2 max-h-56 overflow-auto rounded bg-slate-950 p-2 text-[10px] text-slate-100">{JSON.stringify(selectedRelease.manifest, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}
