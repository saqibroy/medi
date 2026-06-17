/** Tool panel for choosing annotation metadata before drawing.
 *
 * Medical tools often separate geometry capture from semantic labeling: the box
 * tells us where, while label/type tells us what it means.
 */

import type { AnnotationType } from "../types/annotation";
import type { Label } from "../types/project";

interface AnnotationToolsProps {
  labels: Label[];
  selectedLabelId: string;
  annotationType: AnnotationType;
  createdBy: string;
  onLabelChange: (labelId: string) => void;
  onAnnotationTypeChange: (value: AnnotationType) => void;
}

export function AnnotationTools(props: AnnotationToolsProps) {
  /** Render compact controls used before saving a drawn bounding box. */
  const selectedLabel = props.labels.find((label) => label.id === props.selectedLabelId);
  const hasLabels = props.labels.length > 0;

  return (
    <section className="border-b border-slate-200 bg-white p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
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
        <label className="text-xs font-medium text-slate-600">
          Type
          <select className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100 disabled:text-slate-500" disabled={!hasLabels} value={props.annotationType} onChange={(event) => props.onAnnotationTypeChange(event.target.value as AnnotationType)}>
            <option value="bounding_box">Bounding box</option>
            <option value="polygon">Polygon</option>
            <option value="segmentation">Segmentation</option>
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Annotator
          <input className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-sm" value={props.createdBy} readOnly />
        </label>
      </div>
      {!hasLabels ? <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">Add a project label before drawing annotations.</p> : null}
    </section>
  );
}
