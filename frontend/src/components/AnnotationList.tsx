/** Right panel that lists saved annotations for the active scan. */

import { useMemo, useState } from "react";

import type { Annotation, ReviewStatus } from "../types/annotation";
import type { Label } from "../types/project";

interface AnnotationListProps {
  annotations: Annotation[];
  labels: Label[];
  currentSlice: number;
  selectedAnnotationId: string | null;
  canReview: boolean;
  canDelete: boolean;
  onSelectAnnotation: (annotationId: string) => void;
  onDelete: (annotationId: string) => void;
  onReview: (annotationId: string, status: ReviewStatus) => void;
}

const statusBadgeClass = {
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  pending: "bg-amber-100 text-amber-700",
  needs_changes: "bg-sky-100 text-sky-700",
};

const reviewFilters: Array<{ value: "all" | ReviewStatus; label: string }> = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "needs_changes", label: "Needs changes" },
  { value: "rejected", label: "Rejected" },
];

export function AnnotationList({ annotations, labels, currentSlice, selectedAnnotationId, canReview, canDelete, onSelectAnnotation, onDelete, onReview }: AnnotationListProps) {
  /** Surface saved labels and make current-slice annotations easy to spot. */
  const [reviewFilter, setReviewFilter] = useState<"all" | ReviewStatus>("all");
  const labelColorById = new Map(labels.map((label) => [label.id, label.color]));
  const reviewCounts = useMemo(
    () => ({
      all: annotations.length,
      pending: annotations.filter((annotation) => annotation.review_status === "pending").length,
      approved: annotations.filter((annotation) => annotation.review_status === "approved").length,
      needs_changes: annotations.filter((annotation) => annotation.review_status === "needs_changes").length,
      rejected: annotations.filter((annotation) => annotation.review_status === "rejected").length,
    }),
    [annotations],
  );
  const visibleAnnotations = reviewFilter === "all" ? annotations : annotations.filter((annotation) => annotation.review_status === reviewFilter);

  return (
    <section className="min-h-0 flex-1 overflow-y-auto border-t border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Annotations</h2>
      <div className="mb-3 flex flex-wrap gap-1">
        {reviewFilters.map((filter) => (
          <button
            className={`rounded-md border px-2 py-1 text-xs font-medium ${
              reviewFilter === filter.value ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
            key={filter.value}
            onClick={() => setReviewFilter(filter.value)}
            type="button"
          >
            {filter.label} {reviewCounts[filter.value]}
          </button>
        ))}
      </div>
      {annotations.length === 0 ? <p className="text-xs text-slate-500">No annotations for the selected scan.</p> : null}
      {annotations.length > 0 && visibleAnnotations.length === 0 ? <p className="text-xs text-slate-500">No annotations match this review filter.</p> : null}
      <div className="space-y-2">
        {visibleAnnotations.map((annotation) => (
          <article
            key={annotation.id}
            className={`cursor-pointer rounded-md border p-3 text-sm ${annotation.id === selectedAnnotationId ? "border-orange-500 bg-orange-50" : annotation.slice_index === currentSlice ? "border-teal-500 bg-teal-50" : "border-slate-200"}`}
            onClick={() => onSelectAnnotation(annotation.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") onSelectAnnotation(annotation.id);
            }}
            role="button"
            tabIndex={0}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-200" style={{ backgroundColor: labelColorById.get(annotation.label_id ?? "") ?? "#94a3b8" }} />
                  <p className="truncate font-medium text-slate-900">{annotation.label}</p>
                </div>
                <p className="text-xs text-slate-500">{annotation.annotation_type} | slice {annotation.slice_index}</p>
                <p className="mt-1 text-xs text-slate-500">{annotation.created_by}</p>
                {annotation.confidence_score !== null ? <p className="mt-1 text-xs text-slate-500">confidence {annotation.confidence_score.toFixed(2)}</p> : null}
              </div>
              <span className={`rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClass[annotation.review_status]}`}>{annotation.review_status}</span>
            </div>
            {/* Review buttons model the QA workflow before annotations become ML training data. */}
            <div className="mt-3 flex flex-wrap gap-2">
              {canReview ? (
                <>
                  {annotation.review_status !== "approved" ? (
                    <button className="rounded-md border border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50" onClick={() => onReview(annotation.id, "approved")}>
                      Approve
                    </button>
                  ) : null}
                  {annotation.review_status !== "needs_changes" ? (
                    <button className="rounded-md border border-sky-300 px-2 py-1 text-xs text-sky-700 hover:bg-sky-50" onClick={() => onReview(annotation.id, "needs_changes")}>
                      Needs changes
                    </button>
                  ) : null}
                  {annotation.review_status !== "rejected" ? (
                    <button className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50" onClick={() => onReview(annotation.id, "rejected")}>
                      Reject
                    </button>
                  ) : null}
                </>
              ) : null}
              {canDelete ? (
                <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100" onClick={() => onDelete(annotation.id)}>
                  Delete
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
