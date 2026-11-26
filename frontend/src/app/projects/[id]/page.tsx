"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  Download,
  FileCheck2,
  FileSearch,
  FileText,
  FileUp,
  Globe,
  Layers,
  Paperclip,
  Play,
  Presentation,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import {
  getProject,
  listProjectDocuments,
  uploadProjectDocuments,
  deleteProjectDocument,
  ProjectStatus,
} from "@/lib/api";
import { useProjectWebSocket } from "@/lib/useProjectWebSocket";
import { LiveProgressConsole } from "@/components/LiveProgressConsole";
import { ExportModal } from "@/components/ExportModal";
import { DeleteProjectDialog } from "@/components/DeleteProjectDialog";
import { UserMenu } from "@/components/UserMenu";

const workflowSteps = [
  {
    step: 1,
    title: "Project Intake",
    desc: "Topic, objective & scope defined",
    icon: FileText,
    completedStates: [
      "draft",
      "running",
      "awaiting_review",
      "revision_requested",
      "approved",
      "generating",
      "completed",
    ],
  },
  {
    step: 2,
    title: "Research Engine",
    desc: "Search, fetch & evidence extraction",
    icon: FileSearch,
    completedStates: [
      "awaiting_review",
      "revision_requested",
      "approved",
      "generating",
      "completed",
    ],
    activeStates: ["running"],
  },
  {
    step: 3,
    title: "Consulting Synthesis",
    desc: "Findings, implications & QA gate",
    icon: SlidersHorizontal,
    completedStates: [
      "awaiting_review",
      "revision_requested",
      "approved",
      "generating",
      "completed",
    ],
    activeStates: ["running"],
  },
  {
    step: 4,
    title: "Human Review Gate",
    desc: "Approve, edit or research more",
    icon: FileCheck2,
    completedStates: ["approved", "generating", "completed"],
    activeStates: ["awaiting_review", "revision_requested"],
  },
  {
    step: 5,
    title: "Slide Storyline",
    desc: "Outline & key narrative messages",
    icon: Layers,
    completedStates: ["generating", "completed"],
    activeStates: ["approved"],
  },
  {
    step: 6,
    title: "PowerPoint Deck",
    desc: "Rendered PPTX ready for download",
    icon: Presentation,
    completedStates: ["completed"],
    activeStates: ["generating"],
  },
];

export default function ProjectDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const id = params.id;
  const router = useRouter();
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);

  const {
    data: project,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id),
  });

  const { data: documents = [], refetch: refetchDocs } = useQuery({
    queryKey: ["project-documents", id],
    queryFn: () => listProjectDocuments(id),
  });

  const [isUploadingDoc, setIsUploadingDoc] = useState(false);
  const [docUploadError, setDocUploadError] = useState<string | null>(null);

  const handleDocUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setDocUploadError(null);
      const allowedExtensions = [".pdf", ".txt"];
      const maxFiles = 3;
      const maxBytes = 10 * 1024 * 1024; // 10 MB
      const incoming = Array.from(e.target.files);

      if (documents.length + incoming.length > maxFiles) {
        setDocUploadError(`Maximum ${maxFiles} documents allowed per project (already have ${documents.length}).`);
        return;
      }

      for (const file of incoming) {
        const lower = file.name.toLowerCase();
        if (!allowedExtensions.some((ext) => lower.endsWith(ext))) {
          setDocUploadError(`Unsupported format for '${file.name}'. Only .pdf and .txt allowed.`);
          return;
        }
        if (file.size > maxBytes) {
          setDocUploadError(`'${file.name}' exceeds the 10 MB limit.`);
          return;
        }
      }

      setIsUploadingDoc(true);
      try {
        await uploadProjectDocuments(id, incoming);
        await refetchDocs();
      } catch (err: any) {
        setDocUploadError(err.message || "Failed to upload document.");
      } finally {
        setIsUploadingDoc(false);
        e.target.value = "";
      }
    }
  };

  const handleDocDelete = async (docId: string) => {
    try {
      await deleteProjectDocument(id, docId);
      await refetchDocs();
    } catch (err: any) {
      console.error("Failed to delete document:", err);
    }
  };

  const {
    isConnected,
    activeAgent,
    currentStep,
    progress,
    logs,
    reviewAlert,
    lastEvent,
  } = useProjectWebSocket(id, project?.status);

  // Sync React Query cache whenever status changes via websocket
  useEffect(() => {
    if (
      lastEvent?.type === "review_required" ||
      lastEvent?.type === "review_decided" ||
      lastEvent?.type === "storyline_ready" ||
      lastEvent?.type === "storyline_approved" ||
      lastEvent?.type === "artifact_generated"
    ) {
      refetch();
    }
  }, [lastEvent, refetch]);

  const handleStartWorkflow = async () => {
    try {
      const res = await fetch(`/api/projects/${id}/run`, { method: "POST" });
      const data = await res.json();
      setRunMessage(data.detail || "Workflow queued.");
    } catch (err: any) {
      setRunMessage(err.message || "Failed to start workflow.");
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-8 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-semibold text-slate-600 dark:text-slate-400">
            Loading project details...
          </p>
        </div>
      </div>
    );
  }

  if (isError || !project) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-8 flex items-center justify-center">
        <div className="max-w-md w-full rounded-2xl border border-rose-200 dark:border-rose-900 bg-white dark:bg-slate-900 p-8 text-center space-y-4">
          <p className="text-rose-600 font-bold">Project Not Found</p>
          <p className="text-xs text-slate-500">{error?.message}</p>
          <Link
            href="/"
            className="inline-block rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-semibold text-white shadow hover:bg-blue-700 transition"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] pb-20 font-sans">
      {/* ── Top Navigation ────────────────────────────────────────── */}
      <header className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#051C2C]/95 backdrop-blur sticky top-0 z-10 px-6 py-4">
        <div className="mx-auto max-w-5xl flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-semibold text-[#4A5568] dark:text-slate-300 hover:text-[#051C2C] dark:hover:text-white transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Engagements
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-1.5 text-xs text-[#4A5568] dark:text-slate-300 border border-[#E2E6EB] dark:border-slate-700 rounded px-3 py-1.5 bg-white dark:bg-slate-800 hover:bg-[#F7F9FB] transition"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setDeleteModalOpen(true)}
              className="inline-flex items-center gap-1.5 text-xs text-[#941B1B] dark:text-rose-400 border border-[#F5C2C2] dark:border-rose-900/60 rounded px-3 py-1.5 bg-[#FDF2F2] dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-950/80 transition"
              title="Delete this project"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete Engagement
            </button>
            <UserMenu />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pt-8 space-y-8">
        {/* ── Project Header Card ───────────────────────────────────── */}
        <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 sm:p-8 shadow-sm space-y-6 border-l-4 border-l-[#002B49]">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="space-y-1">
              <span className="kicker text-[#005A9C] dark:text-[#60A5FA]">
                Strategic Engagement Brief
              </span>
              <h1 className="text-2xl sm:text-3xl font-serif font-semibold text-[#051C2C] dark:text-white tracking-tight leading-snug">
                {project.topic}
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-2 self-start">
              <span className={`inline-flex items-center gap-1.5 rounded px-2.5 py-0.5 text-xs font-semibold border ${
                project.status === "completed"
                  ? "bg-[#EDF7F4] text-[#0D5E4D] border-[#B4DFD4]"
                  : project.status === "approved"
                  ? "bg-[#EDF7F4] text-[#0D5E4D] border-[#B4DFD4]"
                  : project.status === "awaiting_review"
                  ? "bg-[#FFF8EC] text-[#8D5B00] border-[#F5D6A0]"
                  : "bg-[#F0F6FC] text-[#005A9C] border-[#B9D7F2]"
              }`}>
                {project.status === "completed" && <CheckCircle2 className="w-3.5 h-3.5 text-[#0D5E4D]" />}
                Status: {project.status.replace("_", " ")}
              </span>

              {project.status === "awaiting_review" && (
                <Link
                  href={`/projects/${project.id}/review`}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded text-xs font-semibold bg-[#8D5B00] hover:bg-[#704800] text-white shadow-sm transition"
                >
                  <AlertCircle className="w-3.5 h-3.5" />
                  Review Gate
                </Link>
              )}

              {project.status === "approved" && (
                <div className="flex items-center gap-2">
                  <Link
                    href={`/projects/${project.id}/storyline`}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded text-xs font-semibold bg-[#002B49] hover:bg-[#051C2C] text-white shadow-sm transition"
                  >
                    <Layers className="w-3.5 h-3.5" />
                    Storyline Studio
                  </Link>
                  <button
                    onClick={() => setExportOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded text-xs font-semibold bg-[#0D5E4D] hover:bg-[#09473a] text-white shadow-sm transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export Deck
                  </button>
                </div>
              )}

              {project.status === "completed" && (
                <div className="flex items-center gap-2">
                  <Link
                    href={`/projects/${project.id}/storyline`}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded text-xs font-semibold bg-[#002B49] hover:bg-[#051C2C] text-white shadow-sm transition"
                  >
                    <Layers className="w-3.5 h-3.5" />
                    Storyline Studio
                  </Link>
                  <button
                    onClick={() => setExportOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded text-xs font-semibold bg-[#0D5E4D] hover:bg-[#09473a] text-white shadow-sm transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export Deck
                  </button>
                </div>
              )}
            </div>
          </div>

          <p className="text-xs text-[#334155] dark:text-slate-300 leading-relaxed border-t border-[#ECEFF2] dark:border-slate-800 pt-4 font-normal">
            {project.objective}
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2 text-xs">
            <div className="rounded border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-800/40">
              <span className="kicker text-[#718096] block mb-1 flex items-center gap-1 text-[10px]">
                <Users className="h-3 w-3 text-[#002B49]" /> Audience
              </span>
              <span className="font-semibold text-[#051C2C] dark:text-slate-200">
                {project.audience || "Executive Leadership"}
              </span>
            </div>
            <div className="rounded border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-800/40">
              <span className="kicker text-[#718096] block mb-1 flex items-center gap-1 text-[10px]">
                <Calendar className="h-3 w-3 text-[#002B49]" /> Horizon
              </span>
              <span className="font-semibold text-[#051C2C] dark:text-slate-200">
                {project.time_horizon || "Not specified"}
              </span>
            </div>
            <div className="rounded border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-800/40">
              <span className="kicker text-[#718096] block mb-1 flex items-center gap-1 text-[10px]">
                <Compass className="h-3 w-3 text-[#002B49]" /> Scope Depth
              </span>
              <span className="font-semibold text-[#051C2C] dark:text-slate-200 capitalize">
                {project.research_depth} Depth
              </span>
            </div>
            <div className="rounded border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-800/40">
              <span className="kicker text-[#718096] block mb-1 flex items-center gap-1 text-[10px]">
                <Paperclip className="h-3 w-3 text-[#002B49]" /> Internal Docs
              </span>
              <span className="font-semibold text-[#051C2C] dark:text-slate-200">
                {documents.length} Attached
              </span>
            </div>
          </div>

          {project.additional_context && (
            <div className="rounded-xl border border-blue-100 dark:border-blue-950/60 p-3.5 bg-blue-50/40 dark:bg-blue-950/20 text-xs mt-3">
              <span className="font-bold text-blue-900 dark:text-blue-300 block mb-1 flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                Additional Strategic Context
              </span>
              <p className="text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {project.additional_context}
              </p>
            </div>
          )}

          {/* Research Documents Card */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-slate-50/50 dark:bg-slate-800/40 mt-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                <Paperclip className="h-3.5 w-3.5 text-blue-600" />
                Attached Research Documents ({documents.length}/3)
              </span>
              {project.status === "draft" && documents.length < 3 && (
                <label className="cursor-pointer text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                  <FileUp className="h-3 w-3" />
                  {isUploadingDoc ? "Uploading..." : "Add Document"}
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.txt"
                    disabled={isUploadingDoc}
                    className="hidden"
                    onChange={handleDocUpload}
                  />
                </label>
              )}
            </div>

            {docUploadError && (
              <div className="flex items-center gap-1.5 text-xs text-rose-500 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 px-3 py-1.5 rounded-lg">
                <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                <span>{docUploadError}</span>
              </div>
            )}

            {documents.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700/60 bg-white dark:bg-slate-900 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FileText className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                      <span className="font-medium text-slate-800 dark:text-slate-200 truncate" title={doc.filename}>
                        {doc.filename}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <span className="text-[10px] text-slate-400">
                        {(doc.size_bytes / 1024).toFixed(1)} KB
                      </span>
                      {project.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => handleDocDelete(doc.id)}
                          className="text-slate-400 hover:text-rose-500 p-0.5 rounded transition"
                          title="Remove document"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 italic">
                No internal documents attached. Web search will be used as the primary source pool.
              </p>
            )}
          </div>
        </div>

        {/* ── Failure Alert Banner ─────────────────────────────────── */}
        {project.status === "failed" && (
          <div className="rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50/90 dark:bg-rose-950/40 p-5 shadow-sm space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-rose-900 dark:text-rose-200">
                    Workflow Run Failed
                  </h4>
                  <p className="text-xs text-rose-700 dark:text-rose-300 max-w-2xl font-mono">
                    {project.error_message || "An unexpected error occurred during execution."}
                  </p>
                </div>
              </div>
              <button
                onClick={handleStartWorkflow}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white shadow-sm transition shrink-0"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Retry Research Run
              </button>
            </div>
          </div>
        )}

        {/* ── Live Agent Telemetry & Push Notifications ────────────── */}
        <LiveProgressConsole
          projectId={id}
          isConnected={isConnected}
          activeAgent={activeAgent}
          currentStep={currentStep}
          progress={progress}
          logs={logs}
          reviewAlert={reviewAlert}
          projectStatus={project.status}
        />

        {/* ── Workflow Pipeline Tracker ─────────────────────────────── */}
        <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 sm:p-8 shadow-sm space-y-6 border-t-2 border-t-[#002B49]">
          <div className="flex items-center justify-between">
            <div>
              <span className="kicker text-[#005A9C] dark:text-[#60A5FA] block mb-1">Methodology Pipeline</span>
              <h2 className="text-lg font-serif font-semibold text-[#051C2C] dark:text-white flex items-center gap-2">
                <Layers className="h-5 w-5 text-[#002B49]" />
                Workflow Pipeline Architecture
              </h2>
              <p className="text-xs text-[#718096] mt-0.5">
                Explicit gates ensure human approval before slide generation.
              </p>
            </div>

            <div className="flex items-center gap-3">
              {["awaiting_review", "revision_requested", "approved"].includes(project.status) && (
                <Link
                  href={`/projects/${id}/review`}
                  className="inline-flex items-center gap-1.5 rounded bg-[#8D5B00] hover:bg-[#704800] px-4 py-2 text-xs font-semibold text-white shadow-sm transition"
                >
                  <FileCheck2 className="h-4 w-4" />
                  Review &amp; Approve Synthesis
                </Link>
              )}
              <button
                onClick={handleStartWorkflow}
                className="inline-flex items-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-4 py-2 text-xs font-semibold text-white shadow-sm transition"
              >
                <Play className="h-3.5 w-3.5" />
                Enqueue Research Run
              </button>
            </div>
          </div>

          {runMessage && (
            <div className="rounded border border-[#B9D7F2] dark:border-blue-900 bg-[#F0F6FC] dark:bg-blue-950/40 p-4 text-xs text-[#002B49] dark:text-blue-300">
              <strong className="kicker">Engine Status:</strong> {runMessage}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {workflowSteps.map((step) => {
              const Icon = step.icon;
              const isCompleted = step.completedStates.includes(project.status);
              const isActive = step.activeStates?.includes(project.status);

              return (
                <div
                  key={step.step}
                  className={`rounded-lg border p-4 transition ${
                    isCompleted
                      ? "border-[#B4DFD4] dark:border-emerald-900 bg-[#EDF7F4]/60 dark:bg-emerald-950/20"
                      : isActive
                      ? "border-[#002B49] bg-[#F0F6FC] dark:bg-blue-950/30 ring-1 ring-[#005A9C]"
                      : "border-[#E2E6EB] dark:border-slate-800 bg-[#F7F9FB]/60 dark:bg-slate-900/40 opacity-75"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-[10px] font-semibold text-[#718096]">
                      STEP 0{step.step}
                    </span>
                    {isCompleted ? (
                      <CheckCircle2 className="h-4 w-4 text-[#0D5E4D]" />
                    ) : isActive ? (
                      <span className="h-2 w-2 rounded-full bg-[#005A9C] animate-ping" />
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2 mb-1">
                    <Icon className="h-4 w-4 text-[#002B49] dark:text-slate-300" />
                    <h4 className="text-sm font-serif font-semibold text-[#051C2C] dark:text-white">
                      {step.title}
                    </h4>
                  </div>
                  <p className="text-xs text-[#718096] dark:text-slate-400 font-sans">
                    {step.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </main>

      {/* ── Export Modal ───────────────────────────────────────────── */}
      <ExportModal
        isOpen={exportOpen}
        onClose={() => setExportOpen(false)}
        projectId={id}
        projectTopic={project.topic}
      />

      {/* ── Delete Project Dialog ────────────────────────────────────── */}
      <DeleteProjectDialog
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        project={project}
        onSuccess={() => router.push("/")}
      />
    </div>
  );
}
