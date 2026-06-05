/** Application shell for the medical image annotation frontend.
 *
 * App composes data hooks and presentational components so a developer can trace
 * the full flow from API data to viewer state to saved annotation overlays.
 */

import { useState } from "react";

import { AnnotationList } from "./components/AnnotationList";
import { AnnotationTools } from "./components/AnnotationTools";
import { ScanList } from "./components/ScanList";
import { SliceNavigator } from "./components/SliceNavigator";
import { ViewerPanel } from "./components/ViewerPanel";
import { useAnnotations } from "./hooks/useAnnotations";
import { useScan } from "./hooks/useScan";
import type { AnnotationType } from "./types/annotation";

export default function App() {
  /** Own global page state and pass focused props down to child components. */
  const { scans, selectedScan, sliceIndex, sliceImage, error, selectScan, setSliceIndex } = useScan();
  const { annotations, saveAnnotation, removeAnnotation } = useAnnotations(selectedScan?.id);
  const [label, setLabel] = useState("tumour");
  const [annotationType, setAnnotationType] = useState<AnnotationType>("bounding_box");
  const [createdBy, setCreatedBy] = useState("Dr. Interview");

  return (
    <div className="grid h-full grid-cols-[280px_1fr_320px] overflow-hidden">
      <ScanList scans={scans} selectedScanId={selectedScan?.id} onSelectScan={selectScan} />
      <div className="flex min-w-0 flex-col">
        <AnnotationTools
          label={label}
          annotationType={annotationType}
          createdBy={createdBy}
          onLabelChange={setLabel}
          onAnnotationTypeChange={setAnnotationType}
          onCreatedByChange={setCreatedBy}
        />
        {error ? <div className="bg-red-50 p-2 text-sm text-red-700">{error}</div> : null}
        <ViewerPanel
          scan={selectedScan}
          sliceImage={sliceImage}
          sliceIndex={sliceIndex}
          annotations={annotations}
          label={label}
          annotationType={annotationType}
          createdBy={createdBy}
          onSaveAnnotation={saveAnnotation}
        />
        <SliceNavigator sliceIndex={sliceIndex} maxSliceIndex={Math.max((selectedScan?.num_slices ?? 1) - 1, 0)} onSliceChange={setSliceIndex} />
      </div>
      <AnnotationList annotations={annotations} currentSlice={sliceIndex} onDelete={removeAnnotation} />
    </div>
  );
}
