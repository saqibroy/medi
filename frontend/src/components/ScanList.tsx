/** Left panel listing available scans.
 *
 * This component receives data from useScan and focuses only on selection UI,
 * which keeps API and state logic out of presentational components.
 */

import type { Scan } from "../types/scan";

interface ScanListProps {
  scans: Scan[];
  selectedScanId?: string;
  onSelectScan: (scan: Scan) => void;
}

export function ScanList({ scans, selectedScanId, onSelectScan }: ScanListProps) {
  /** Render one button per scan with modality and slice metadata. */
  return (
    <aside className="h-full border-r border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Scans</h2>
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
              {scan.modality} | {scan.num_slices} slices
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
