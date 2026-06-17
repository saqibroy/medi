/** React hook for annotation state and persistence.
 *
 * The viewer produces geometry, this hook sends it to FastAPI, and the response
 * becomes the single source of truth shown in overlays and the right panel.
 */

import { useCallback, useEffect, useState } from "react";

import { createAnnotation, deleteAnnotation, deleteSegmentationMask, getSegmentationMask, listAnnotationHistory, listAnnotations, reviewAnnotation, updateAnnotation, uploadSegmentationMask } from "../api/annotationsApi";
import type { Annotation, AnnotationCreate, AnnotationHistory, AnnotationUpdate, ReviewStatus, SegmentationMask, SegmentationMaskImage } from "../types/annotation";

export function useAnnotations(scanId?: string, token?: string, reviewerName = "Reviewer") {
  /** Load and mutate annotations for the selected scan. */
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [annotationHistory, setAnnotationHistory] = useState<AnnotationHistory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  const refresh = useCallback(() => {
    /** Refresh keeps overlays aligned with database state after mutations. */
    if (!scanId || !token) {
      setAnnotations([]);
      return;
    }
    listAnnotations(token, scanId)
      .then(setAnnotations)
      .catch((apiError: Error) => setError(apiError.message));
  }, [scanId, token]);

  useEffect(() => {
    /** Re-run when the user selects a different scan. */
    refresh();
  }, [refresh]);

  const saveAnnotation = useCallback(
    async (payload: AnnotationCreate): Promise<Annotation | undefined> => {
      /** Persist one annotation and append the server-confirmed version. */
      if (!token) return undefined;
      const saved = await createAnnotation(payload, token);
      setAnnotations((current) => [saved, ...current]);
      return saved;
    },
    [token],
  );

  const saveSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number, mask: Blob): Promise<SegmentationMask | undefined> => {
    /** Store mask PNG bytes for an existing segmentation annotation. */
    if (!token) return undefined;
    return uploadSegmentationMask(annotationId, sliceIndex, mask, token);
  }, [token]);

  const loadSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number): Promise<SegmentationMaskImage | null> => {
    /** Load saved mask bytes for the viewer overlay. */
    if (!token) return null;
    return getSegmentationMask(annotationId, sliceIndex, token);
  }, [token]);

  const removeSegmentationMask = useCallback(async (annotationId: string, sliceIndex: number): Promise<void> => {
    /** Remove saved mask bytes without deleting the annotation row. */
    if (!token) return;
    await deleteSegmentationMask(annotationId, sliceIndex, token);
  }, [token]);

  const loadAnnotationHistory = useCallback(async (annotationId?: string | null) => {
    /** Load audit entries for the selected annotation detail view. */
    if (!token || !annotationId) {
      setAnnotationHistory([]);
      setHistoryError(null);
      setIsHistoryLoading(false);
      return;
    }
    setIsHistoryLoading(true);
    setHistoryError(null);
    try {
      setAnnotationHistory(await listAnnotationHistory(annotationId, token));
    } catch (apiError) {
      setHistoryError(apiError instanceof Error ? apiError.message : "Could not load annotation history");
      setAnnotationHistory([]);
    } finally {
      setIsHistoryLoading(false);
    }
  }, [token]);

  const removeAnnotation = useCallback(async (annotationId: string) => {
    /** Delete in the backend first, then update UI state optimistically. */
    if (!token) return;
    await deleteAnnotation(annotationId, token);
    setAnnotations((current) => current.filter((annotation) => annotation.id !== annotationId));
  }, [token]);

  const updateExistingAnnotation = useCallback(async (annotationId: string, payload: AnnotationUpdate) => {
    /** Persist edits and replace the local row with the updated annotation. */
    if (!token) return;
    const updated = await updateAnnotation(annotationId, payload, token);
    setAnnotations((current) => current.map((annotation) => (annotation.id === updated.id ? updated : annotation)));
  }, [token]);

  const reviewExistingAnnotation = useCallback(async (annotationId: string, status: ReviewStatus, notes?: string | null) => {
    /** Save QA decisions and replace the local row with the reviewed version. */
    if (!token) return;
    const reviewed = await reviewAnnotation(annotationId, reviewerName, status, token, notes ?? null);
    setAnnotations((current) => current.map((annotation) => (annotation.id === reviewed.id ? reviewed : annotation)));
  }, [reviewerName, token]);

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
