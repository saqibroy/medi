/** React hook for annotation state and persistence.
 *
 * The viewer produces geometry, this hook sends it to FastAPI, and the response
 * becomes the single source of truth shown in overlays and the right panel.
 */

import { useCallback, useEffect, useState } from "react";

import { createAnnotation, deleteAnnotation, listAnnotations, reviewAnnotation } from "../api/annotationsApi";
import type { Annotation, AnnotationCreate, ReviewStatus } from "../types/annotation";

export function useAnnotations(scanId?: string, token?: string, reviewerName = "Reviewer") {
  /** Load and mutate annotations for the selected scan. */
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [error, setError] = useState<string | null>(null);

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
    async (payload: AnnotationCreate) => {
      /** Persist one annotation and append the server-confirmed version. */
      if (!token) return;
      const saved = await createAnnotation(payload, token);
      setAnnotations((current) => [saved, ...current]);
    },
    [token],
  );

  const removeAnnotation = useCallback(async (annotationId: string) => {
    /** Delete in the backend first, then update UI state optimistically. */
    if (!token) return;
    await deleteAnnotation(annotationId, token);
    setAnnotations((current) => current.filter((annotation) => annotation.id !== annotationId));
  }, [token]);

  const reviewExistingAnnotation = useCallback(async (annotationId: string, status: ReviewStatus) => {
    /** Save QA decisions and replace the local row with the reviewed version. */
    if (!token) return;
    const reviewed = await reviewAnnotation(annotationId, reviewerName, status, token, null);
    setAnnotations((current) => current.map((annotation) => (annotation.id === reviewed.id ? reviewed : annotation)));
  }, [reviewerName, token]);

  return { annotations, error, refresh, saveAnnotation, removeAnnotation, reviewExistingAnnotation };
}
