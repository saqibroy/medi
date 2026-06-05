/** Cornerstone3D viewer lifecycle hook.
 *
 * Cornerstone3D's RenderingEngine manages one or more viewports. React owns the
 * DOM node; this hook bridges React's mount/unmount lifecycle to Cornerstone's
 * imperative setup and cleanup.
 */

import { useEffect, useRef } from "react";
import { RenderingEngine, Enums, init } from "@cornerstonejs/core";

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
