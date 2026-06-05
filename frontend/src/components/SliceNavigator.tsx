/** Slice slider for navigating through a 3D volume one 2D plane at a time. */

interface SliceNavigatorProps {
  sliceIndex: number;
  maxSliceIndex: number;
  onSliceChange: (sliceIndex: number) => void;
}

export function SliceNavigator({ sliceIndex, maxSliceIndex, onSliceChange }: SliceNavigatorProps) {
  /** Render a bounded range input so users cannot request impossible slices. */
  return (
    <div className="flex items-center gap-3 border-t border-slate-200 bg-white p-3">
      <span className="w-16 text-xs font-medium text-slate-600">Slice {sliceIndex}</span>
      <input
        className="h-2 flex-1"
        type="range"
        min={0}
        max={maxSliceIndex}
        value={sliceIndex}
        onChange={(event) => onSliceChange(Number(event.target.value))}
      />
      <span className="w-16 text-right text-xs text-slate-500">0-{maxSliceIndex}</span>
    </div>
  );
}
