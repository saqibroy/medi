/** Application shell for the medical image annotation frontend.
 *
 * App composes data hooks and presentational components so a developer can trace
 * the full flow from API data to viewer state to saved annotation overlays.
 */

import { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { getCsrfToken, getMe, listUsers, login, logout } from "./api/authApi";
import { createProject, createProjectLabel, deleteProjectLabel, getProjectStats, listProjectLabels, listProjects, updateProject, updateProjectLabel } from "./api/projectsApi";
import { createScan, getScanStats, uploadScan } from "./api/scansApi";
import { AnnotationList } from "./components/AnnotationList";
import { AnnotationTools, type ViewerTool } from "./components/AnnotationTools";
import { DatasetReleasePanel } from "./components/DatasetReleasePanel";
import { DataGovernancePanel } from "./components/DataGovernancePanel";
import { ExportPanel } from "./components/ExportPanel";
import { ExternalAIGovernancePanel } from "./components/ExternalAIGovernancePanel";
import { PrivacyGovernancePanel } from "./components/PrivacyGovernancePanel";
import { LabelManager } from "./components/LabelManager";
import { ProjectManager } from "./components/ProjectManager";
import { ReviewSummaryPanel } from "./components/ReviewSummaryPanel";
import { ScanList } from "./components/ScanList";
import { ScanManager } from "./components/ScanManager";
import { ScanMetadataPanel } from "./components/ScanMetadataPanel";
import { SliceNavigator } from "./components/SliceNavigator";
import { WindowLevelControls } from "./components/WindowLevelControls";
import { useAnnotations } from "./hooks/useAnnotations";
import { useScan } from "./hooks/useScan";
import type { Label, Project, ProjectPayload } from "./types/project";
import type { ProjectReviewStats, ReviewStats, ScanCreate, ScanUpload } from "./types/scan";
import type { User } from "./types/user";

const ViewerPanel = lazy(() => import("./components/ViewerPanel").then((module) => ({ default: module.ViewerPanel })));

function ViewerFallback() {
  return (
    <main className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div className="flex min-h-0 flex-1 items-center justify-center p-4">
        <p className="text-sm text-slate-300">Loading viewer...</p>
      </div>
    </main>
  );
}

export default function App() {
  /** Own global page state and pass focused props down to child components. */
  const [csrfToken, setCsrfToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [labels, setLabels] = useState<Label[]>([]);
  const [workspaceUsers, setWorkspaceUsers] = useState<User[]>([]);
  const [selectedLabelId, setSelectedLabelId] = useState("");
  const [viewerTool, setViewerTool] = useState<ViewerTool>("select");
  const [loginEmail, setLoginEmail] = useState("admin@medi.local");
  const [loginPassword, setLoginPassword] = useState("password");
  const [authError, setAuthError] = useState<string | null>(null);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [labelsError, setLabelsError] = useState<string | null>(null);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);
  const [isLabelsLoading, setIsLabelsLoading] = useState(false);
  const [projectReviewStats, setProjectReviewStats] = useState<ProjectReviewStats | null>(null);
  const [scanReviewStats, setScanReviewStats] = useState<ReviewStats | null>(null);
  const [reviewStatsError, setReviewStatsError] = useState<string | null>(null);
  const [isProjectStatsLoading, setIsProjectStatsLoading] = useState(false);
  const [isScanStatsLoading, setIsScanStatsLoading] = useState(false);
  const [windowCenter, setWindowCenter] = useState(600);
  const [windowWidth, setWindowWidth] = useState(1200);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);

  const { scans, selectedScan, sliceIndex, sliceImage, isLoading: isScansLoading, error, selectScan, addScan, setSliceIndex } = useScan(selectedProject?.id, csrfToken || undefined);
  const {
    annotations,
    annotationHistory,
    historyError,
    isHistoryLoading,
    loadAnnotationHistory,
    saveAnnotation,
    updateExistingAnnotation,
    removeAnnotation,
    reviewExistingAnnotation,
    saveSegmentationMask,
    loadSegmentationMask,
    removeSegmentationMask,
  } = useAnnotations(selectedScan?.id, csrfToken, user?.full_name ?? "Reviewer");
  const selectedLabel = useMemo(() => labels.find((label) => label.id === selectedLabelId) ?? labels[0] ?? null, [labels, selectedLabelId]);
  const canManageWorkspace = user?.role === "admin";
  const canAnnotate = user?.role === "admin" || user?.role === "annotator";
  const canReview = user?.role === "admin" || user?.role === "reviewer";
  const canDrawAnnotations = canAnnotate && Boolean(selectedLabel) && selectedScan?.ingestion_status === "ready";
  const annotationBlockedMessage = selectedScan?.ingestion_status === "quarantined"
    ? "This scan is quarantined and cannot be viewed or annotated. Upload a remediated de-identified copy."
    : canAnnotate && selectedProject && selectedScan && !isLabelsLoading && !selectedLabel
      ? "Add a project label before drawing annotations."
      : null;
  const workspaceStats = useMemo(
    () => ({
      scans: scans.length,
      labels: labels.length,
      annotations: annotations.length,
      approved: annotations.filter((annotation) => annotation.review_status === "approved").length,
      pending: annotations.filter((annotation) => annotation.review_status === "pending").length,
    }),
    [annotations, labels.length, scans.length],
  );
  const viewerEmptyMessage = !selectedProject
    ? "Create or select a project to begin."
    : scans.length === 0
      ? "Add a scan to this project to open the viewer."
      : labels.length === 0
        ? "Add at least one label before annotation begins."
        : selectedScan?.ingestion_status === "pending" || selectedScan?.ingestion_status === "processing"
          ? "Scan ingestion is still processing."
          : selectedScan?.ingestion_status === "quarantined"
            ? "Scan quarantined by the medical-image intake policy. Upload a remediated de-identified copy."
          : selectedScan?.ingestion_status === "failed"
            ? selectedScan.ingestion_error ?? "Scan ingestion failed."
            : "Loading selected scan...";
  const defaultWindowCenter = selectedScan?.window_center ?? 600;
  const defaultWindowWidth = selectedScan?.window_width ?? 1200;

  useEffect(() => {
    getCsrfToken()
      .then(async (issuedToken) => {
        setCsrfToken(issuedToken);
        try {
          setUser(await getMe());
        } catch {
          setUser(null);
        }
      })
      .catch((apiError: Error) => setAuthError(apiError.message));
  }, []);

  useEffect(() => {
    if (!csrfToken || !user) {
      setWorkspaceUsers([]);
      setUsersError(null);
      return;
    }
    listUsers(csrfToken)
      .then(setWorkspaceUsers)
      .catch((apiError: Error) => setUsersError(apiError.message));
  }, [csrfToken, user]);

  useEffect(() => {
    if (!csrfToken || !user) return;
    setIsProjectsLoading(true);
    setProjectsError(null);
    listProjects(csrfToken)
      .then((loadedProjects) => {
        setProjects(loadedProjects);
        setSelectedProject((current) => current ?? loadedProjects[0] ?? null);
      })
      .catch((apiError: Error) => setProjectsError(apiError.message))
      .finally(() => setIsProjectsLoading(false));
  }, [csrfToken, user]);

  useEffect(() => {
    if (!csrfToken || !selectedProject) {
      setLabels([]);
      setLabelsError(null);
      return;
    }
    setIsLabelsLoading(true);
    setLabelsError(null);
    listProjectLabels(selectedProject.id, csrfToken)
      .then((loadedLabels) => {
        setLabels(loadedLabels);
        setSelectedLabelId(loadedLabels[0]?.id ?? "");
      })
      .catch((apiError: Error) => setLabelsError(apiError.message))
      .finally(() => setIsLabelsLoading(false));
  }, [csrfToken, selectedProject]);

  useEffect(() => {
    if (!csrfToken || !selectedProject) {
      setProjectReviewStats(null);
      setReviewStatsError(null);
      return;
    }
    setIsProjectStatsLoading(true);
    setReviewStatsError(null);
    getProjectStats(selectedProject.id, csrfToken)
      .then(setProjectReviewStats)
      .catch((apiError: Error) => setReviewStatsError(apiError.message))
      .finally(() => setIsProjectStatsLoading(false));
  }, [annotations, selectedProject, csrfToken]);

  useEffect(() => {
    if (!csrfToken || !selectedScan || selectedScan.ingestion_status !== "ready") {
      setScanReviewStats(null);
      return;
    }
    setIsScanStatsLoading(true);
    setReviewStatsError(null);
    getScanStats(selectedScan.id, csrfToken)
      .then(setScanReviewStats)
      .catch((apiError: Error) => setReviewStatsError(apiError.message))
      .finally(() => setIsScanStatsLoading(false));
  }, [annotations, selectedScan, csrfToken]);

  useEffect(() => {
    setWindowCenter(defaultWindowCenter);
    setWindowWidth(defaultWindowWidth);
    setSelectedAnnotationId(null);
  }, [defaultWindowCenter, defaultWindowWidth, selectedScan?.id]);

  useEffect(() => {
    if (!selectedLabel && (viewerTool === "bounding_box" || viewerTool === "polygon" || viewerTool === "segmentation")) {
      setViewerTool("select");
    }
  }, [selectedLabel, viewerTool]);

  useEffect(() => {
    if (!annotations.some((annotation) => annotation.id === selectedAnnotationId)) {
      setSelectedAnnotationId(null);
    }
  }, [annotations, selectedAnnotationId]);

  useEffect(() => {
    void loadAnnotationHistory(selectedAnnotationId);
  }, [annotations, loadAnnotationHistory, selectedAnnotationId]);

  async function handleLogin(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setAuthError(null);
    try {
      const loginCsrfToken = csrfToken || await getCsrfToken();
      const response = await login(loginEmail, loginPassword, loginCsrfToken);
      setCsrfToken(response.csrf_token);
      setUser(response.user);
    } catch (apiError) {
      setAuthError(apiError instanceof Error ? apiError.message : "Login failed");
    }
  }

  async function handleLogout(): Promise<void> {
    try {
      if (csrfToken) await logout(csrfToken);
    } finally {
      setCsrfToken("");
      setUser(null);
      setProjects([]);
      setSelectedProject(null);
      setLabels([]);
      setProjectsError(null);
      setLabelsError(null);
      getCsrfToken().then(setCsrfToken).catch((apiError: Error) => setAuthError(apiError.message));
    }
  }

  function handleSelectProject(projectId: string): void {
    setSelectedProject(projects.find((project) => project.id === projectId) ?? null);
  }

  async function handleCreateProject(payload: ProjectPayload): Promise<void> {
    if (!csrfToken) return;
    const created = await createProject(csrfToken, payload);
    setProjects((current) => [created, ...current]);
    setSelectedProject(created);
  }

  async function handleUpdateProject(projectId: string, payload: ProjectPayload): Promise<void> {
    if (!csrfToken) return;
    const updated = await updateProject(projectId, csrfToken, payload);
    setProjects((current) => current.map((project) => (project.id === updated.id ? updated : project)));
    setSelectedProject((current) => (current?.id === updated.id ? updated : current));
  }

  async function handleCreateLabel(payload: { name: string; color: string; description: string | null }): Promise<void> {
    if (!selectedProject || !csrfToken) return;
    const created = await createProjectLabel(selectedProject.id, csrfToken, payload);
    setLabels((current) => [...current, created].sort((left, right) => left.name.localeCompare(right.name)));
    setSelectedLabelId(created.id);
  }

  async function handleUpdateLabel(labelId: string, payload: { name: string; color: string; description: string | null }): Promise<void> {
    if (!csrfToken) return;
    const updated = await updateProjectLabel(labelId, csrfToken, payload);
    setLabels((current) => current.map((label) => (label.id === updated.id ? updated : label)).sort((left, right) => left.name.localeCompare(right.name)));
  }

  async function handleDeleteLabel(labelId: string): Promise<void> {
    if (!csrfToken) return;
    await deleteProjectLabel(labelId, csrfToken);
    setLabels((current) => {
      const remaining = current.filter((label) => label.id !== labelId);
      if (selectedLabelId === labelId) {
        setSelectedLabelId(remaining[0]?.id ?? "");
      }
      return remaining;
    });
  }

  async function handleCreateScan(payload: ScanCreate): Promise<void> {
    if (!csrfToken || !selectedProject) return;
    const created = await createScan({ ...payload, project_id: selectedProject.id }, csrfToken);
    addScan(created);
  }

  async function handleUploadScan(payload: ScanUpload): Promise<void> {
    if (!csrfToken || !selectedProject) return;
    const uploaded = await uploadScan({ ...payload, project_id: selectedProject.id }, csrfToken);
    addScan(uploaded);
  }

  async function handleDeleteAnnotation(annotationId: string): Promise<void> {
    await removeAnnotation(annotationId);
    if (selectedAnnotationId === annotationId) {
      setSelectedAnnotationId(null);
    }
  }

  const selectAdjacentLabel = useCallback(
    (direction: 1 | -1): void => {
      if (labels.length === 0) return;
      const currentIndex = Math.max(0, labels.findIndex((label) => label.id === selectedLabelId));
      const nextIndex = (currentIndex + direction + labels.length) % labels.length;
      setSelectedLabelId(labels[nextIndex].id);
    },
    [labels, selectedLabelId],
  );

  useEffect(() => {
    if (!user) return;

    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null;
      if (target && (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName) || target.isContentEditable)) return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;

      const selectedAnnotation = annotations.find((annotation) => annotation.id === selectedAnnotationId);
      if (event.key === "v" || event.key === "V") {
        event.preventDefault();
        setViewerTool("select");
        return;
      }
      if (event.key === "h" || event.key === "H") {
        event.preventDefault();
        setViewerTool("pan");
        return;
      }
      if (event.key === "b" || event.key === "B") {
        event.preventDefault();
        setViewerTool("bounding_box");
        return;
      }
      if (event.key === "p" || event.key === "P") {
        event.preventDefault();
        setViewerTool("polygon");
        return;
      }
      if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        setViewerTool("segmentation");
        return;
      }
      if (event.key === "[") {
        event.preventDefault();
        selectAdjacentLabel(-1);
        return;
      }
      if (event.key === "]") {
        event.preventDefault();
        selectAdjacentLabel(1);
        return;
      }
      if (event.key === "ArrowLeft" && selectedScan) {
        event.preventDefault();
        setSliceIndex(Math.max(0, sliceIndex - 1));
        return;
      }
      if (event.key === "ArrowRight" && selectedScan) {
        event.preventDefault();
        setSliceIndex(Math.min(Math.max(selectedScan.num_slices - 1, 0), sliceIndex + 1));
        return;
      }
      if (!canReview || !selectedAnnotation) return;
      if (event.key === "a" || event.key === "A") {
        event.preventDefault();
        void reviewExistingAnnotation(selectedAnnotation.id, "approved");
      }
      if (event.key === "n" || event.key === "N") {
        event.preventDefault();
        void reviewExistingAnnotation(selectedAnnotation.id, "needs_changes");
      }
      if (event.key === "r" || event.key === "R") {
        event.preventDefault();
        void reviewExistingAnnotation(selectedAnnotation.id, "rejected");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [annotations, canReview, reviewExistingAnnotation, selectAdjacentLabel, selectedAnnotationId, selectedScan, setSliceIndex, sliceIndex, user]);

  if (!user) {
    return (
      <main className="flex h-full items-center justify-center bg-slate-100 p-6">
        <form className="w-full max-w-sm rounded-md border border-slate-200 bg-white p-5 shadow-sm" onSubmit={handleLogin}>
          <h1 className="text-xl font-semibold text-slate-950">Medi</h1>
          <p className="mt-1 text-sm text-slate-600">Medical imaging annotation workspace</p>
          <label className="mt-5 block text-xs font-medium text-slate-600">
            Email
            <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} />
          </label>
          <label className="mt-3 block text-xs font-medium text-slate-600">
            Password
            <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} />
          </label>
          {authError ? <p className="mt-3 text-sm text-red-700">{authError}</p> : null}
          <button className="mt-5 w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white" type="submit">
            Sign in
          </button>
        </form>
      </main>
    );
  }

  return (
    <div className="grid min-h-full grid-cols-1 overflow-y-auto lg:h-full lg:grid-cols-[240px_minmax(0,1fr)_280px] lg:overflow-hidden xl:grid-cols-[280px_minmax(0,1fr)_320px]">
      <aside className="border-r border-slate-200 bg-white lg:h-full lg:overflow-y-auto">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold text-slate-950">Medi</h1>
              <p className="text-xs text-slate-500">{user.full_name}</p>
            </div>
            <button className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50" onClick={() => void handleLogout()}>
              Sign out
            </button>
          </div>
        </div>
        <ProjectManager
          projects={projects}
          selectedProjectId={selectedProject?.id}
          canManage={canManageWorkspace}
          isLoading={isProjectsLoading}
          error={projectsError}
          onSelectProject={handleSelectProject}
          onCreateProject={handleCreateProject}
          onUpdateProject={handleUpdateProject}
        />
        <div className="border-b border-slate-200 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Workspace</h2>
          <div className="grid grid-cols-2 gap-2 text-center text-sm">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
              <p className="text-xs text-slate-500">Scans</p>
              <p className="font-semibold text-slate-950">{workspaceStats.scans}</p>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
              <p className="text-xs text-slate-500">Labels</p>
              <p className="font-semibold text-slate-950">{workspaceStats.labels}</p>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
              <p className="text-xs text-slate-500">Approved</p>
              <p className="font-semibold text-emerald-700">{workspaceStats.approved}</p>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
              <p className="text-xs text-slate-500">Pending</p>
              <p className="font-semibold text-amber-700">{workspaceStats.pending}</p>
            </div>
          </div>
        </div>
        <ReviewSummaryPanel projectStats={projectReviewStats} scanStats={scanReviewStats} isLoading={isProjectStatsLoading || isScanStatsLoading} error={reviewStatsError} />
        <LabelManager
          labels={labels}
          selectedLabelId={selectedLabel?.id ?? ""}
          canManage={canManageWorkspace}
          isLoading={isLabelsLoading}
          error={labelsError}
          onSelectLabel={setSelectedLabelId}
          onCreateLabel={handleCreateLabel}
          onUpdateLabel={handleUpdateLabel}
          onDeleteLabel={handleDeleteLabel}
        />
        <ScanManager projectId={selectedProject?.id} canCreate={canManageWorkspace} defaultModality={selectedProject?.modality} onCreateScan={handleCreateScan} onUploadScan={handleUploadScan} />
        <ScanList scans={scans} selectedScanId={selectedScan?.id} isLoading={isScansLoading} hasProject={Boolean(selectedProject)} onSelectScan={selectScan} />
      </aside>
      <div className="flex min-h-[42rem] min-w-0 flex-col lg:min-h-0">
        <AnnotationTools
          labels={labels}
          selectedLabelId={selectedLabel?.id ?? ""}
          viewerTool={viewerTool}
          createdBy={user.full_name}
          onLabelChange={setSelectedLabelId}
          onViewerToolChange={setViewerTool}
        />
        {error ? <div className="bg-red-50 p-2 text-sm text-red-700">{error}</div> : null}
        {authError ? <div className="bg-red-50 p-2 text-sm text-red-700">{authError}</div> : null}
        {usersError ? <div className="bg-red-50 p-2 text-sm text-red-700">{usersError}</div> : null}
        <Suspense fallback={<ViewerFallback />}>
          <ViewerPanel
            scan={selectedScan}
            sliceImage={sliceImage}
            sliceIndex={sliceIndex}
            annotations={annotations}
            label={selectedLabel?.name ?? "unlabeled"}
            labelId={selectedLabel?.id}
            projectId={selectedProject?.id}
            viewerTool={viewerTool}
            createdBy={user.full_name}
            canAnnotate={canDrawAnnotations}
            canDeleteAnnotation={canManageWorkspace}
            selectedAnnotationId={selectedAnnotationId}
            windowCenter={windowCenter}
            windowWidth={windowWidth}
            emptyMessage={viewerEmptyMessage}
            annotationBlockedMessage={annotationBlockedMessage}
            onSelectAnnotation={setSelectedAnnotationId}
            onSliceChange={setSliceIndex}
            onSaveAnnotation={saveAnnotation}
            onUpdateAnnotation={updateExistingAnnotation}
            onDeleteAnnotation={handleDeleteAnnotation}
            onSaveMask={saveSegmentationMask}
            onLoadMask={loadSegmentationMask}
            onDeleteMask={removeSegmentationMask}
          />
        </Suspense>
        <WindowLevelControls center={windowCenter} width={windowWidth} onCenterChange={setWindowCenter} onWidthChange={setWindowWidth} onReset={() => {
          setWindowCenter(defaultWindowCenter);
          setWindowWidth(defaultWindowWidth);
        }} />
        <SliceNavigator sliceIndex={sliceIndex} maxSliceIndex={Math.max((selectedScan?.num_slices ?? 1) - 1, 0)} onSliceChange={setSliceIndex} />
      </div>
      <aside className="flex min-h-0 flex-col border-l border-slate-200 bg-white lg:h-full">
        <ScanMetadataPanel scanId={selectedScan?.id} csrfToken={csrfToken} />
        {canManageWorkspace ? <DataGovernancePanel projectId={selectedProject?.id} csrfToken={csrfToken} /> : null}
        {canManageWorkspace ? <PrivacyGovernancePanel projectId={selectedProject?.id} csrfToken={csrfToken} /> : null}
        {canManageWorkspace ? <ExternalAIGovernancePanel projectId={selectedProject?.id} csrfToken={csrfToken} /> : null}
        <DatasetReleasePanel projectId={selectedProject?.id} csrfToken={csrfToken} canManage={canManageWorkspace} />
        <ExportPanel projectId={selectedProject?.id} scanId={selectedScan?.id} csrfToken={csrfToken} />
        <AnnotationList
          annotations={annotations}
          annotationHistory={annotationHistory}
          historyError={historyError}
          isHistoryLoading={isHistoryLoading}
          labels={labels}
          users={workspaceUsers}
          currentSlice={sliceIndex}
          selectedAnnotationId={selectedAnnotationId}
          canAnnotate={canAnnotate}
          canReview={canReview}
          canDelete={canManageWorkspace}
          onSelectAnnotation={setSelectedAnnotationId}
          onDelete={handleDeleteAnnotation}
          onUpdateAnnotation={updateExistingAnnotation}
          onReview={reviewExistingAnnotation}
        />
      </aside>
    </div>
  );
}
