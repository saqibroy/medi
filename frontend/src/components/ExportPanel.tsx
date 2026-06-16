/** ML export preview panel for project and scan datasets. */

import { useState } from "react";

import { exportProjectAsCoco, exportProjectAsCsv, exportProjectAsSegmentation, exportProjectAsYolo, exportProjectForMl } from "../api/projectsApi";
import { exportScanAsCoco, exportScanAsCsv, exportScanAsSegmentation, exportScanAsYolo, exportScanForMl } from "../api/scansApi";

interface ExportPanelProps {
  projectId?: string;
  scanId?: string;
  token: string;
}

type ExportMode = "project" | "scan";
type ExportFormat = "internal" | "csv" | "coco" | "yolo" | "segmentation";
type ExportData = Record<string, unknown>;

export function ExportPanel({ projectId, scanId, token }: ExportPanelProps) {
  /** Let developers inspect exactly what the ML team receives from the API. */
  const [mode, setMode] = useState<ExportMode>("project");
  const [format, setFormat] = useState<ExportFormat>("internal");
  const [exportData, setExportData] = useState<ExportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function metricValue(key: string): number | null {
    const value = exportData?.[key];
    return typeof value === "number" ? value : null;
  }

  function collectionSize(key: string): number | null {
    const value = exportData?.[key];
    return Array.isArray(value) ? value.length : null;
  }

  function primaryMetricLabel(): string {
    if (format === "internal") return "Total";
    if (format === "csv") return "Rows";
    if (format === "coco") return "Images";
    if (format === "segmentation") return "Masks";
    return "Files";
  }

  function primaryMetricValue(): number {
    return metricValue("total_annotations") ?? metricValue("row_count") ?? metricValue("mask_count") ?? collectionSize(format === "coco" ? "images" : "files") ?? 0;
  }

  function secondaryMetricLabel(): string {
    if (format === "internal") return "Approved";
    if (format === "csv") return "File";
    if (format === "coco") return "Boxes";
    if (format === "segmentation") return "Available";
    return "Classes";
  }

  function secondaryMetricValue(): string | number {
    if (format === "csv") return String(exportData?.file_name ?? "CSV");
    if (format === "segmentation") return metricValue("available_mask_count") ?? 0;
    return metricValue("approved_count") ?? collectionSize(format === "coco" ? "annotations" : "classes") ?? 0;
  }

  async function handleExport(): Promise<void> {
    /** Fetch approved annotation data for a training pipeline handoff. */
    if (!token) return;
    if (mode === "project" && !projectId) return;
    if (mode === "scan" && !scanId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response =
        mode === "project"
          ? format === "coco"
            ? await exportProjectAsCoco(projectId as string, token)
            : format === "csv"
              ? await exportProjectAsCsv(projectId as string, token)
            : format === "yolo"
              ? await exportProjectAsYolo(projectId as string, token)
            : format === "segmentation"
              ? await exportProjectAsSegmentation(projectId as string, token)
              : await exportProjectForMl(projectId as string, token)
          : format === "coco"
            ? await exportScanAsCoco(scanId as string, token)
            : format === "csv"
              ? await exportScanAsCsv(scanId as string, token)
            : format === "yolo"
              ? await exportScanAsYolo(scanId as string, token)
            : format === "segmentation"
              ? await exportScanAsSegmentation(scanId as string, token)
              : await exportScanForMl(scanId as string, token);
      setExportData(response as ExportData);
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
      <div className="mb-3 grid grid-cols-5 rounded-md border border-slate-200 bg-white p-1 text-xs font-medium">
        <button className={`rounded px-2 py-1 ${format === "internal" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setFormat("internal")}>
          JSON
        </button>
        <button className={`rounded px-2 py-1 ${format === "csv" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setFormat("csv")}>
          CSV
        </button>
        <button className={`rounded px-2 py-1 ${format === "coco" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setFormat("coco")}>
          COCO
        </button>
        <button className={`rounded px-2 py-1 ${format === "yolo" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setFormat("yolo")}>
          YOLO
        </button>
        <button className={`rounded px-2 py-1 ${format === "segmentation" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setFormat("segmentation")}>
          SEG
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
              <p className="text-xs text-slate-500">{primaryMetricLabel()}</p>
              <p className="font-semibold text-slate-900">{primaryMetricValue()}</p>
            </div>
            <div className="rounded-md bg-white p-2">
              <p className="text-xs text-slate-500">{secondaryMetricLabel()}</p>
              <p className="truncate font-semibold text-emerald-700">{secondaryMetricValue()}</p>
            </div>
            <div className="rounded-md bg-white p-2">
              <p className="text-xs text-slate-500">{format === "internal" ? "Pending" : "Format"}</p>
              <p className="font-semibold text-amber-700">{metricValue("pending_count") ?? String(exportData.export_format ?? format)}</p>
            </div>
          </div>
          <pre className="max-h-56 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(exportData, null, 2)}</pre>
        </div>
      ) : null}
    </section>
  );
}
