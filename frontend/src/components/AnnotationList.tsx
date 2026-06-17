/** Right panel that lists saved annotations for the active scan. */

import { useEffect, useMemo, useState } from "react";

import type { Annotation, AnnotationHistory, AnnotationUpdate, ReviewStatus } from "../types/annotation";
import type { Label } from "../types/project";
import type { User } from "../types/user";

interface AnnotationListProps {
  annotations: Annotation[];
  annotationHistory: AnnotationHistory[];
  historyError: string | null;
  isHistoryLoading: boolean;
  labels: Label[];
  users: User[];
  currentSlice: number;
  selectedAnnotationId: string | null;
  canAnnotate: boolean;
  canReview: boolean;
  canDelete: boolean;
  onSelectAnnotation: (annotationId: string) => void;
  onDelete: (annotationId: string) => void;
  onUpdateAnnotation: (annotationId: string, payload: AnnotationUpdate) => Promise<void>;
  onReview: (annotationId: string, status: ReviewStatus, notes?: string | null) => Promise<void>;
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

const reviewStatusOptions: ReviewStatus[] = ["pending", "approved", "needs_changes", "rejected"];

function formatDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function summarizeHistory(entry: AnnotationHistory): string {
  return entry.changed_fields.map((field) => field.replace(/_/g, " ")).join(", ");
}

export function AnnotationList({
  annotations,
  annotationHistory,
  historyError,
  isHistoryLoading,
  labels,
  users,
  currentSlice,
  selectedAnnotationId,
  canAnnotate,
  canReview,
  canDelete,
  onSelectAnnotation,
  onDelete,
  onUpdateAnnotation,
  onReview,
}: AnnotationListProps) {
  /** Surface saved labels and make current-slice annotations easy to spot. */
  const [reviewFilter, setReviewFilter] = useState<"all" | ReviewStatus>("all");
  const [labelIdDraft, setLabelIdDraft] = useState("");
  const [assigneeIdDraft, setAssigneeIdDraft] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [reviewStatusDraft, setReviewStatusDraft] = useState<ReviewStatus>("pending");
  const [isMetadataSaving, setIsMetadataSaving] = useState(false);
  const [isReviewSaving, setIsReviewSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const labelColorById = new Map(labels.map((label) => [label.id, label.color]));
  const userNameById = new Map(users.map((workspaceUser) => [workspaceUser.id, workspaceUser.full_name]));
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
  const selectedAnnotation = annotations.find((annotation) => annotation.id === selectedAnnotationId) ?? null;

  useEffect(() => {
    if (!selectedAnnotation) return;
    const matchingLabel = labels.find((label) => label.id === selectedAnnotation.label_id || label.name === selectedAnnotation.label);
    setLabelIdDraft(matchingLabel?.id ?? selectedAnnotation.label_id ?? "");
    setAssigneeIdDraft(selectedAnnotation.assigned_to_user_id ?? "");
    setNotesDraft(selectedAnnotation.notes ?? "");
    setReviewStatusDraft(selectedAnnotation.review_status);
    setEditError(null);
  }, [labels, selectedAnnotation]);

  async function handleSaveMetadata(event: React.MouseEvent<HTMLButtonElement>): Promise<void> {
    event.stopPropagation();
    if (!selectedAnnotation || !canAnnotate) return;
    const selectedLabel = labels.find((label) => label.id === labelIdDraft);
    const payload: AnnotationUpdate = { assigned_to_user_id: assigneeIdDraft || null, notes: notesDraft.trim() || null };
    if (selectedLabel) {
      payload.label_id = selectedLabel.id;
      payload.label = selectedLabel.name;
    }
    setIsMetadataSaving(true);
    setEditError(null);
    try {
      await onUpdateAnnotation(selectedAnnotation.id, payload);
    } catch (error) {
      setEditError(error instanceof Error ? error.message : "Could not save annotation edits");
    } finally {
      setIsMetadataSaving(false);
    }
  }

  async function handleSaveReview(event: React.MouseEvent<HTMLButtonElement>): Promise<void> {
    event.stopPropagation();
    if (!selectedAnnotation || !canReview) return;
    setIsReviewSaving(true);
    setEditError(null);
    try {
      await onReview(selectedAnnotation.id, reviewStatusDraft, notesDraft.trim() || null);
    } catch (error) {
      setEditError(error instanceof Error ? error.message : "Could not save review edits");
    } finally {
      setIsReviewSaving(false);
    }
  }

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
                <p className="mt-1 text-xs text-slate-500">Assigned {annotation.assigned_to_user_id ? userNameById.get(annotation.assigned_to_user_id) ?? "Unknown user" : "Unassigned"}</p>
                {annotation.confidence_score !== null ? <p className="mt-1 text-xs text-slate-500">confidence {annotation.confidence_score.toFixed(2)}</p> : null}
              </div>
              <span className={`rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClass[annotation.review_status]}`}>{annotation.review_status}</span>
            </div>
            <div className="mt-3 space-y-1 border-t border-slate-100 pt-2 text-xs text-slate-500">
              <p>Created {formatDateTime(annotation.created_at)}</p>
              <p>Updated {formatDateTime(annotation.updated_at)}</p>
              {annotation.reviewed_at ? <p>Reviewed {formatDateTime(annotation.reviewed_at)}{annotation.reviewer ? ` by ${annotation.reviewer}` : ""}</p> : null}
              {annotation.notes ? <p className="rounded-md bg-slate-50 p-2 text-slate-700">{annotation.notes}</p> : null}
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
            {annotation.id === selectedAnnotationId ? (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <div className="mb-3 space-y-3 rounded-md border border-slate-200 bg-white p-3" onClick={(event) => event.stopPropagation()}>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Edit selected</h3>
                  <label className="block text-xs font-medium text-slate-600">
                    Label
                    <select
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 disabled:bg-slate-100 disabled:text-slate-500"
                      disabled={!canAnnotate || labels.length === 0 || isMetadataSaving}
                      onChange={(event) => setLabelIdDraft(event.target.value)}
                      value={labelIdDraft}
                    >
                      {labels.length === 0 ? <option value="">No labels</option> : null}
                      {labels.map((label) => (
                        <option key={label.id} value={label.id}>
                          {label.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs font-medium text-slate-600">
                    Assignee
                    <select
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 disabled:bg-slate-100 disabled:text-slate-500"
                      disabled={!canAnnotate || isMetadataSaving}
                      onChange={(event) => setAssigneeIdDraft(event.target.value)}
                      value={assigneeIdDraft}
                    >
                      <option value="">Unassigned</option>
                      {users.map((workspaceUser) => (
                        <option key={workspaceUser.id} value={workspaceUser.id}>
                          {workspaceUser.full_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs font-medium text-slate-600">
                    Status
                    <select
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 disabled:bg-slate-100 disabled:text-slate-500"
                      disabled={!canReview || isReviewSaving}
                      onChange={(event) => setReviewStatusDraft(event.target.value as ReviewStatus)}
                      value={reviewStatusDraft}
                    >
                      {reviewStatusOptions.map((status) => (
                        <option key={status} value={status}>
                          {status.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs font-medium text-slate-600">
                    Notes
                    <textarea
                      className="mt-1 min-h-20 w-full resize-y rounded-md border border-slate-300 px-2 py-2 text-sm text-slate-900 disabled:bg-slate-100 disabled:text-slate-500"
                      disabled={(!canAnnotate && !canReview) || isMetadataSaving || isReviewSaving}
                      onChange={(event) => setNotesDraft(event.target.value)}
                      value={notesDraft}
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {canAnnotate ? (
                      <button
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isMetadataSaving || labels.length === 0}
                        onClick={handleSaveMetadata}
                        type="button"
                      >
                        {isMetadataSaving ? "Saving..." : "Save details"}
                      </button>
                    ) : null}
                    {canReview ? (
                      <button
                        className="rounded-md border border-teal-300 px-3 py-1.5 text-xs font-medium text-teal-700 hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isReviewSaving}
                        onClick={handleSaveReview}
                        type="button"
                      >
                        {isReviewSaving ? "Saving..." : "Save review"}
                      </button>
                    ) : null}
                  </div>
                  {editError ? <p className="text-xs text-red-700">{editError}</p> : null}
                </div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">History</h3>
                {isHistoryLoading ? <p className="mt-2 text-xs text-slate-500">Loading history...</p> : null}
                {historyError ? <p className="mt-2 text-xs text-red-700">{historyError}</p> : null}
                {!isHistoryLoading && !historyError && annotationHistory.length === 0 ? <p className="mt-2 text-xs text-slate-500">No recorded changes yet.</p> : null}
                <div className="mt-2 space-y-2">
                  {annotationHistory.map((entry) => (
                    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs" key={entry.id}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-medium text-slate-700">{entry.action}</p>
                        <p className="shrink-0 text-slate-500">{formatDateTime(entry.created_at)}</p>
                      </div>
                      <p className="mt-1 text-slate-500">{summarizeHistory(entry)}</p>
                      {entry.changed_by_user_id ? <p className="mt-1 truncate text-slate-400">User {entry.changed_by_user_id}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
