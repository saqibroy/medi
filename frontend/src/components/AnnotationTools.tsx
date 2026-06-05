/** Tool panel for choosing annotation metadata before drawing.
 *
 * Medical tools often separate geometry capture from semantic labeling: the box
 * tells us where, while label/type tells us what it means.
 */

import type { AnnotationType } from "../types/annotation";

interface AnnotationToolsProps {
  label: string;
  annotationType: AnnotationType;
  createdBy: string;
  onLabelChange: (value: string) => void;
  onAnnotationTypeChange: (value: AnnotationType) => void;
  onCreatedByChange: (value: string) => void;
}

export function AnnotationTools(props: AnnotationToolsProps) {
  /** Render compact controls used before saving a drawn bounding box. */
  return (
    <section className="border-b border-slate-200 bg-white p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <label className="text-xs font-medium text-slate-600">
          Label
          <input className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" value={props.label} onChange={(event) => props.onLabelChange(event.target.value)} />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Type
          <select className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" value={props.annotationType} onChange={(event) => props.onAnnotationTypeChange(event.target.value as AnnotationType)}>
            <option value="bounding_box">Bounding box</option>
            <option value="polygon">Polygon</option>
            <option value="segmentation">Segmentation</option>
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Created by
          <input className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" value={props.createdBy} onChange={(event) => props.onCreatedByChange(event.target.value)} />
        </label>
      </div>
    </section>
  );
}
