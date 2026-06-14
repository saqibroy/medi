/** ML export preview panel for project and scan datasets. */

import { useState } from "react";

import { exportProjectForMl } from "../api/projectsApi";
import { exportScanForMl } from "../api/scansApi";
import type { ExportResponse } from "../types/annotation";
import type { ProjectExportResponse } from "../types/project";

interface ExportPanelProps {
  projectId?: string;
  scanId?: string;
  token: string;
}

type ExportMode = "project" | "scan";

export function ExportPanel({ projectId, scanId, token }: ExportPanelProps) {
  /** Let developers inspect exactly what the ML team receives from the API. */
  const [mode, setMode] = useState<ExportMode>("project");
  const [exportData, setExportData] = useState<ExportResponse | ProjectExportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleExport(): Promise<void> {
    /** Fetch approved annotation data for a training pipeline handoff. */
    if (!token) return;
    if (mode === "project" && !projectId) return;
    if (mode === "scan" && !scanId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = mode === "project" ? await exportProjectForMl(projectId as string, token) : await exportScanForMl(scanId as string, token);
      setExportData(response);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Export failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="border-l border-slate-200 bg-slate-50 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">ML Export</h2>
      <div className="mb-3 grid grid-cols-2 rounded-md border border-slate-200 bg-white p-1 text-xs font-medium">
        <button className={`rounded px-2 py-1 ${mode === "project" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setMode("project")}>
          Project
        </button>
        <button className={`rounded px-2 py-1 ${mode === "scan" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setMode("scan")}>
          Scan
        </button>
      </div>
      {/* ML teams use this JSON to build datasets, check label quality, and feed training jobs. */}
      <button
        className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
        disabled={!token || isLoading || (mode === "project" ? !projectId : !scanId)}
        onClick={handleExport}
      >
        {isLoading ? "Exporting..." : mode === "project" ? "Export Project Dataset" : "Export Selected Scan"}
      </button>
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
      {!projectId ? <p className="mt-2 text-xs text-slate-500">Select a project to export dataset annotations.</p> : null}
      {projectId && mode === "scan" && !scanId ? <p className="mt-2 text-xs text-slate-500">Select a scan to export scan-level annotations.</p> : null}
      {exportData ? (
        <div className="mt-3 space-y-3 text-sm">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md bg-white p-2">
              <p className="text-xs text-slate-500">Total</p>
              <p className="font-semibold text-slate-900">{exportData.total_annotations}</p>
            </div>
            <div className="rounded-md bg-white p-2">
              <p className="text-xs text-slate-500">Approved</p>
              <p className="font-semibold text-emerald-700">{exportData.approved_count}</p>
            </div>
            <div className="rounded-md bg-white p-2">
              <p className="text-xs text-slate-500">Pending</p>
              <p className="font-semibold text-amber-700">{exportData.pending_count}</p>
            </div>
          </div>
          <pre className="max-h-56 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(exportData, null, 2)}</pre>
        </div>
      ) : null}
    </section>
  );
}
