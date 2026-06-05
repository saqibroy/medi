/** Main viewer panel with Cornerstone3D initialization and canvas drawing.
 *
 * Real medical imaging viewers usually render DICOM imageIds through
 * Cornerstone3D. This teaching project initializes Cornerstone to show the
 * lifecycle pattern, then draws the simulated backend PNG and overlays on a
 * normal canvas so bounding-box capture stays understandable.
 */

import { MouseEvent, useEffect, useMemo, useRef, useState } from "react";

import { useViewer } from "../hooks/useViewer";
import type { Annotation, AnnotationCreate, BoundingBoxCoordinates } from "../types/annotation";
import type { Scan, SliceImage } from "../types/scan";

interface ViewerPanelProps {
  scan: Scan | null;
  sliceImage: SliceImage | null;
  sliceIndex: number;
  annotations: Annotation[];
  label: string;
  annotationType: AnnotationCreate["annotation_type"];
  createdBy: string;
  onSaveAnnotation: (payload: AnnotationCreate) => Promise<void>;
}

interface DraftBox extends BoundingBoxCoordinates {
  isDrawing: boolean;
}

export function ViewerPanel(props: ViewerPanelProps) {
  /** Capture mouse gestures, render images, and save bounding boxes. */
  const { elementRef } = useViewer();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [draftBox, setDraftBox] = useState<DraftBox | null>(null);

  const currentSliceAnnotations = useMemo(
    () => props.annotations.filter((annotation) => annotation.slice_index === props.sliceIndex),
    [props.annotations, props.sliceIndex],
  );

  useEffect(() => {
    /** Draw the current slice and overlays whenever source data changes. */
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !props.sliceImage) return;

    const image = new Image();
    image.onload = () => {
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      context.strokeStyle = "#14b8a6";
      context.lineWidth = 3;
      currentSliceAnnotations.forEach((annotation) => {
        const box = annotation.coordinates as Partial<BoundingBoxCoordinates>;
        if (annotation.annotation_type === "bounding_box" && box.x !== undefined) {
          context.strokeRect(box.x, box.y ?? 0, box.width ?? 0, box.height ?? 0);
        }
      });
      if (draftBox?.isDrawing) {
        context.strokeStyle = "#f97316";
        context.strokeRect(draftBox.x, draftBox.y, draftBox.width, draftBox.height);
      }
    };
    image.src = `data:image/png;base64,${props.sliceImage.image_base64}`;
  }, [props.sliceImage, currentSliceAnnotations, draftBox]);

  function canvasPoint(event: MouseEvent<HTMLCanvasElement>) {
    /** Convert browser coordinates into canvas coordinates used by annotation JSON. */
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * canvas.width),
      y: Math.round(((event.clientY - rect.top) / rect.height) * canvas.height),
    };
  }

  function handleMouseDown(event: MouseEvent<HTMLCanvasElement>): void {
    /** Start a new bounding box draft at the first mouse position. */
    const point = canvasPoint(event);
    setDraftBox({ x: point.x, y: point.y, width: 0, height: 0, isDrawing: true });
  }

  function handleMouseMove(event: MouseEvent<HTMLCanvasElement>): void {
    /** Update width and height as the user drags across the image. */
    if (!draftBox?.isDrawing) return;
    const point = canvasPoint(event);
    setDraftBox({ ...draftBox, width: point.x - draftBox.x, height: point.y - draftBox.y });
  }

  async function handleMouseUp(): Promise<void> {
    /** Normalize and save the completed draft box through the annotation API. */
    if (!props.scan || !draftBox) return;
    const coordinates = {
      x: Math.min(draftBox.x, draftBox.x + draftBox.width),
      y: Math.min(draftBox.y, draftBox.y + draftBox.height),
      width: Math.abs(draftBox.width),
      height: Math.abs(draftBox.height),
    };
    setDraftBox(null);
    if (coordinates.width < 4 || coordinates.height < 4) return;
    await props.onSaveAnnotation({
      scan_id: props.scan.id,
      label: props.label,
      annotation_type: props.annotationType,
      coordinates,
      slice_index: props.sliceIndex,
      created_by: props.createdBy,
    });
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div ref={elementRef} className="hidden" />
      <div className="flex min-h-0 flex-1 items-center justify-center p-4">
        {props.scan && props.sliceImage ? (
          <canvas
            ref={canvasRef}
            width={512}
            height={512}
            className="aspect-square max-h-full max-w-full cursor-crosshair rounded-md border border-slate-700 bg-black"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          />
        ) : (
          <p className="text-sm text-slate-300">Start the backend and seed data to load scans.</p>
        )}
      </div>
    </main>
  );
}
