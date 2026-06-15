import { FormEvent, useState } from "react";

import type { Modality, ScanCreate, ScanUpload } from "../types/scan";

interface ScanManagerProps {
  projectId?: string;
  canCreate: boolean;
  defaultModality?: Modality;
  onCreateScan: (payload: ScanCreate) => Promise<void>;
  onUploadScan: (payload: ScanUpload) => Promise<void>;
}

const modalities: Modality[] = ["MRI", "CT", "PET", "Ultrasound", "XRAY"];
const scanUploadAccept = ".nii,.nii.gz,.dcm,.zip,application/dicom,application/gzip,application/zip";

export function ScanManager({ projectId, canCreate, defaultModality = "MRI", onCreateScan, onUploadScan }: ScanManagerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [modality, setModality] = useState<Modality>(defaultModality);
  const [numSlices, setNumSlices] = useState(64);
  const [fileName, setFileName] = useState("synthetic-volume.nii.gz");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  function openForm(): void {
    setIsOpen(true);
    setModality(defaultModality);
    setError(null);
  }

  function closeForm(): void {
    setIsOpen(false);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (isSaving || !projectId || !name.trim() || (!file && (numSlices < 1 || !fileName.trim()))) return;
    setError(null);
    setIsSaving(true);
    try {
      if (file) {
        await onUploadScan({ project_id: projectId, name: name.trim(), modality, file });
      } else {
        await onCreateScan({
          project_id: projectId,
          name: name.trim(),
          modality,
          num_slices: numSlices,
          file_name: fileName.trim(),
        });
      }
      setName("");
      setNumSlices(64);
      setFileName("synthetic-volume.nii.gz");
      setFile(null);
      closeForm();
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Could not create scan");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="border-b border-slate-200 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Scans</h2>
        {canCreate ? (
          <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:text-slate-400" disabled={!projectId} onClick={openForm} type="button">
            New
          </button>
        ) : null}
      </div>
      {isOpen ? (
        <form className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3" onSubmit={handleSubmit}>
          <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="Scan name" value={name} onChange={(event) => setName(event.target.value)} />
          <div className={file ? "grid grid-cols-1" : "grid grid-cols-[1fr_88px] gap-2"}>
            <select className="min-w-0 rounded-md border border-slate-300 px-2 py-1 text-sm" value={modality} onChange={(event) => setModality(event.target.value as Modality)}>
              {modalities.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {!file ? <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" min={1} type="number" value={numSlices} onChange={(event) => setNumSlices(Number(event.target.value))} /> : null}
          </div>
          {!file ? <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="File name" value={fileName} onChange={(event) => setFileName(event.target.value)} /> : null}
          <input accept={scanUploadAccept} className="w-full rounded-md border border-slate-300 px-2 py-1 text-xs file:mr-2 file:rounded file:border-0 file:bg-slate-900 file:px-2 file:py-1 file:text-xs file:font-medium file:text-white" type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          {file ? <p className="text-xs text-slate-500">Slice count will be parsed for NIfTI, DICOM, and zipped DICOM uploads.</p> : null}
          {isSaving ? <p className="text-xs text-slate-500">{file ? "Uploading and parsing scan..." : "Creating placeholder scan..."}</p> : null}
          {error ? <p className="rounded-md bg-red-50 p-2 text-xs text-red-700">{error}</p> : null}
          <div className="flex gap-2">
            <button className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:bg-slate-400" disabled={isSaving || !name.trim() || (!file && (!fileName.trim() || numSlices < 1))} type="submit">
              {isSaving ? "Saving..." : file ? "Upload" : "Create"}
            </button>
            <button className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-white disabled:text-slate-400" disabled={isSaving} onClick={closeForm} type="button">
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
