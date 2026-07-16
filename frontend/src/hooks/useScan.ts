/** React hook for scan selection and slice loading.
 *
 * Hooks are a natural home for data flow: components ask for state and actions,
 * while the hook coordinates API calls, loading flags, and error handling.
 */

import { useCallback, useEffect, useState } from "react";

import { listProjectScans } from "../api/projectsApi";
import { getScanSlice } from "../api/scansApi";
import type { Scan, SliceImage } from "../types/scan";

export function useScan(projectId?: string, csrfToken?: string) {
  /** Load scans, track selection, and fetch the current slice image. */
  const [scans, setScans] = useState<Scan[]>([]);
  const [selectedScan, setSelectedScan] = useState<Scan | null>(null);
  const [sliceIndex, setSliceIndex] = useState(0);
  const [sliceImage, setSliceImage] = useState<SliceImage | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    /** Initial load populates the left panel and selects the first scan. */
    let isMounted = true;
    if (!projectId || !csrfToken) {
      setScans([]);
      setSelectedScan(null);
      setSliceImage(null);
      setError(null);
      return () => {
        isMounted = false;
      };
    }
    setIsLoading(true);
    setError(null);
    listProjectScans(projectId, csrfToken)
      .then((loadedScans) => {
        if (!isMounted) return;
        setScans(loadedScans);
        setSelectedScan(loadedScans[0] ?? null);
        setSliceImage(null);
      })
      .catch((apiError: Error) => setError(apiError.message))
      .finally(() => setIsLoading(false));
    return () => {
      isMounted = false;
    };
  }, [projectId, csrfToken]);

  useEffect(() => {
    /** Every scan or slice change fetches a new image for the viewer. */
    if (!selectedScan || !csrfToken) return;
    if (selectedScan.ingestion_status !== "ready") {
      setSliceImage(null);
      setError(null);
      return;
    }
    let isMounted = true;
    setIsLoading(true);
    setError(null);
    setSliceImage(null);
    getScanSlice(selectedScan.id, sliceIndex, csrfToken)
      .then((image) => {
        if (isMounted) setSliceImage(image);
      })
      .catch((apiError: Error) => {
        if (!isMounted) return;
        setSliceImage(null);
        setError(apiError.message);
      })
      .finally(() => setIsLoading(false));
    return () => {
      isMounted = false;
    };
  }, [selectedScan, sliceIndex, csrfToken]);

  const selectScan = useCallback((scan: Scan) => {
    /** Reset the slice when switching studies so the viewer starts at the front. */
    setSelectedScan(scan);
    setSliceIndex(0);
  }, []);

  const addScan = useCallback((scan: Scan) => {
    /** Add a newly created scan to the current project list and open it. */
    setScans((current) => [scan, ...current.filter((existingScan) => existingScan.id !== scan.id)]);
    setSelectedScan(scan);
    setSliceIndex(0);
  }, []);

  return { scans, selectedScan, sliceIndex, sliceImage, isLoading, error, selectScan, addScan, setSliceIndex };
}
