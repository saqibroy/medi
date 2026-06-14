interface WindowLevelControlsProps {
  center: number;
  width: number;
  onCenterChange: (value: number) => void;
  onWidthChange: (value: number) => void;
  onReset: () => void;
}

export function WindowLevelControls({ center, width, onCenterChange, onWidthChange, onReset }: WindowLevelControlsProps) {
  return (
    <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-3 border-t border-slate-200 bg-white p-3">
      <label className="text-xs font-medium text-slate-600">
        Center {Math.round(center)}
        <input className="mt-1 h-2 w-full" type="range" min={0} max={1200} step={1} value={center} onChange={(event) => onCenterChange(Number(event.target.value))} />
      </label>
      <label className="text-xs font-medium text-slate-600">
        Width {Math.round(width)}
        <input className="mt-1 h-2 w-full" type="range" min={1} max={2400} step={1} value={width} onChange={(event) => onWidthChange(Number(event.target.value))} />
      </label>
      <button className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50" type="button" onClick={onReset}>
        Reset
      </button>
    </div>
  );
}
