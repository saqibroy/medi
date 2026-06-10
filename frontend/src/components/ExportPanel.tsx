/** ML export preview panel for the selected scan. */

import { useState } from "react";

import { exportScanForMl } from "../api/scansApi";
import type { ExportResponse } from "../types/annotation";

interface ExportPanelProps {
  scanId?: string;
}

export function ExportPanel({ scanId }: ExportPanelProps) {
  /** Let developers inspect exactly what the ML team receives from the API. */
  const [exportData, setExportData] = useState<ExportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleExport(): Promise<void> {
    /** Fetch approved annotation data for a training pipeline handoff. */
    if (!scanId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await exportScanForMl(scanId);
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
      {/* ML teams use this JSON to build datasets, check label quality, and feed training jobs. */}
      <button
        className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
        disabled={!scanId || isLoading}
        onClick={handleExport}
      >
        {isLoading ? "Exporting..." : "Export for ML Training"}
      </button>
      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
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
