/** React hook for scan selection and slice loading.
 *
 * Hooks are a natural home for data flow: components ask for state and actions,
 * while the hook coordinates API calls, loading flags, and error handling.
 */

import { useCallback, useEffect, useState } from "react";

import { getScanSlice, listScans } from "../api/scansApi";
import type { Scan, SliceImage } from "../types/scan";

export function useScan() {
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
    setIsLoading(true);
    listScans()
      .then((loadedScans) => {
        if (!isMounted) return;
        setScans(loadedScans);
        setSelectedScan(loadedScans[0] ?? null);
      })
      .catch((apiError: Error) => setError(apiError.message))
      .finally(() => setIsLoading(false));
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    /** Every scan or slice change fetches a new image for the viewer. */
    if (!selectedScan) return;
    let isMounted = true;
    setIsLoading(true);
    getScanSlice(selectedScan.id, sliceIndex)
      .then((image) => {
        if (isMounted) setSliceImage(image);
      })
      .catch((apiError: Error) => setError(apiError.message))
      .finally(() => setIsLoading(false));
    return () => {
      isMounted = false;
    };
  }, [selectedScan, sliceIndex]);

  const selectScan = useCallback((scan: Scan) => {
    /** Reset the slice when switching studies so the viewer starts at the front. */
    setSelectedScan(scan);
    setSliceIndex(0);
  }, []);

  return { scans, selectedScan, sliceIndex, sliceImage, isLoading, error, selectScan, setSliceIndex };
}
