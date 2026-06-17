/** Main viewer panel with Cornerstone3D initialization and canvas drawing.
 *
 * Real medical imaging viewers usually render DICOM imageIds through
 * Cornerstone3D. This teaching project initializes Cornerstone to show the
 * lifecycle pattern, then draws the simulated backend PNG and overlays on a
 * normal canvas so bounding-box capture stays understandable.
 */

import { MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useViewer } from "../hooks/useViewer";
import type { Annotation, AnnotationCreate, AnnotationUpdate, BoundingBoxCoordinates, PolygonCoordinates, PolygonPoint, SegmentationMaskImage } from "../types/annotation";
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
  annotationBlockedMessage?: string | null;
  onSelectAnnotation: (annotationId: string | null) => void;
  onSliceChange: (sliceIndex: number) => void;
  onSaveAnnotation: (payload: AnnotationCreate) => Promise<Annotation | void>;
  onUpdateAnnotation: (annotationId: string, payload: AnnotationUpdate) => Promise<void>;
  onDeleteAnnotation: (annotationId: string) => Promise<void>;
  onSaveMask: (annotationId: string, sliceIndex: number, mask: Blob) => Promise<unknown>;
  onLoadMask: (annotationId: string, sliceIndex: number) => Promise<SegmentationMaskImage | null>;
  onDeleteMask: (annotationId: string, sliceIndex: number) => Promise<void>;
}

type InteractionMode = "draw" | "move" | "resize" | "polygon_vertex";
type ResizeHandle = "nw" | "ne" | "sw" | "se";
type GeometryCoordinates = Record<string, unknown>;
type MaskTool = "brush" | "eraser";
type MaskStatus = "idle" | "loading" | "saving" | "saved" | "error";

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

interface GeometryHistoryEntry {
  annotationId: string;
  before: GeometryCoordinates;
  after: GeometryCoordinates;
}

interface MaskHistoryEntry {
  before: ImageData;
  after: ImageData;
}

export function ViewerPanel(props: ViewerPanelProps) {
  /** Capture mouse gestures, render images, and save annotation geometry. */
  const { elementRef } = useViewer();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const maskGestureStartRef = useRef<ImageData | null>(null);
  const panStartRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [zoom, setZoom] = useState(1);
  const [isPanMode, setIsPanMode] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const [polygonPoints, setPolygonPoints] = useState<PolygonPoint[]>([]);
  const [polygonPreviewPoint, setPolygonPreviewPoint] = useState<PolygonPoint | null>(null);
  const [undoStack, setUndoStack] = useState<GeometryHistoryEntry[]>([]);
  const [redoStack, setRedoStack] = useState<GeometryHistoryEntry[]>([]);
  const [maskUndoStack, setMaskUndoStack] = useState<MaskHistoryEntry[]>([]);
  const [maskRedoStack, setMaskRedoStack] = useState<MaskHistoryEntry[]>([]);
  const [maskTool, setMaskTool] = useState<MaskTool>("brush");
  const [maskBrushSize, setMaskBrushSize] = useState(24);
  const [maskOpacity, setMaskOpacity] = useState(0.45);
  const [isMaskDrawing, setIsMaskDrawing] = useState(false);
  const [maskRevision, setMaskRevision] = useState(0);
  const [maskStatus, setMaskStatus] = useState<MaskStatus>("idle");
  const [isDeleting, setIsDeleting] = useState(false);
  const [copyDirection, setCopyDirection] = useState<-1 | 1 | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);
  const { canDeleteAnnotation, onDeleteAnnotation, onSelectAnnotation, selectedAnnotationId } = props;

  const currentSliceAnnotations = useMemo(
    () => props.annotations.filter((annotation) => annotation.slice_index === props.sliceIndex),
    [props.annotations, props.sliceIndex],
  );
  const selectedSegmentationAnnotation = useMemo(
    () => currentSliceAnnotations.find((annotation) => annotation.id === props.selectedAnnotationId && annotation.annotation_type === "segmentation") ?? null,
    [currentSliceAnnotations, props.selectedAnnotationId],
  );
  const selectedAnnotation = useMemo(
    () => props.annotations.find((annotation) => annotation.id === props.selectedAnnotationId) ?? null,
    [props.annotations, props.selectedAnnotationId],
  );
  const contrast = Math.max(0.25, Math.min(4, 1200 / Math.max(props.windowWidth, 1)));
  const brightness = Math.max(0.25, Math.min(2.5, props.windowCenter / 600));
  const canvasWidth = props.scan?.width ?? 512;
  const canvasHeight = props.scan?.height ?? 512;
  const zoomPercent = Math.round(zoom * 100);
  const previousSliceIndex = selectedAnnotation ? selectedAnnotation.slice_index - 1 : -1;
  const nextSliceIndex = selectedAnnotation ? selectedAnnotation.slice_index + 1 : -1;
  const canCopySelectedAnnotation = Boolean(props.canAnnotate && props.scan && selectedAnnotation && selectedAnnotation.annotation_type !== "segmentation");
  const canCopyPrevious = canCopySelectedAnnotation && previousSliceIndex >= 0;
  const canCopyNext = canCopySelectedAnnotation && props.scan !== null && nextSliceIndex < props.scan.num_slices;

  function clampZoom(value: number): number {
    return Math.max(0.5, Math.min(4, Number(value.toFixed(2))));
  }

  function changeZoom(delta: number): void {
    setZoom((current) => clampZoom(current + delta));
  }

  function resetViewport(): void {
    setZoom(1);
    setIsPanMode(false);
    setIsPanning(false);
    panStartRef.current = null;
    if (viewportRef.current) {
      viewportRef.current.scrollLeft = 0;
      viewportRef.current.scrollTop = 0;
    }
  }

  function boundingBoxFor(annotation: Annotation): BoundingBoxCoordinates | null {
    const box = annotation.coordinates as Partial<BoundingBoxCoordinates>;
    if (typeof box.x !== "number" || typeof box.y !== "number" || typeof box.width !== "number" || typeof box.height !== "number") return null;
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }

  function cloneCoordinates<T extends GeometryCoordinates>(coordinates: T): T {
    return JSON.parse(JSON.stringify(coordinates)) as T;
  }

  function sameCoordinates(left: GeometryCoordinates, right: GeometryCoordinates): boolean {
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function recordGeometryEdit(annotationId: string, before: GeometryCoordinates, after: GeometryCoordinates): void {
    if (sameCoordinates(before, after)) return;
    setUndoStack((current) => [...current.slice(-24), { annotationId, before: cloneCoordinates(before), after: cloneCoordinates(after) }]);
    setRedoStack([]);
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

  function ensureMaskCanvas(): HTMLCanvasElement {
    if (!maskCanvasRef.current) {
      maskCanvasRef.current = document.createElement("canvas");
    }
    const maskCanvas = maskCanvasRef.current;
    if (maskCanvas.width !== canvasWidth || maskCanvas.height !== canvasHeight) {
      maskCanvas.width = canvasWidth;
      maskCanvas.height = canvasHeight;
    }
    return maskCanvas;
  }

  function captureMaskSnapshot(): ImageData | null {
    const maskCanvas = ensureMaskCanvas();
    const context = maskCanvas.getContext("2d");
    return context?.getImageData(0, 0, maskCanvas.width, maskCanvas.height) ?? null;
  }

  function sameMaskSnapshot(left: ImageData | null, right: ImageData | null): boolean {
    if (!left || !right) return left === right;
    if (left.width !== right.width || left.height !== right.height || left.data.length !== right.data.length) return false;
    for (let index = 0; index < left.data.length; index += 1) {
      if (left.data[index] !== right.data[index]) return false;
    }
    return true;
  }

  function applyMaskSnapshot(snapshot: ImageData): void {
    const maskCanvas = ensureMaskCanvas();
    const context = maskCanvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    context.putImageData(snapshot, 0, 0);
    setMaskRevision((current) => current + 1);
    setMaskStatus("idle");
  }

  function recordMaskEdit(before: ImageData | null, after: ImageData | null): void {
    if (!before || !after || sameMaskSnapshot(before, after)) return;
    setMaskUndoStack((current) => [...current.slice(-24), { before, after }]);
    setMaskRedoStack([]);
  }

  function drawMaskPoint(point: PolygonPoint): void {
    const maskCanvas = ensureMaskCanvas();
    const context = maskCanvas.getContext("2d");
    if (!context) return;
    context.save();
    context.globalCompositeOperation = maskTool === "eraser" ? "destination-out" : "source-over";
    context.fillStyle = "rgba(14, 165, 233, 1)";
    context.beginPath();
    context.arc(point.x, point.y, maskBrushSize / 2, 0, Math.PI * 2);
    context.fill();
    context.restore();
    setMaskRevision((current) => current + 1);
    setMaskStatus("idle");
  }

  function clearMask(): void {
    const maskCanvas = ensureMaskCanvas();
    const context = maskCanvas.getContext("2d");
    context?.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    setMaskRevision((current) => current + 1);
    setMaskStatus("idle");
  }

  function handleClearMask(): void {
    const before = captureMaskSnapshot();
    clearMask();
    recordMaskEdit(before, captureMaskSnapshot());
  }

  function handlePanMouseDown(event: MouseEvent<HTMLDivElement>): void {
    if (!isPanMode || event.button !== 0) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    event.preventDefault();
    panStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    setIsPanning(true);
  }

  function handlePanMouseMove(event: MouseEvent<HTMLDivElement>): void {
    if (!isPanning || !panStartRef.current || !viewportRef.current) return;
    const start = panStartRef.current;
    viewportRef.current.scrollLeft = start.scrollLeft - (event.clientX - start.x);
    viewportRef.current.scrollTop = start.scrollTop - (event.clientY - start.y);
  }

  function finishPanGesture(): void {
    panStartRef.current = null;
    setIsPanning(false);
  }

  function maskCanvasToBlob(): Promise<Blob> {
    const maskCanvas = ensureMaskCanvas();
    return new Promise((resolve, reject) => {
      maskCanvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Could not encode mask"));
          return;
        }
        resolve(blob);
      }, "image/png");
    });
  }

  function drawLoadedMask(mask: SegmentationMaskImage, shouldDraw: () => boolean, onDone?: () => void, onError?: () => void): void {
    const maskCanvas = ensureMaskCanvas();
    const context = maskCanvas.getContext("2d");
    if (!context) {
      onError?.();
      return;
    }
    const image = new Image();
    image.onload = () => {
      if (!shouldDraw()) return;
      context.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
      context.drawImage(image, 0, 0, maskCanvas.width, maskCanvas.height);
      setMaskRevision((current) => current + 1);
      onDone?.();
    };
    image.onerror = () => {
      if (shouldDraw()) onError?.();
    };
    image.src = `data:image/png;base64,${mask.mask_base64}`;
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

  async function copySelectedAnnotation(direction: -1 | 1): Promise<void> {
    if (!props.scan || !selectedAnnotation || selectedAnnotation.annotation_type === "segmentation") return;
    const targetSliceIndex = selectedAnnotation.slice_index + direction;
    if (targetSliceIndex < 0 || targetSliceIndex >= props.scan.num_slices) return;
    setCopyDirection(direction);
    setCopyError(null);
    try {
      const copied = await props.onSaveAnnotation({
        scan_id: selectedAnnotation.scan_id,
        project_id: selectedAnnotation.project_id ?? props.projectId ?? props.scan.project_id,
        label_id: selectedAnnotation.label_id,
        label: selectedAnnotation.label,
        annotation_type: selectedAnnotation.annotation_type,
        coordinates: cloneCoordinates(selectedAnnotation.coordinates),
        slice_index: targetSliceIndex,
        created_by: props.createdBy,
        confidence_score: selectedAnnotation.confidence_score,
        review_status: "pending",
        notes: selectedAnnotation.notes,
        assigned_to_user_id: selectedAnnotation.assigned_to_user_id,
      });
      props.onSliceChange(targetSliceIndex);
      if (copied) props.onSelectAnnotation(copied.id);
    } catch (error) {
      setCopyError(error instanceof Error ? error.message : "Could not copy annotation");
    } finally {
      setCopyDirection(null);
    }
  }

  const undoGeometryEdit = useCallback(async (): Promise<void> => {
    const entry = undoStack[undoStack.length - 1];
    if (!entry || !props.canAnnotate) return;
    setUndoStack((current) => current.slice(0, -1));
    await props.onUpdateAnnotation(entry.annotationId, { coordinates: cloneCoordinates(entry.before) });
    props.onSelectAnnotation(entry.annotationId);
    setRedoStack((current) => [...current.slice(-24), entry]);
  }, [props, undoStack]);

  const redoGeometryEdit = useCallback(async (): Promise<void> => {
    const entry = redoStack[redoStack.length - 1];
    if (!entry || !props.canAnnotate) return;
    setRedoStack((current) => current.slice(0, -1));
    await props.onUpdateAnnotation(entry.annotationId, { coordinates: cloneCoordinates(entry.after) });
    props.onSelectAnnotation(entry.annotationId);
    setUndoStack((current) => [...current.slice(-24), entry]);
  }, [props, redoStack]);

  const undoMaskEdit = useCallback((): void => {
    const entry = maskUndoStack[maskUndoStack.length - 1];
    if (!entry || !props.canAnnotate) return;
    setMaskUndoStack((current) => current.slice(0, -1));
    applyMaskSnapshot(entry.before);
    setMaskRedoStack((current) => [...current.slice(-24), entry]);
  }, [maskUndoStack, props.canAnnotate]);

  const redoMaskEdit = useCallback((): void => {
    const entry = maskRedoStack[maskRedoStack.length - 1];
    if (!entry || !props.canAnnotate) return;
    setMaskRedoStack((current) => current.slice(0, -1));
    applyMaskSnapshot(entry.after);
    setMaskUndoStack((current) => [...current.slice(-24), entry]);
  }, [maskRedoStack, props.canAnnotate]);

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
    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null;
      if (target && (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName) || target.isContentEditable)) return;
      const isUndo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.shiftKey;
      const isRedo = ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") || ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "z");
      if (isUndo) {
        event.preventDefault();
        if (props.annotationType === "segmentation") {
          undoMaskEdit();
          return;
        }
        void undoGeometryEdit();
        return;
      }
      if (isRedo) {
        event.preventDefault();
        if (props.annotationType === "segmentation") {
          redoMaskEdit();
          return;
        }
        void redoGeometryEdit();
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setInteraction(null);
        setPolygonPoints([]);
        setPolygonPreviewPoint(null);
        props.onSelectAnnotation(null);
      }
      if (event.key === "Enter" && props.annotationType === "polygon" && polygonPoints.length >= 3) {
        event.preventDefault();
        void finishPolygon(polygonPoints);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [finishPolygon, polygonPoints, props, redoGeometryEdit, redoMaskEdit, undoGeometryEdit, undoMaskEdit]);

  useEffect(() => {
    setPolygonPoints([]);
    setPolygonPreviewPoint(null);
  }, [props.annotationType, props.scan?.id, props.sliceIndex]);

  useEffect(() => {
    setUndoStack([]);
    setRedoStack([]);
    setMaskUndoStack([]);
    setMaskRedoStack([]);
    maskGestureStartRef.current = null;
  }, [props.scan?.id, props.sliceIndex]);

  useEffect(() => {
    setCopyError(null);
  }, [props.selectedAnnotationId, props.sliceIndex]);

  useEffect(() => {
    resetViewport();
  }, [canvasHeight, canvasWidth, props.scan?.id]);

  useEffect(() => {
    clearMask();
  }, [canvasHeight, canvasWidth, props.scan?.id, props.sliceIndex]);

  useEffect(() => {
    if (props.annotationType !== "segmentation") return;
    let isCancelled = false;

    if (!selectedSegmentationAnnotation) {
      const maskCanvas = ensureMaskCanvas();
      maskCanvas.getContext("2d")?.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
      setMaskUndoStack([]);
      setMaskRedoStack([]);
      maskGestureStartRef.current = null;
      setMaskStatus("idle");
      setMaskRevision((current) => current + 1);
      return () => {
        isCancelled = true;
      };
    }

    setMaskStatus("loading");
    setMaskUndoStack([]);
    setMaskRedoStack([]);
    maskGestureStartRef.current = null;
    props
      .onLoadMask(selectedSegmentationAnnotation.id, props.sliceIndex)
      .then((mask) => {
        if (isCancelled) return;
        if (!mask) {
          clearMask();
          setMaskStatus("idle");
          return;
        }
        drawLoadedMask(
          mask,
          () => !isCancelled,
          () => {
            if (!isCancelled) setMaskStatus("saved");
          },
          () => {
            if (!isCancelled) setMaskStatus("error");
          },
        );
      })
      .catch(() => {
        if (!isCancelled) setMaskStatus("error");
      });

    return () => {
      isCancelled = true;
    };
  }, [canvasHeight, canvasWidth, props.annotationType, props.onLoadMask, props.sliceIndex, selectedSegmentationAnnotation]);

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
      const maskCanvas = maskCanvasRef.current;
      if (maskCanvas && props.annotationType === "segmentation") {
        context.save();
        context.globalAlpha = maskOpacity;
        context.drawImage(maskCanvas, 0, 0, canvas.width, canvas.height);
        context.restore();
      }
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
  }, [brightness, contrast, props.sliceImage, currentSliceAnnotations, interaction, maskOpacity, maskRevision, polygonPoints, polygonPreviewPoint, props.annotationType, props.selectedAnnotationId]);

  function canvasPoint(event: MouseEvent<HTMLCanvasElement>) {
    /** Convert browser coordinates into canvas coordinates used by annotation JSON. */
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * canvas.width),
      y: Math.round(((event.clientY - rect.top) / rect.height) * canvas.height),
    };
  }

  async function handleSaveMask(): Promise<void> {
    if (!props.scan || !props.canAnnotate) return;
    setMaskStatus("saving");
    try {
      const maskBlob = await maskCanvasToBlob();
      let targetAnnotation = selectedSegmentationAnnotation;
      if (!targetAnnotation) {
        const saved = await props.onSaveAnnotation({
          scan_id: props.scan.id,
          project_id: props.projectId ?? props.scan.project_id,
          label_id: props.labelId ?? null,
          label: props.label,
          annotation_type: "segmentation",
          coordinates: { mask_ref: true, representation: "png_binary" },
          slice_index: props.sliceIndex,
          created_by: props.createdBy,
        });
        if (!saved) throw new Error("Could not create segmentation annotation");
        targetAnnotation = saved;
      }
      await props.onSaveMask(targetAnnotation.id, props.sliceIndex, maskBlob);
      props.onSelectAnnotation(targetAnnotation.id);
      setMaskStatus("saved");
    } catch {
      setMaskStatus("error");
    }
  }

  async function handleDeleteSavedMask(): Promise<void> {
    if (!selectedSegmentationAnnotation || !props.canAnnotate) return;
    setMaskStatus("saving");
    try {
      await props.onDeleteMask(selectedSegmentationAnnotation.id, props.sliceIndex);
      clearMask();
      setMaskStatus("idle");
    } catch {
      setMaskStatus("error");
    }
  }

  async function handleMouseDown(event: MouseEvent<HTMLCanvasElement>): Promise<void> {
    /** Select existing annotations or start a new annotation draft. */
    if (isPanMode) return;
    if (!props.canAnnotate) return;
    const point = canvasPoint(event);
    if (props.annotationType === "segmentation") {
      if (props.selectedAnnotationId && !selectedSegmentationAnnotation) {
        props.onSelectAnnotation(null);
      }
      setInteraction(null);
      setPolygonPoints([]);
      setPolygonPreviewPoint(null);
      maskGestureStartRef.current = captureMaskSnapshot();
      setIsMaskDrawing(true);
      drawMaskPoint(point);
      return;
    }
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
    if (isPanMode) return;
    const point = canvasPoint(event);
    if (props.annotationType === "segmentation" && isMaskDrawing) {
      drawMaskPoint(point);
      return;
    }
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

  function finishMaskGesture(): void {
    setIsMaskDrawing(false);
    recordMaskEdit(maskGestureStartRef.current, captureMaskSnapshot());
    maskGestureStartRef.current = null;
  }

  async function handleMouseUp(): Promise<void> {
    /** Normalize and save the completed draft box through the annotation API. */
    if (isPanMode) return;
    if (isMaskDrawing) {
      finishMaskGesture();
      return;
    }
    if (!props.scan || !props.canAnnotate || !interaction) return;
    const mode = interaction.mode;
    const annotationId = interaction.annotationId;
    setInteraction(null);
    if (mode === "polygon_vertex" && annotationId && interaction.points) {
      const before = { points: interaction.originalPoints ?? [] };
      const after = { points: interaction.points };
      await props.onUpdateAnnotation(annotationId, { coordinates: after });
      recordGeometryEdit(annotationId, before, after);
      return;
    }
    if (props.annotationType !== "bounding_box" || !interaction.box) return;
    const coordinates = normalizedBox(interaction.box);
    if (coordinates.width < 4 || coordinates.height < 4) return;
    if ((mode === "move" || mode === "resize") && annotationId) {
      await props.onUpdateAnnotation(annotationId, { coordinates: { ...coordinates } });
      if (interaction.originalBox) {
        recordGeometryEdit(annotationId, { ...interaction.originalBox }, { ...coordinates });
      }
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

  const maskSaveLabel = maskStatus === "saving" ? "Saving..." : maskStatus === "loading" ? "Loading..." : maskStatus === "saved" ? "Saved" : maskStatus === "error" ? "Retry save" : "Save";

  return (
    <main className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div ref={elementRef} className="hidden" />
      <div className="relative min-h-0 flex-1 p-4">
        {props.scan && props.sliceImage ? (
          <>
            <div className="absolute bottom-6 right-6 z-20 flex items-center gap-1 rounded-md border border-slate-700 bg-slate-950/90 p-1 text-xs text-white shadow-sm">
              <button className="h-8 min-w-8 rounded border border-slate-600 px-2 font-semibold hover:bg-slate-800" onClick={() => changeZoom(-0.25)} type="button">
                -
              </button>
              <span className="min-w-12 text-center font-medium">{zoomPercent}%</span>
              <button className="h-8 min-w-8 rounded border border-slate-600 px-2 font-semibold hover:bg-slate-800" onClick={() => changeZoom(0.25)} type="button">
                +
              </button>
              <button className="h-8 rounded border border-slate-600 px-2 font-medium hover:bg-slate-800" onClick={resetViewport} type="button">
                Reset
              </button>
              <button className={`h-8 rounded border px-2 font-medium ${isPanMode ? "border-teal-400 bg-teal-500 text-white" : "border-slate-600 hover:bg-slate-800"}`} onClick={() => setIsPanMode((current) => !current)} type="button">
                Pan
              </button>
            </div>
            {props.annotationBlockedMessage ? (
              <div className="absolute left-1/2 top-6 z-20 max-w-sm -translate-x-1/2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-center text-sm font-medium text-amber-900 shadow-sm">
                {props.annotationBlockedMessage}
              </div>
            ) : null}
            <div
              ref={viewportRef}
              className={`h-full w-full overflow-auto rounded-md border border-slate-800 bg-slate-900 ${isPanMode ? (isPanning ? "cursor-grabbing" : "cursor-grab") : ""}`}
              onMouseDown={handlePanMouseDown}
              onMouseLeave={() => {
                finishPanGesture();
                if (isMaskDrawing) finishMaskGesture();
              }}
              onMouseMove={handlePanMouseMove}
              onMouseUp={finishPanGesture}
            >
              <div className="flex min-h-full min-w-full items-center justify-center p-3">
                <div className="relative shrink-0" style={{ width: canvasWidth * zoom, height: canvasHeight * zoom }}>
                  {props.selectedAnnotationId ? (
                    <div className="absolute right-3 top-3 z-10 flex max-w-44 flex-wrap justify-end gap-2">
                      {canCopySelectedAnnotation ? (
                        <>
                          <button
                            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={!canCopyPrevious || copyDirection !== null}
                            onClick={() => void copySelectedAnnotation(-1)}
                            type="button"
                          >
                            {copyDirection === -1 ? "Copying..." : "Copy prev"}
                          </button>
                          <button
                            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={!canCopyNext || copyDirection !== null}
                            onClick={() => void copySelectedAnnotation(1)}
                            type="button"
                          >
                            {copyDirection === 1 ? "Copying..." : "Copy next"}
                          </button>
                        </>
                      ) : null}
                      {props.canDeleteAnnotation ? (
                        <button
                          className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={isDeleting}
                          onClick={handleDeleteSelected}
                          type="button"
                        >
                          {isDeleting ? "Deleting..." : "Delete"}
                        </button>
                      ) : null}
                      {copyError ? <p className="w-full rounded-md bg-white/95 px-2 py-1 text-right text-xs text-red-700 shadow-sm">{copyError}</p> : null}
                    </div>
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
                  {props.annotationType === "segmentation" ? (
                    <div className="absolute left-3 top-3 z-10 flex max-w-[min(28rem,calc(100vw-2rem))] flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white p-2 text-xs shadow-sm">
                      <button
                        className={`rounded-md border px-2 py-1 font-medium ${maskTool === "brush" ? "border-sky-500 bg-sky-50 text-sky-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                        onClick={() => setMaskTool("brush")}
                        type="button"
                      >
                        Brush
                      </button>
                      <button
                        className={`rounded-md border px-2 py-1 font-medium ${maskTool === "eraser" ? "border-sky-500 bg-sky-50 text-sky-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                        onClick={() => setMaskTool("eraser")}
                        type="button"
                      >
                        Eraser
                      </button>
                      <label className="flex items-center gap-2 text-slate-600">
                        Size
                        <input className="w-20 accent-sky-600" max={80} min={4} onChange={(event) => setMaskBrushSize(Number(event.target.value))} type="range" value={maskBrushSize} />
                      </label>
                      <label className="flex items-center gap-2 text-slate-600">
                        Opacity
                        <input className="w-20 accent-sky-600" max={0.9} min={0.1} onChange={(event) => setMaskOpacity(Number(event.target.value))} step={0.05} type="range" value={maskOpacity} />
                      </label>
                      <button
                        className="rounded-md border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={!props.canAnnotate || maskUndoStack.length === 0 || maskStatus === "saving" || maskStatus === "loading"}
                        onClick={undoMaskEdit}
                        type="button"
                      >
                        Undo
                      </button>
                      <button
                        className="rounded-md border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={!props.canAnnotate || maskRedoStack.length === 0 || maskStatus === "saving" || maskStatus === "loading"}
                        onClick={redoMaskEdit}
                        type="button"
                      >
                        Redo
                      </button>
                      <button className="rounded-md border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50" onClick={handleClearMask} type="button">
                        Clear
                      </button>
                      <button
                        className="rounded-md border border-sky-500 bg-sky-600 px-2 py-1 font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={!props.canAnnotate || maskStatus === "saving" || maskStatus === "loading"}
                        onClick={() => void handleSaveMask()}
                        type="button"
                      >
                        {maskSaveLabel}
                      </button>
                      {selectedSegmentationAnnotation ? (
                        <button
                          className="rounded-md border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={!props.canAnnotate || maskStatus === "saving" || maskStatus === "loading"}
                          onClick={() => void handleDeleteSavedMask()}
                          type="button"
                        >
                          Delete saved
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                  <canvas
                    ref={canvasRef}
                    width={canvasWidth}
                    height={canvasHeight}
                    className={`rounded-md border border-slate-700 bg-black ${isPanMode ? (isPanning ? "cursor-grabbing" : "cursor-grab") : props.canAnnotate ? "cursor-crosshair" : "cursor-not-allowed"}`}
                    style={{ width: canvasWidth * zoom, height: canvasHeight * zoom }}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                  />
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="max-w-sm text-center text-sm text-slate-300">{props.emptyMessage}</p>
          </div>
        )}
      </div>
    </main>
  );
}
