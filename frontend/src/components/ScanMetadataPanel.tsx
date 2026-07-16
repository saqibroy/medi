import { useEffect, useState } from "react";

import { getScanMetadata } from "../api/scansApi";
import type { ScanMetadata } from "../types/scan";

interface ScanMetadataPanelProps {
  scanId?: string;
  token: string;
}

function formatList(values: number[] | null): string {
  return values?.map((value) => Number(value).toFixed(2)).join(" x ") ?? "Not parsed";
}

function formatNumber(value: number | null): string {
  return value === null ? "Not parsed" : String(value);
}

export function ScanMetadataPanel({ scanId, token }: ScanMetadataPanelProps) {
  const [metadata, setMetadata] = useState<ScanMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!scanId || !token) {
      setMetadata(null);
      setError(null);
      return;
    }
    let isMounted = true;
    setIsLoading(true);
    setError(null);
    getScanMetadata(scanId, token)
      .then((response) => {
        if (isMounted) setMetadata(response);
      })
      .catch((apiError: Error) => {
        if (isMounted) setError(apiError.message);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [scanId, token]);

  return (
    <section className="border-b border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Scan Metadata</h2>
      {!scanId ? <p className="text-xs text-slate-500">Select a scan to inspect metadata.</p> : null}
      {isLoading ? <p className="text-xs text-slate-500">Loading metadata...</p> : null}
      {error ? <p className="text-xs text-red-700">{error}</p> : null}
      {metadata && !isLoading ? (
        <div className="space-y-3 text-xs">
          <div>
            <p className="font-medium text-slate-900">{metadata.scan_name}</p>
            <p className="mt-1 text-slate-500">
              {metadata.modality} | {metadata.source_format} | {metadata.ingestion_status}
            </p>
          </div>
          {metadata.ingestion_error ? <p className="rounded-md bg-red-50 p-2 text-red-700">{metadata.ingestion_error}</p> : null}
          <div className="rounded-md bg-slate-50 p-2 text-slate-700">
            <p>Intake decision: {metadata.deidentification_status}</p>
            <p>Profile: {metadata.deidentification_profile_version ?? "Not evaluated"}</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-slate-500">Dimensions</p>
              <p className="font-medium text-slate-900">
                {formatNumber(metadata.width)} x {formatNumber(metadata.height)} x {formatNumber(metadata.depth)}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Slices</p>
              <p className="font-medium text-slate-900">{metadata.num_slices}</p>
            </div>
            <div>
              <p className="text-slate-500">Spacing</p>
              <p className="font-medium text-slate-900">{formatList(metadata.spacing)}</p>
            </div>
            <div>
              <p className="text-slate-500">Window</p>
              <p className="font-medium text-slate-900">
                {formatNumber(metadata.window_center)} / {formatNumber(metadata.window_width)}
              </p>
            </div>
          </div>
          {metadata.metadata ? <pre className="max-h-32 overflow-auto rounded-md bg-slate-950 p-2 text-[11px] text-slate-100">{JSON.stringify(metadata.metadata, null, 2)}</pre> : null}
        </div>
      ) : null}
    </section>
  );
}
