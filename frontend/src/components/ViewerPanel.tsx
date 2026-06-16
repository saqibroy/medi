/** Main viewer panel with Cornerstone3D initialization and canvas drawing.
 *
 * Real medical imaging viewers usually render DICOM imageIds through
 * Cornerstone3D. This teaching project initializes Cornerstone to show the
 * lifecycle pattern, then draws the simulated backend PNG and overlays on a
 * normal canvas so bounding-box capture stays understandable.
 */

import { MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useViewer } from "../hooks/useViewer";
import type { Annotation, AnnotationCreate, AnnotationUpdate, BoundingBoxCoordinates, PolygonCoordinates, PolygonPoint } from "../types/annotation";
import type { Scan, SliceImage } from "../types/scan";

interface ViewerPanelProps {
  scan: Scan | null;
  sliceImage: SliceImage | null;
  sliceIndex: number;
  annotations: Annotation[];
  label: string;
  labelId?: string;
  projectId?: string;
  annotationType: AnnotationCreate["annotation_type"];
  createdBy: string;
  canAnnotate: boolean;
  canDeleteAnnotation: boolean;
  selectedAnnotationId: string | null;
  windowCenter: number;
  windowWidth: number;
  emptyMessage: string;
  onSelectAnnotation: (annotationId: string | null) => void;
  onSaveAnnotation: (payload: AnnotationCreate) => Promise<void>;
  onUpdateAnnotation: (annotationId: string, payload: AnnotationUpdate) => Promise<void>;
  onDeleteAnnotation: (annotationId: string) => Promise<void>;
}

type InteractionMode = "draw" | "move" | "resize" | "polygon_vertex";
type ResizeHandle = "nw" | "ne" | "sw" | "se";

interface Interaction {
  mode: InteractionMode;
  annotationId?: string;
  handle?: ResizeHandle;
  vertexIndex?: number;
  startPoint: { x: number; y: number };
  originalBox?: BoundingBoxCoordinates;
  box?: BoundingBoxCoordinates;
  originalPoints?: PolygonPoint[];
  points?: PolygonPoint[];
}

export function ViewerPanel(props: ViewerPanelProps) {
  /** Capture mouse gestures, render images, and save annotation geometry. */
  const { elementRef } = useViewer();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [polygonPoints, setPolygonPoints] = useState<PolygonPoint[]>([]);
  const [polygonPreviewPoint, setPolygonPreviewPoint] = useState<PolygonPoint | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const { canDeleteAnnotation, onDeleteAnnotation, onSelectAnnotation, selectedAnnotationId } = props;

  const currentSliceAnnotations = useMemo(
    () => props.annotations.filter((annotation) => annotation.slice_index === props.sliceIndex),
    [props.annotations, props.sliceIndex],
  );
  const contrast = Math.max(0.25, Math.min(4, 1200 / Math.max(props.windowWidth, 1)));
  const brightness = Math.max(0.25, Math.min(2.5, props.windowCenter / 600));
  const canvasWidth = props.scan?.width ?? 512;
  const canvasHeight = props.scan?.height ?? 512;

  function boundingBoxFor(annotation: Annotation): BoundingBoxCoordinates | null {
    const box = annotation.coordinates as Partial<BoundingBoxCoordinates>;
    if (typeof box.x !== "number" || typeof box.y !== "number" || typeof box.width !== "number" || typeof box.height !== "number") return null;
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }

  function polygonFor(annotation: Annotation): PolygonPoint[] | null {
    const polygon = annotation.coordinates as Partial<PolygonCoordinates>;
    if (!Array.isArray(polygon.points) || polygon.points.length < 3) return null;
    const points = polygon.points.map((point) => ({ x: point.x, y: point.y }));
    if (points.some((point) => typeof point.x !== "number" || typeof point.y !== "number")) return null;
    return points;
  }

  function selectedEditBox(annotation: Annotation, fallback: BoundingBoxCoordinates): BoundingBoxCoordinates {
    return interaction?.annotationId === annotation.id && interaction.box ? interaction.box : fallback;
  }

  function selectedEditPolygon(annotation: Annotation, fallback: PolygonPoint[]): PolygonPoint[] {
    return interaction?.annotationId === annotation.id && interaction.points ? interaction.points : fallback;
  }

  function clampBox(box: BoundingBoxCoordinates): BoundingBoxCoordinates {
    const width = Math.max(1, Math.min(box.width, canvasWidth));
    const height = Math.max(1, Math.min(box.height, canvasHeight));
    return {
      x: Math.max(0, Math.min(box.x, canvasWidth - width)),
      y: Math.max(0, Math.min(box.y, canvasHeight - height)),
      width,
      height,
    };
  }

  function normalizedBox(box: BoundingBoxCoordinates): BoundingBoxCoordinates {
    return clampBox({
      x: Math.min(box.x, box.x + box.width),
      y: Math.min(box.y, box.y + box.height),
      width: Math.abs(box.width),
      height: Math.abs(box.height),
    });
  }

  function resizeBox(originalBox: BoundingBoxCoordinates, point: { x: number; y: number }, handle: ResizeHandle): BoundingBoxCoordinates {
    const right = originalBox.x + originalBox.width;
    const bottom = originalBox.y + originalBox.height;
    if (handle === "nw") return normalizedBox({ x: point.x, y: point.y, width: right - point.x, height: bottom - point.y });
    if (handle === "ne") return normalizedBox({ x: originalBox.x, y: point.y, width: point.x - originalBox.x, height: bottom - point.y });
    if (handle === "sw") return normalizedBox({ x: point.x, y: originalBox.y, width: right - point.x, height: point.y - originalBox.y });
    return normalizedBox({ x: originalBox.x, y: originalBox.y, width: point.x - originalBox.x, height: point.y - originalBox.y });
  }

  function handleAtPoint(box: BoundingBoxCoordinates, point: { x: number; y: number }): ResizeHandle | null {
    const tolerance = Math.max(6, Math.round(Math.min(canvasWidth, canvasHeight) * 0.02));
    const handles: Array<{ handle: ResizeHandle; x: number; y: number }> = [
      { handle: "nw", x: box.x, y: box.y },
      { handle: "ne", x: box.x + box.width, y: box.y },
      { handle: "sw", x: box.x, y: box.y + box.height },
      { handle: "se", x: box.x + box.width, y: box.y + box.height },
    ];
    return handles.find((candidate) => Math.abs(point.x - candidate.x) <= tolerance && Math.abs(point.y - candidate.y) <= tolerance)?.handle ?? null;
  }

  function pointInBox(box: BoundingBoxCoordinates, point: { x: number; y: number }): boolean {
    return point.x >= box.x && point.x <= box.x + box.width && point.y >= box.y && point.y <= box.y + box.height;
  }

  function distanceBetween(left: PolygonPoint, right: PolygonPoint): number {
    return Math.hypot(left.x - right.x, left.y - right.y);
  }

  function isNearPoint(left: PolygonPoint, right: PolygonPoint): boolean {
    return distanceBetween(left, right) <= Math.max(8, Math.round(Math.min(canvasWidth, canvasHeight) * 0.02));
  }

  function clampPoint(point: PolygonPoint): PolygonPoint {
    return {
      x: Math.max(0, Math.min(point.x, canvasWidth)),
      y: Math.max(0, Math.min(point.y, canvasHeight)),
    };
  }

  function vertexIndexAtPoint(points: PolygonPoint[], point: PolygonPoint): number | null {
    const index = points.findIndex((candidate) => isNearPoint(candidate, point));
    return index >= 0 ? index : null;
  }

  function pointInPolygon(points: PolygonPoint[], point: PolygonPoint): boolean {
    let isInside = false;
    for (let index = 0, previousIndex = points.length - 1; index < points.length; previousIndex = index, index += 1) {
      const current = points[index];
      const previous = points[previousIndex];
      const crossesY = current.y > point.y !== previous.y > point.y;
      const xIntersection = ((previous.x - current.x) * (point.y - current.y)) / (previous.y - current.y || 1) + current.x;
      if (crossesY && point.x < xIntersection) isInside = !isInside;
    }
    return isInside;
  }

  function strokePolygon(context: CanvasRenderingContext2D, points: PolygonPoint[], options: { selected: boolean; closed: boolean }): void {
    if (points.length === 0) return;
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach((point) => context.lineTo(point.x, point.y));
    if (options.closed) context.closePath();
    context.strokeStyle = options.selected ? "#f97316" : "#38bdf8";
    context.lineWidth = options.selected ? 4 : 3;
    context.stroke();
    if (options.closed) {
      context.fillStyle = options.selected ? "rgba(249, 115, 22, 0.16)" : "rgba(56, 189, 248, 0.14)";
      context.fill();
    }
    context.fillStyle = options.selected ? "#f97316" : "#38bdf8";
    points.forEach((point) => context.fillRect(point.x - 3, point.y - 3, 6, 6));
  }

  const finishPolygon = useCallback(
    async (points: PolygonPoint[]): Promise<void> => {
      if (!props.scan || !props.canAnnotate || points.length < 3) return;
      await props.onSaveAnnotation({
        scan_id: props.scan.id,
        project_id: props.projectId ?? props.scan.project_id,
        label_id: props.labelId ?? null,
        label: props.label,
        annotation_type: "polygon",
        coordinates: { points },
        slice_index: props.sliceIndex,
        created_by: props.createdBy,
      });
      setPolygonPoints([]);
      setPolygonPreviewPoint(null);
    },
    [props],
  );

  const handleDeleteSelected = useCallback(async (): Promise<void> => {
    if (!selectedAnnotationId || !canDeleteAnnotation || isDeleting) return;
    setIsDeleting(true);
    setInteraction(null);
    try {
      await onDeleteAnnotation(selectedAnnotationId);
      onSelectAnnotation(null);
    } finally {
      setIsDeleting(false);
    }
  }, [canDeleteAnnotation, isDeleting, onDeleteAnnotation, onSelectAnnotation, selectedAnnotationId]);

  useEffect(() => {
    if (!props.canDeleteAnnotation || !props.selectedAnnotationId) return;

    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      if (event.key !== "Delete" && event.key !== "Backspace") return;
      event.preventDefault();
      void handleDeleteSelected();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleDeleteSelected, props.canDeleteAnnotation, props.selectedAnnotationId]);

  useEffect(() => {
    setPolygonPoints([]);
    setPolygonPreviewPoint(null);
  }, [props.annotationType, props.scan?.id, props.sliceIndex]);

  useEffect(() => {
    /** Draw the current slice and overlays whenever source data changes. */
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !props.sliceImage) return;

    const image = new Image();
    image.onload = () => {
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.filter = `contrast(${contrast}) brightness(${brightness})`;
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      context.filter = "none";
      currentSliceAnnotations.forEach((annotation) => {
        const box = boundingBoxFor(annotation);
        if (annotation.annotation_type === "bounding_box" && box) {
          const renderedBox = selectedEditBox(annotation, box);
          context.strokeStyle = annotation.id === props.selectedAnnotationId ? "#f97316" : "#14b8a6";
          context.lineWidth = annotation.id === props.selectedAnnotationId ? 4 : 3;
          context.strokeRect(renderedBox.x, renderedBox.y, renderedBox.width, renderedBox.height);
          if (annotation.id === props.selectedAnnotationId) {
            context.fillStyle = "#f97316";
            [
              [renderedBox.x, renderedBox.y],
              [renderedBox.x + renderedBox.width, renderedBox.y],
              [renderedBox.x, renderedBox.y + renderedBox.height],
              [renderedBox.x + renderedBox.width, renderedBox.y + renderedBox.height],
            ].forEach(([x, y]) => context.fillRect(x - 3, y - 3, 6, 6));
          }
        }
        if (annotation.annotation_type === "polygon") {
          const points = polygonFor(annotation);
          if (points) strokePolygon(context, selectedEditPolygon(annotation, points), { selected: annotation.id === props.selectedAnnotationId, closed: true });
        }
      });
      if (interaction?.mode === "draw" && interaction.box) {
        context.strokeStyle = "#f97316";
        context.lineWidth = 3;
        context.strokeRect(interaction.box.x, interaction.box.y, interaction.box.width, interaction.box.height);
      }
      const draftPoints = polygonPreviewPoint && polygonPoints.length > 0 ? [...polygonPoints, polygonPreviewPoint] : polygonPoints;
      if (draftPoints.length > 0) {
        strokePolygon(context, draftPoints, { selected: true, closed: false });
        if (polygonPoints.length >= 3) {
          context.beginPath();
          context.arc(polygonPoints[0].x, polygonPoints[0].y, 8, 0, Math.PI * 2);
          context.strokeStyle = "#f97316";
          context.lineWidth = 2;
          context.stroke();
        }
      }
    };
    image.src = `data:image/png;base64,${props.sliceImage.image_base64}`;
  }, [brightness, contrast, props.sliceImage, currentSliceAnnotations, interaction, polygonPoints, polygonPreviewPoint, props.selectedAnnotationId]);

  function canvasPoint(event: MouseEvent<HTMLCanvasElement>) {
    /** Convert browser coordinates into canvas coordinates used by annotation JSON. */
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * canvas.width),
      y: Math.round(((event.clientY - rect.top) / rect.height) * canvas.height),
    };
  }

  async function handleMouseDown(event: MouseEvent<HTMLCanvasElement>): Promise<void> {
    /** Select existing annotations or start a new annotation draft. */
    if (!props.canAnnotate) return;
    const point = canvasPoint(event);
    const selectedAnnotation = [...currentSliceAnnotations].reverse().find((annotation) => {
      if (annotation.annotation_type === "bounding_box") {
        const box = boundingBoxFor(annotation);
        return box ? pointInBox(box, point) || handleAtPoint(box, point) !== null : false;
      }
      if (annotation.annotation_type === "polygon") {
        const points = polygonFor(annotation);
        return points ? vertexIndexAtPoint(points, point) !== null || pointInPolygon(points, point) : false;
      }
      return false;
    });
    if (selectedAnnotation && polygonPoints.length === 0) {
      props.onSelectAnnotation(selectedAnnotation.id);
      if (selectedAnnotation.annotation_type === "polygon") {
        const points = polygonFor(selectedAnnotation);
        const vertexIndex = points ? vertexIndexAtPoint(points, point) : null;
        if (!points || vertexIndex === null) return;
        setInteraction({
          mode: "polygon_vertex",
          annotationId: selectedAnnotation.id,
          vertexIndex,
          startPoint: point,
          originalPoints: points,
          points,
        });
        return;
      }
      const box = boundingBoxFor(selectedAnnotation);
      if (!box) return;
      const handle = handleAtPoint(box, point);
      setInteraction({
        mode: handle ? "resize" : "move",
        annotationId: selectedAnnotation.id,
        handle: handle ?? undefined,
        startPoint: point,
        originalBox: box,
        box,
      });
      return;
    }
    if (props.annotationType === "polygon") {
      props.onSelectAnnotation(null);
      setInteraction(null);
      if (polygonPoints.length >= 3 && isNearPoint(point, polygonPoints[0])) {
        await finishPolygon(polygonPoints);
        return;
      }
      setPolygonPoints((current) => [...current, point]);
      setPolygonPreviewPoint(null);
      return;
    }
    props.onSelectAnnotation(null);
    setPolygonPoints([]);
    setPolygonPreviewPoint(null);
    setInteraction({ mode: "draw", startPoint: point, originalBox: { x: point.x, y: point.y, width: 0, height: 0 }, box: { x: point.x, y: point.y, width: 0, height: 0 } });
  }

  function handleMouseMove(event: MouseEvent<HTMLCanvasElement>): void {
    /** Update width and height as the user drags across the image. */
    const point = canvasPoint(event);
    if (polygonPoints.length > 0) {
      setPolygonPreviewPoint(point);
    }
    if (!interaction) return;
    if (interaction.mode === "draw") {
      if (!interaction.originalBox) return;
      setInteraction({ ...interaction, box: normalizedBox({ ...interaction.originalBox, width: point.x - interaction.startPoint.x, height: point.y - interaction.startPoint.y }) });
      return;
    }
    if (interaction.mode === "move") {
      if (!interaction.originalBox) return;
      const deltaX = point.x - interaction.startPoint.x;
      const deltaY = point.y - interaction.startPoint.y;
      setInteraction({ ...interaction, box: clampBox({ ...interaction.originalBox, x: interaction.originalBox.x + deltaX, y: interaction.originalBox.y + deltaY }) });
      return;
    }
    if (interaction.handle) {
      if (!interaction.originalBox) return;
      setInteraction({ ...interaction, box: resizeBox(interaction.originalBox, point, interaction.handle) });
      return;
    }
    if (interaction.mode === "polygon_vertex" && interaction.originalPoints && interaction.vertexIndex !== undefined) {
      setInteraction({
        ...interaction,
        points: interaction.originalPoints.map((candidate, index) => (index === interaction.vertexIndex ? clampPoint(point) : candidate)),
      });
    }
  }

  async function handleMouseUp(): Promise<void> {
    /** Normalize and save the completed draft box through the annotation API. */
    if (!props.scan || !props.canAnnotate || !interaction) return;
    const mode = interaction.mode;
    const annotationId = interaction.annotationId;
    setInteraction(null);
    if (mode === "polygon_vertex" && annotationId && interaction.points) {
      await props.onUpdateAnnotation(annotationId, { coordinates: { points: interaction.points } });
      return;
    }
    if (props.annotationType !== "bounding_box" || !interaction.box) return;
    const coordinates = normalizedBox(interaction.box);
    if (coordinates.width < 4 || coordinates.height < 4) return;
    if ((mode === "move" || mode === "resize") && annotationId) {
      await props.onUpdateAnnotation(annotationId, { coordinates: { ...coordinates } });
      return;
    }
    await props.onSaveAnnotation({
      scan_id: props.scan.id,
      project_id: props.projectId ?? props.scan.project_id,
      label_id: props.labelId ?? null,
      label: props.label,
      annotation_type: props.annotationType,
      coordinates: { ...coordinates },
      slice_index: props.sliceIndex,
      created_by: props.createdBy,
    });
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div ref={elementRef} className="hidden" />
      <div className="flex min-h-0 flex-1 items-center justify-center p-4">
        {props.scan && props.sliceImage ? (
          <div className="relative flex max-h-full max-w-full items-center justify-center">
            {props.canDeleteAnnotation && props.selectedAnnotationId ? (
              <button
                className="absolute right-3 top-3 z-10 rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isDeleting}
                onClick={handleDeleteSelected}
                type="button"
              >
                {isDeleting ? "Deleting..." : "Delete selected"}
              </button>
            ) : null}
            {props.annotationType === "polygon" && polygonPoints.length > 0 ? (
              <div className="absolute left-3 top-3 z-10 flex gap-2">
                <button
                  className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={polygonPoints.length < 3}
                  onClick={() => void finishPolygon(polygonPoints)}
                  type="button"
                >
                  Finish polygon
                </button>
                <button
                  className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                  onClick={() => {
                    setPolygonPoints([]);
                    setPolygonPreviewPoint(null);
                  }}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            ) : null}
            <canvas
              ref={canvasRef}
              width={canvasWidth}
              height={canvasHeight}
              className={`max-h-full max-w-full rounded-md border border-slate-700 bg-black ${props.canAnnotate ? "cursor-crosshair" : "cursor-not-allowed"}`}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
            />
          </div>
        ) : (
          <p className="max-w-sm text-center text-sm text-slate-300">{props.emptyMessage}</p>
        )}
      </div>
    </main>
  );
}
