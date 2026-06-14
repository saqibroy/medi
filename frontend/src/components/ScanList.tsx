/** Left panel listing available scans.
 *
 * This component receives data from useScan and focuses only on selection UI,
 * which keeps API and state logic out of presentational components.
 */

import type { Scan } from "../types/scan";

interface ScanListProps {
  scans: Scan[];
  selectedScanId?: string;
  isLoading: boolean;
  hasProject: boolean;
  onSelectScan: (scan: Scan) => void;
}

export function ScanList({ scans, selectedScanId, isLoading, hasProject, onSelectScan }: ScanListProps) {
  /** Render one button per scan with modality and slice metadata. */
  return (
    <section className="p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Scans</h2>
      {isLoading ? <p className="text-xs text-slate-500">Loading scans...</p> : null}
      {!isLoading && !hasProject ? <p className="text-xs text-slate-500">Select or create a project to load scans.</p> : null}
      {!isLoading && hasProject && scans.length === 0 ? <p className="text-xs text-slate-500">No scans in this project yet.</p> : null}
      <div className="space-y-2">
        {scans.map((scan) => (
          <button
            key={scan.id}
            className={`w-full rounded-md border p-3 text-left text-sm transition ${
              scan.id === selectedScanId ? "border-teal-500 bg-teal-50" : "border-slate-200 hover:bg-slate-50"
            }`}
            onClick={() => onSelectScan(scan)}
          >
            <span className="block font-medium text-slate-900">{scan.name}</span>
            <span className="mt-1 block text-xs text-slate-500">
              {scan.modality} | {scan.num_slices} slices | {scan.source_format} | {scan.ingestion_status}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
