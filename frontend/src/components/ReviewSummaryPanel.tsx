/** Compact QA metrics for project and selected-scan review progress. */

import type { ProjectReviewStats, ReviewStats } from "../types/scan";

interface ReviewSummaryPanelProps {
  projectStats: ProjectReviewStats | null;
  scanStats: ReviewStats | null;
  isLoading: boolean;
  error: string | null;
}

function formatRate(value?: number): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function MetricTile({ label, value, tone = "text-slate-950" }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-2 text-center">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function topLabel(stats: ReviewStats | null): string {
  if (!stats) return "None";
  const [label, count] = Object.entries(stats.annotations_by_label).sort((left, right) => right[1] - left[1])[0] ?? [];
  return label && count ? `${label} ${count}` : "None";
}

export function ReviewSummaryPanel({ projectStats, scanStats, isLoading, error }: ReviewSummaryPanelProps) {
  return (
    <div className="border-b border-slate-200 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Review</h2>
        {isLoading ? <span className="text-xs text-slate-400">Loading</span> : null}
      </div>
      {error ? <p className="mb-3 text-xs text-red-700">{error}</p> : null}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <MetricTile label="Project" value={projectStats?.total_annotations ?? 0} />
        <MetricTile label="Complete" value={formatRate(projectStats?.review_completion_rate)} tone="text-teal-700" />
        <MetricTile label="Approved" value={projectStats?.approved_count ?? 0} tone="text-emerald-700" />
        <MetricTile label="Needs work" value={projectStats?.needs_changes_count ?? 0} tone="text-sky-700" />
        <MetricTile label="Pending" value={projectStats?.pending_count ?? 0} tone="text-amber-700" />
        <MetricTile label="Rejected" value={projectStats?.rejected_count ?? 0} tone="text-red-700" />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <MetricTile label="Scan" value={scanStats?.total_annotations ?? 0} />
        <MetricTile label="Scan done" value={formatRate(scanStats?.review_completion_rate)} tone="text-teal-700" />
      </div>
      <div className="mt-3 space-y-1 text-xs text-slate-500">
        <p>Top label: {topLabel(projectStats)}</p>
        <p>Annotated slices: {scanStats?.slices_with_annotations.length ?? 0}</p>
        <p>Annotators: {projectStats?.radiologists_involved.length ?? 0}</p>
      </div>
    </div>
  );
}
