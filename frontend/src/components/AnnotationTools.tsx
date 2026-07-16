/** Tool panel for choosing annotation metadata before drawing.
 *
 * Medical tools often separate geometry capture from semantic labeling: the box
 * tells us where, while label/type tells us what it means.
 */

import type { Label } from "../types/project";

export type ViewerTool = "select" | "pan" | "bounding_box" | "polygon" | "segmentation";

interface AnnotationToolsProps {
  labels: Label[];
  selectedLabelId: string;
  viewerTool: ViewerTool;
  createdBy: string;
  onLabelChange: (labelId: string) => void;
  onViewerToolChange: (value: ViewerTool) => void;
}

export function AnnotationTools(props: AnnotationToolsProps) {
  /** Render compact controls used before saving a drawn bounding box. */
  const selectedLabel = props.labels.find((label) => label.id === props.selectedLabelId);
  const hasLabels = props.labels.length > 0;
  const tools: Array<{ value: ViewerTool; label: string; title: string; needsLabel?: boolean; shortcut: string }> = [
    { value: "select", label: "Select", title: "Select and edit saved annotations", shortcut: "V" },
    { value: "pan", label: "Pan", title: "Move around the zoomed image", shortcut: "H" },
    { value: "bounding_box", label: "Box", title: "Draw bounding boxes", needsLabel: true, shortcut: "B" },
    { value: "polygon", label: "Polygon", title: "Draw polygons", needsLabel: true, shortcut: "P" },
    { value: "segmentation", label: "Mask", title: "Paint segmentation masks", needsLabel: true, shortcut: "M" },
  ];

  function chooseTool(value: ViewerTool): void {
    props.onViewerToolChange(value);
  }

  function ToolIcon({ tool }: { tool: ViewerTool }) {
    const commonProps = {
      "aria-hidden": true,
      className: "h-4 w-4",
      fill: "none",
      stroke: "currentColor",
      strokeLinecap: "round" as const,
      strokeLinejoin: "round" as const,
      strokeWidth: 2,
      viewBox: "0 0 24 24",
    };

    if (tool === "select") {
      return (
        <svg {...commonProps}>
          <path d="M5 3l12 9-6 1.5L8 20 5 3z" />
        </svg>
      );
    }
    if (tool === "pan") {
      return (
        <svg {...commonProps}>
          <path d="M8 11V6a2 2 0 1 1 4 0v5" />
          <path d="M12 11V5a2 2 0 1 1 4 0v7" />
          <path d="M16 12V8a2 2 0 1 1 4 0v6a6 6 0 0 1-6 6h-2a7 7 0 0 1-5.6-2.8L4 14a2 2 0 0 1 3.2-2.4L9 14" />
        </svg>
      );
    }
    if (tool === "bounding_box") {
      return (
        <svg {...commonProps}>
          <rect height="14" width="14" x="5" y="5" />
          <path d="M5 9V5h4" />
          <path d="M15 5h4v4" />
          <path d="M19 15v4h-4" />
          <path d="M9 19H5v-4" />
        </svg>
      );
    }
    if (tool === "polygon") {
      return (
        <svg {...commonProps}>
          <path d="M7 5l10 3 2 9-9 2-5-7 2-7z" />
          <path d="M7 5h.01" />
          <path d="M17 8h.01" />
          <path d="M19 17h.01" />
          <path d="M10 19h.01" />
          <path d="M5 12h.01" />
        </svg>
      );
    }
    return (
      <svg {...commonProps}>
        <path d="M7 17c4 0 8-3 8-7a4 4 0 0 0-8 0c0 4-3 5-3 5s1 2 3 2z" />
        <path d="M14 5l5-2 2 2-2 5" />
        <path d="M15 9l4-4" />
      </svg>
    );
  }

  return (
    <section className="border-b border-slate-200 bg-white p-3">
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.2fr_2fr_1fr]">
        <label className="text-xs font-medium text-slate-600">
          Label
          <div className="mt-1 flex items-center gap-2">
            <span className="h-4 w-4 rounded-sm border border-slate-200" style={{ backgroundColor: selectedLabel?.color ?? "#94a3b8" }} />
            <select className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100 disabled:text-slate-500" disabled={!hasLabels} value={props.selectedLabelId} onChange={(event) => props.onLabelChange(event.target.value)}>
              {props.labels.length === 0 ? <option value="">No labels</option> : null}
              {props.labels.map((label) => (
                <option key={label.id} value={label.id}>
                  {label.name}
                </option>
              ))}
            </select>
          </div>
        </label>
        <div className="text-xs font-medium text-slate-600">
          Tool
          <div className="mt-1 flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 p-1">
            {tools.map((tool) => {
              const isActive = props.viewerTool === tool.value;
              const isDisabled = Boolean(tool.needsLabel && !hasLabels);
              return (
                <span key={tool.value} className="group relative">
                  <button
                    aria-label={`${tool.label}: ${tool.title}`}
                    aria-pressed={isActive}
                    className={`flex h-9 w-9 items-center justify-center rounded border text-sm transition disabled:cursor-not-allowed disabled:border-transparent disabled:text-slate-400 ${isActive ? "border-slate-900 bg-slate-900 text-white shadow-sm" : "border-transparent text-slate-600 hover:border-slate-200 hover:bg-white"}`}
                    disabled={isDisabled}
                    onClick={() => chooseTool(tool.value)}
                    title={`${tool.title} (${tool.shortcut})`}
                    type="button"
                  >
                    <ToolIcon tool={tool.value} />
                  </button>
                  <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 w-max max-w-52 -translate-x-1/2 rounded bg-slate-950 px-2 py-1 text-center text-[11px] font-medium text-white opacity-0 shadow-sm transition group-focus-within:opacity-100 group-hover:opacity-100">
                    {tool.label}: {tool.title} ({tool.shortcut})
                  </span>
                </span>
              );
            })}
          </div>
        </div>
        <label className="text-xs font-medium text-slate-600">
          Annotator
          <input className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-sm" value={props.createdBy} readOnly />
        </label>
      </div>
      {!hasLabels ? <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">Add a project label before drawing annotations.</p> : null}
    </section>
  );
}
