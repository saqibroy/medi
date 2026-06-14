import { FormEvent, useState } from "react";

import type { Label } from "../types/project";

interface LabelManagerProps {
  labels: Label[];
  selectedLabelId: string;
  canManage: boolean;
  isLoading: boolean;
  error: string | null;
  onSelectLabel: (labelId: string) => void;
  onCreateLabel: (payload: { name: string; color: string; description: string | null }) => Promise<void>;
  onUpdateLabel: (labelId: string, payload: { name: string; color: string; description: string | null }) => Promise<void>;
  onDeleteLabel: (labelId: string) => Promise<void>;
}

const defaultColor = "#14b8a6";

export function LabelManager({ labels, selectedLabelId, canManage, isLoading, error: loadError, onSelectLabel, onCreateLabel, onUpdateLabel, onDeleteLabel }: LabelManagerProps) {
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(defaultColor);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingColor, setEditingColor] = useState(defaultColor);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    try {
      await onCreateLabel({ name: newName.trim(), color: newColor, description: null });
      setNewName("");
      setNewColor(defaultColor);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not create label");
    }
  }

  function startEditing(label: Label): void {
    setEditingId(label.id);
    setEditingName(label.name);
    setEditingColor(label.color);
    setError(null);
  }

  async function saveEditing(label: Label): Promise<void> {
    if (!editingName.trim()) return;
    setError(null);
    try {
      await onUpdateLabel(label.id, { name: editingName.trim(), color: editingColor, description: label.description });
      setEditingId(null);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not update label");
    }
  }

  async function handleDelete(labelId: string): Promise<void> {
    setError(null);
    try {
      await onDeleteLabel(labelId);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not delete label");
    }
  }

  return (
    <section className="border-b border-slate-200 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Labels</h2>
      {canManage ? (
        <form className="mb-3 grid grid-cols-[1fr_38px] gap-2" onSubmit={handleCreate}>
          <input className="min-w-0 rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="New label" value={newName} onChange={(event) => setNewName(event.target.value)} />
          <input className="h-8 w-full cursor-pointer rounded-md border border-slate-300 p-1" type="color" value={newColor} onChange={(event) => setNewColor(event.target.value)} />
          <button className="col-span-2 rounded-md bg-slate-900 px-2 py-1.5 text-sm font-medium text-white disabled:bg-slate-400" disabled={!newName.trim()} type="submit">
            Add Label
          </button>
        </form>
      ) : null}
      {loadError ? <p className="mb-2 text-xs text-red-700">{loadError}</p> : null}
      {error ? <p className="mb-2 text-xs text-red-700">{error}</p> : null}
      {isLoading ? <p className="text-xs text-slate-500">Loading labels...</p> : null}
      {!isLoading && labels.length === 0 ? (
        <p className="text-xs text-slate-500">{canManage ? "Add labels before annotators start drawing." : "No labels have been added to this project."}</p>
      ) : null}
      <div className="space-y-2">
        {labels.map((label) => (
          <article key={label.id} className={`rounded-md border p-2 text-sm ${label.id === selectedLabelId ? "border-teal-500 bg-teal-50" : "border-slate-200 bg-white"}`}>
            {editingId === label.id ? (
              <div className="space-y-2">
                <div className="grid grid-cols-[1fr_36px] gap-2">
                  <input className="min-w-0 rounded-md border border-slate-300 px-2 py-1 text-sm" value={editingName} onChange={(event) => setEditingName(event.target.value)} />
                  <input className="h-8 w-full cursor-pointer rounded-md border border-slate-300 p-1" type="color" value={editingColor} onChange={(event) => setEditingColor(event.target.value)} />
                </div>
                <div className="flex gap-2">
                  <button className="rounded-md border border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50" onClick={() => saveEditing(label)} type="button">
                    Save
                  </button>
                  <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50" onClick={() => setEditingId(null)} type="button">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <button className="flex w-full items-center gap-2 text-left" onClick={() => onSelectLabel(label.id)} type="button">
                  <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-200" style={{ backgroundColor: label.color }} />
                  <span className="min-w-0 flex-1 truncate font-medium text-slate-900">{label.name}</span>
                </button>
                {canManage ? (
                  <div className="mt-2 flex gap-2">
                    <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50" onClick={() => startEditing(label)} type="button">
                      Edit
                    </button>
                    <button className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50" onClick={() => handleDelete(label.id)} type="button">
                      Delete
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
