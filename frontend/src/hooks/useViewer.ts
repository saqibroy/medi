/** Cornerstone3D viewer lifecycle hook.
 *
 * Cornerstone3D's RenderingEngine manages one or more viewports. React owns the
 * DOM node; this hook bridges React's mount/unmount lifecycle to Cornerstone's
 * imperative setup and cleanup.
 */

import { useEffect, useRef } from "react";
import { RenderingEngine, Enums, init } from "@cornerstonejs/core";

/**
 * In a production DICOM viewer the image source would usually be an imageId,
 * for example: wadouri:https://server/wado?studyUID=...&seriesUID=...&objectUID=...
 * Cornerstone image loaders parse that string, fetch DICOM bytes, decode pixels,
 * and hand the result to a STACK viewport for 2D slice navigation.
 *
 * Tool packages such as cornerstoneTools register interaction tools separately:
 * a real app might register BoundingBoxTool for detection labels and LengthTool
 * for measurements, then bind those tools to mouse buttons or keyboard modes.
 *
 * This hook still leaves canvas rendering to ViewerPanel so the learning repo
 * stays readable. The important lifecycle detail is cleanup: RenderingEngine
 * owns WebGL/canvas resources, so destroy() on unmount prevents GPU memory leaks
 * when React remounts viewers or navigates between studies.
 *
 * STACK viewports show a sequence of 2D imageIds, one slice at a time. VOLUME
 * viewports load a reconstructed 3D volume and can render orthogonal planes or
 * 3D views, which is more powerful but also heavier to configure and cache.
 */
export function useViewer() {
  /** Return a DOM ref that ViewerPanel attaches to the viewport element. */
  const elementRef = useRef<HTMLDivElement | null>(null);
  const renderingEngineRef = useRef<RenderingEngine | null>(null);

  useEffect(() => {
    /** Initialize Cornerstone once after React has created the viewport div. */
    const element = elementRef.current;
    if (!element) return;

    let disposed = false;
    const renderingEngineId = "learning-rendering-engine";
    const viewportId = "slice-viewport";

    init();
    if (!disposed && elementRef.current) {
      const renderingEngine = new RenderingEngine(renderingEngineId);
      renderingEngine.enableElement({
        viewportId,
        element: elementRef.current,
        type: Enums.ViewportType.STACK,
      });
      renderingEngineRef.current = renderingEngine;
    }

    return () => {
      /** Cleanup matters because canvas/WebGL libraries can retain GPU memory. */
      disposed = true;
      renderingEngineRef.current?.destroy();
      renderingEngineRef.current = null;
    };
  }, []);

  return { elementRef, renderingEngineRef };
}
