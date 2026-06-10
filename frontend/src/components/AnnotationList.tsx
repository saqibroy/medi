/** Right panel that lists saved annotations for the active scan. */

import type { Annotation } from "../types/annotation";

interface AnnotationListProps {
  annotations: Annotation[];
  currentSlice: number;
  onDelete: (annotationId: string) => void;
  onReview: (annotationId: string, status: "approved" | "rejected") => void;
}

const statusBadgeClass = {
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  pending: "bg-amber-100 text-amber-700",
};

export function AnnotationList({ annotations, currentSlice, onDelete, onReview }: AnnotationListProps) {
  /** Surface saved labels and make current-slice annotations easy to spot. */
  return (
    <section className="min-h-0 flex-1 overflow-y-auto border-t border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Annotations</h2>
      <div className="space-y-2">
        {annotations.map((annotation) => (
          <article key={annotation.id} className={`rounded-md border p-3 text-sm ${annotation.slice_index === currentSlice ? "border-teal-500 bg-teal-50" : "border-slate-200"}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{annotation.label}</p>
                <p className="text-xs text-slate-500">{annotation.annotation_type} | slice {annotation.slice_index}</p>
                <p className="mt-1 text-xs text-slate-500">{annotation.created_by}</p>
                {annotation.confidence_score !== null ? <p className="mt-1 text-xs text-slate-500">confidence {annotation.confidence_score.toFixed(2)}</p> : null}
              </div>
              <span className={`rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClass[annotation.review_status]}`}>{annotation.review_status}</span>
            </div>
            {/* Review buttons model the QA workflow before annotations become ML training data. */}
            <div className="mt-3 flex flex-wrap gap-2">
              {annotation.review_status === "pending" ? (
                <>
                  <button className="rounded-md border border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50" onClick={() => onReview(annotation.id, "approved")}>
                    Approve
                  </button>
                  <button className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50" onClick={() => onReview(annotation.id, "rejected")}>
                    Reject
                  </button>
                </>
              ) : null}
              <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100" onClick={() => onDelete(annotation.id)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
