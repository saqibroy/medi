/** Right panel that lists saved annotations for the active scan. */

import type { Annotation } from "../types/annotation";

interface AnnotationListProps {
  annotations: Annotation[];
  currentSlice: number;
  onDelete: (annotationId: string) => void;
}

export function AnnotationList({ annotations, currentSlice, onDelete }: AnnotationListProps) {
  /** Surface saved labels and make current-slice annotations easy to spot. */
  return (
    <aside className="h-full border-l border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Annotations</h2>
      <div className="space-y-2">
        {annotations.map((annotation) => (
          <article key={annotation.id} className={`rounded-md border p-3 text-sm ${annotation.slice_index === currentSlice ? "border-teal-500 bg-teal-50" : "border-slate-200"}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium text-slate-900">{annotation.label}</p>
                <p className="text-xs text-slate-500">{annotation.annotation_type} | slice {annotation.slice_index}</p>
                <p className="mt-1 text-xs text-slate-500">{annotation.created_by}</p>
              </div>
              <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100" onClick={() => onDelete(annotation.id)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}
