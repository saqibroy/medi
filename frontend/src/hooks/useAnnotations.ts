/** React hook for annotation state and persistence.
 *
 * The viewer produces geometry, this hook sends it to FastAPI, and the response
 * becomes the single source of truth shown in overlays and the right panel.
 */

import { useCallback, useEffect, useState } from "react";

import { createAnnotation, deleteAnnotation, deleteSegmentationMask, getSegmentationMask, listAnnotationHistory, listAnnotations, reviewAnnotation, updateAnnotation, uploadSegmentationMask } from "../api/annotationsApi";
import type { Annotation, AnnotationCreate, AnnotationHistory, AnnotationUpdate, ReviewStatus, SegmentationMask, SegmentationMaskImage } from "../types/annotation";

export function useAnnotations(scanId?: string, csrfToken?: string, reviewerName = "Reviewer") {
  /** Load and mutate annotations for the selected scan. */
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [annotationHistory, setAnnotationHistory] = useState<AnnotationHistory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  const refresh = useCallback(() => {
    /** Refresh keeps overlays aligned with database state after mutations. */
    if (!scanId || !csrfToken) {
      setAnnotations([]);
      return;
    }
    listAnnotations(csrfToken, scanId)
      .then(setAnnotations)
      .catch((apiError: Error) => setError(apiError.message));
  }, [scanId, csrfToken]);

  useEffect(() => {
    /** Re-run when the user selects a different scan. */
    refresh();
  }, [refresh]);

  const saveAnnotation = useCallback(
    async (payload: AnnotationCreate): Promise<Annotation | undefined> => {
      /** Persist one annotation and append the server-confirmed version. */
      if (!csrfToken) return undefined;
      const saved = await createAnnotation(payload, csrfToken);
      setAnnotations((current) => [saved, ...current]);
      return saved;
    },
    [csrfToken],
  );

  const saveSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number, mask: Blob): Promise<SegmentationMask | undefined> => {
    /** Store mask PNG bytes for an existing segmentation annotation. */
    if (!csrfToken) return undefined;
    return uploadSegmentationMask(annotationId, sliceIndex, mask, csrfToken);
  }, [csrfToken]);

  const loadSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number): Promise<SegmentationMaskImage | null> => {
    /** Load saved mask bytes for the viewer overlay. */
    if (!csrfToken) return null;
    return getSegmentationMask(annotationId, sliceIndex, csrfToken);
  }, [csrfToken]);

  const removeSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number): Promise<void> => {
    /** Remove saved mask bytes without deleting the annotation row. */
    if (!csrfToken) return;
    await deleteSegmentationMask(annotationId, sliceIndex, csrfToken);
  }, [csrfToken]);

  const loadAnnotationHistory = useCallback(async (annotationId?: string | null) => {
    /** Load audit entries for the selected annotation detail view. */
    if (!csrfToken || !annotationId) {
      setAnnotationHistory([]);
      setHistoryError(null);
      setIsHistoryLoading(false);
      return;
    }
    setIsHistoryLoading(true);
    setHistoryError(null);
    try {
      setAnnotationHistory(await listAnnotationHistory(annotationId, csrfToken));
    } catch (apiError) {
      setHistoryError(apiError instanceof Error ? apiError.message : "Could not load annotation history");
      setAnnotationHistory([]);
    } finally {
      setIsHistoryLoading(false);
    }
  }, [csrfToken]);

  const removeAnnotation = useCallback(async (annotationId: string) => {
    /** Delete in the backend first, then update UI state optimistically. */
    if (!csrfToken) return;
    await deleteAnnotation(annotationId, csrfToken);
    setAnnotations((current) => current.filter((annotation) => annotation.id !== annotationId));
  }, [csrfToken]);

  const updateExistingAnnotation = useCallback(async (annotationId: string, payload: AnnotationUpdate) => {
    /** Persist edits and replace the local row with the updated annotation. */
    if (!csrfToken) return;
    const updated = await updateAnnotation(annotationId, payload, csrfToken);
    setAnnotations((current) => current.map((annotation) => (annotation.id === updated.id ? updated : annotation)));
  }, [csrfToken]);

  const reviewExistingAnnotation = useCallback(async (annotationId: string, status: ReviewStatus, notes?: string | null) => {
    /** Save QA decisions and replace the local row with the reviewed version. */
    if (!csrfToken) return;
    const reviewed = await reviewAnnotation(annotationId, reviewerName, status, csrfToken, notes ?? null);
    setAnnotations((current) => current.map((annotation) => (annotation.id === reviewed.id ? reviewed : annotation)));
  }, [reviewerName, csrfToken]);

  return {
    annotations,
    annotationHistory,
    error,
    historyError,
    isHistoryLoading,
    refresh,
    loadAnnotationHistory,
    saveAnnotation,
    updateExistingAnnotation,
    removeAnnotation,
    reviewExistingAnnotation,
    saveSegmentationMask,
    loadSegmentationMask,
    removeSegmentationMask,
  };
}
