import { FormEvent, useState } from "react";

import type { Project, ProjectPayload } from "../types/project";
import type { Modality } from "../types/scan";

interface ProjectManagerProps {
  projects: Project[];
  selectedProjectId?: string;
  canManage: boolean;
  isLoading: boolean;
  error: string | null;
  onSelectProject: (projectId: string) => void;
  onCreateProject: (payload: ProjectPayload) => Promise<void>;
  onUpdateProject: (projectId: string, payload: ProjectPayload) => Promise<void>;
}

const modalities: Modality[] = ["MRI", "CT", "PET", "Ultrasound", "XRAY"];

export function ProjectManager({ projects, selectedProjectId, canManage, isLoading, error: loadError, onSelectProject, onCreateProject, onUpdateProject }: ProjectManagerProps) {
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const [isCreating, setIsCreating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [modality, setModality] = useState<Modality>("MRI");
  const [error, setError] = useState<string | null>(null);

  function beginCreate(): void {
    setIsCreating(true);
    setIsEditing(false);
    setName("");
    setDescription("");
    setModality("MRI");
    setError(null);
  }

  function beginEdit(): void {
    if (!selectedProject) return;
    setIsEditing(true);
    setIsCreating(false);
    setName(selectedProject.name);
    setDescription(selectedProject.description ?? "");
    setModality(selectedProject.modality);
    setError(null);
  }

  function closeForm(): void {
    setIsCreating(false);
    setIsEditing(false);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!name.trim()) return;
    const payload = { name: name.trim(), description: description.trim() || null, modality };
    setError(null);
    try {
      if (isEditing && selectedProject) {
        await onUpdateProject(selectedProject.id, payload);
      } else {
        await onCreateProject(payload);
      }
      closeForm();
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not save project");
    }
  }

  const showForm = isCreating || isEditing;

  return (
    <section className="border-b border-slate-200 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Projects</h2>
        {canManage ? (
          <div className="flex gap-2">
            <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50" onClick={beginCreate} type="button">
              New
            </button>
            <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:text-slate-400" disabled={!selectedProject} onClick={beginEdit} type="button">
              Edit
            </button>
          </div>
        ) : null}
      </div>
      <select className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" disabled={isLoading || projects.length === 0} value={selectedProjectId ?? ""} onChange={(event) => onSelectProject(event.target.value)}>
        {projects.length === 0 ? <option value="">No projects</option> : null}
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
      {selectedProject ? (
        <p className="mt-2 text-xs text-slate-500">
          {selectedProject.modality}
          {selectedProject.description ? ` | ${selectedProject.description}` : ""}
        </p>
      ) : null}
      {isLoading ? <p className="mt-2 text-xs text-slate-500">Loading projects...</p> : null}
      {loadError ? <p className="mt-2 text-xs text-red-700">{loadError}</p> : null}
      {!isLoading && !loadError && projects.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">{canManage ? "Create a project to start a dataset workspace." : "No projects are available for this workspace."}</p>
      ) : null}
      {showForm ? (
        <form className="mt-3 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3" onSubmit={handleSubmit}>
          <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="Project name" value={name} onChange={(event) => setName(event.target.value)} />
          <select className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" value={modality} onChange={(event) => setModality(event.target.value as Modality)}>
            {modalities.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <textarea className="min-h-16 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
          {error ? <p className="text-xs text-red-700">{error}</p> : null}
          <div className="flex gap-2">
            <button className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:bg-slate-400" disabled={!name.trim()} type="submit">
              {isEditing ? "Save" : "Create"}
            </button>
            <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-white" onClick={closeForm} type="button">
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
