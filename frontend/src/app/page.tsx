"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BriefcaseBusiness,
  Clock,
  Compass,
  FileSpreadsheet,
  Globe,
  Layers,
  PlusCircle,
  RefreshCw,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { listProjects, Project, ProjectStatus } from "@/lib/api";
import { UserMenu } from "@/components/UserMenu";
import { DeleteProjectDialog } from "@/components/DeleteProjectDialog";

const statusConfig: Record<
  ProjectStatus,
  { label: string; bg: string; text: string; border: string; dot: string }
> = {
  draft: {
    label: "Draft",
    bg: "bg-[#F1F3F5] dark:bg-slate-800",
    text: "text-[#4A5568] dark:text-slate-300",
    border: "border-[#D9DEE4] dark:border-slate-700",
    dot: "bg-[#718096]",
  },
  running: {
    label: "Active Research",
    bg: "bg-[#F0F6FC] dark:bg-blue-950/40",
    text: "text-[#005A9C] dark:text-blue-300",
    border: "border-[#B9D7F2] dark:border-blue-900",
    dot: "bg-[#005A9C] animate-pulse",
  },
  awaiting_review: {
    label: "Review Gate Ready",
    bg: "bg-[#FFF8EC] dark:bg-amber-950/40",
    text: "text-[#8D5B00] dark:text-amber-300",
    border: "border-[#F5D6A0] dark:border-amber-900",
    dot: "bg-[#8D5B00]",
  },
  revision_requested: {
    label: "Revising Synthesis",
    bg: "bg-[#FFF8EC] dark:bg-amber-950/40",
    text: "text-[#8D5B00] dark:text-amber-300",
    border: "border-[#F5D6A0] dark:border-amber-900",
    dot: "bg-[#8D5B00]",
  },
  approved: {
    label: "Synthesis Approved",
    bg: "bg-[#EDF7F4] dark:bg-emerald-950/40",
    text: "text-[#0D5E4D] dark:text-emerald-300",
    border: "border-[#B4DFD4] dark:border-emerald-900",
    dot: "bg-[#0D5E4D]",
  },
  generating: {
    label: "Rendering Deck",
    bg: "bg-[#F0F6FC] dark:bg-indigo-950/40",
    text: "text-[#002B49] dark:text-indigo-300",
    border: "border-[#B9D7F2] dark:border-indigo-900",
    dot: "bg-[#002B49] animate-pulse",
  },
  completed: {
    label: "Deck Ready",
    bg: "bg-[#EDF7F4] dark:bg-emerald-900/40",
    text: "text-[#0D5E4D] dark:text-emerald-200",
    border: "border-[#B4DFD4] dark:border-emerald-800",
    dot: "bg-[#0D5E4D]",
  },
  failed: {
    label: "Needs Attention",
    bg: "bg-[#FDF2F2] dark:bg-rose-950/40",
    text: "text-[#941B1B] dark:text-rose-300",
    border: "border-[#F5C2C2] dark:border-rose-900",
    dot: "bg-[#941B1B]",
  },
};

export default function HomePage() {
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);

  const {
    data: projects,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  return (
    <main className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C]">
      {/* ── Header / Top Nav ────────────────────────────────────────── */}
      <header className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#051C2C]/95 backdrop-blur sticky top-0 z-10 px-6 py-4">
        <div className="mx-auto max-w-6xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded bg-[#002B49] p-2 text-white shadow-sm">
              <Layers className="h-5 w-5" />
            </div>
            <div>
              <span className="font-serif font-bold text-[#051C2C] dark:text-white tracking-tight text-base block">
                AI Consulting Platform
              </span>
              <span className="kicker text-[#005A9C] dark:text-[#60A5FA]">
                Enterprise Executive Edition
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/projects/new"
              className="inline-flex items-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-4 py-2 text-xs font-semibold text-white shadow-sm transition"
            >
              <PlusCircle className="h-4 w-4" />
              New Engagement
            </Link>
            <UserMenu />
          </div>
        </div>
      </header>

      {/* ── Hero Banner ──────────────────────────────────────────────── */}
      <section className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] px-6 py-12">
        <div className="mx-auto max-w-4xl text-center space-y-3">
          <div className="inline-flex items-center gap-2 rounded border border-[#B9D7F2] dark:border-slate-700 bg-[#F0F6FC] dark:bg-slate-800 px-3.5 py-1 text-[11px] kicker text-[#005A9C] dark:text-[#60A5FA]">
            <Sparkles className="h-3 w-3" />
            Research-to-Presentation with Explicit Human Review Gates
          </div>
          <h1 className="text-3xl sm:text-4xl font-serif font-semibold text-[#051C2C] dark:text-white tracking-tight">
            Consulting Brief to Executive Presentation
          </h1>
          <p className="text-sm text-[#4A5568] dark:text-slate-300 max-w-2xl mx-auto leading-relaxed">
            Input an executive question. Autonomous research agents query verified institutional sources,
            structure empirical evidence, synthesize strategic insights, and pause at quality gates for partner review before rendering PowerPoint deliverables.
          </p>
        </div>
      </section>

      {/* ── Projects List Section ────────────────────────────────────── */}
      <section className="mx-auto max-w-5xl px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <span className="kicker text-[#005A9C] block mb-1">Portfolio Overview</span>
            <h2 className="text-xl font-serif font-semibold text-[#051C2C] dark:text-white flex items-center gap-2">
              <BriefcaseBusiness className="h-5 w-5 text-[#002B49]" />
              Active Engagements
            </h2>
            <p className="text-xs text-[#718096]">
              Manage strategic research streams, review gates, and rendered slide decks.
            </p>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 text-xs text-[#4A5568] hover:text-[#051C2C] dark:hover:text-white border border-[#E2E6EB] dark:border-slate-700 rounded px-3 py-1.5 bg-white dark:bg-slate-800 transition disabled:opacity-50 shadow-sm"
            title="Refresh list"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-28 rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] animate-pulse p-6"
              />
            ))}
          </div>
        )}

        {/* Error state */}
        {isError && (
          <div className="rounded-lg border border-[#F5C2C2] dark:border-rose-900 bg-[#FDF2F2] dark:bg-rose-950/40 p-6 text-center">
            <p className="text-[#941B1B] dark:text-rose-300 font-semibold mb-2">
              Failed to load projects
            </p>
            <p className="text-xs text-rose-600/80 mb-4">{error?.message}</p>
            <button
              onClick={() => refetch()}
              className="rounded bg-[#941B1B] text-white px-4 py-2 text-xs font-semibold hover:bg-rose-800 transition"
            >
              Try Again
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && projects?.length === 0 && (
          <div className="rounded-lg border border-dashed border-[#D1D7E0] dark:border-slate-700 bg-white/50 dark:bg-slate-900/50 p-12 text-center">
            <div className="mx-auto w-12 h-12 rounded bg-[#E8F1F8] dark:bg-blue-950 flex items-center justify-center text-[#002B49] mb-4">
              <FileSpreadsheet className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-serif font-semibold text-[#051C2C] dark:text-white">
              No active consulting engagements
            </h3>
            <p className="text-xs text-[#718096] mt-1 max-w-sm mx-auto">
              Start by formulating a strategic topic, target executive audience, and research depth.
            </p>
            <Link
              href="/projects/new"
              className="mt-6 inline-flex items-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-5 py-2.5 text-xs font-semibold text-white shadow-sm transition"
            >
              <PlusCircle className="h-4 w-4" />
              Create First Engagement
            </Link>
          </div>
        )}

        {/* Project Cards List */}
        {!isLoading && !isError && projects && projects.length > 0 && (
          <div className="space-y-4">
            {projects.map((project: Project) => {
              const status = statusConfig[project.status] || statusConfig.draft;
              return (
                <div
                  key={project.id}
                  className="group relative rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm hover:shadow-md hover:border-[#002B49] dark:hover:border-slate-600 transition border-l-4 border-l-[#002B49]"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <Link
                      href={`/projects/${project.id}`}
                      className="space-y-2 flex-1 block"
                    >
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-serif font-semibold text-[#051C2C] dark:text-white group-hover:text-[#005A9C] transition">
                          {project.topic}
                        </h3>
                        <span
                          className={`inline-flex items-center gap-1.5 rounded px-2.5 py-0.5 text-[10px] font-semibold border ${status.bg} ${status.text} ${status.border}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                          {status.label}
                        </span>
                      </div>
                      <p className="text-xs text-[#4A5568] dark:text-slate-300 line-clamp-2 leading-relaxed font-sans">
                        {project.objective}
                      </p>
                      <div className="flex flex-wrap gap-3 text-xs text-[#718096] dark:text-slate-400 pt-2">
                        <span className="flex items-center gap-1 border border-[#E2E6EB] dark:border-slate-800 px-2.5 py-1 rounded bg-[#F7F9FB] dark:bg-slate-800/60 text-[11px]">
                          <Users className="h-3 w-3 text-[#002B49]" />
                          {project.audience || "Executive Leadership"}
                        </span>
                        <span className="flex items-center gap-1 border border-[#E2E6EB] dark:border-slate-800 px-2.5 py-1 rounded bg-[#F7F9FB] dark:bg-slate-800/60 text-[11px]">
                          <Globe className="h-3 w-3 text-[#002B49]" />
                          {project.geography || "Global"}
                        </span>
                        <span className="flex items-center gap-1 border border-[#E2E6EB] dark:border-slate-800 px-2.5 py-1 rounded bg-[#F7F9FB] dark:bg-slate-800/60 text-[11px]">
                          <Compass className="h-3 w-3 text-[#002B49]" />
                          {project.time_horizon || "Horizon Open"}
                        </span>
                        <span className="capitalize px-2.5 py-1 rounded border border-[#E2E6EB] dark:border-slate-800 bg-[#F7F9FB] dark:bg-slate-800/60 font-medium text-[11px] text-[#002B49]">
                          {project.research_depth} depth
                        </span>
                      </div>
                    </Link>

                    <div className="flex items-center gap-3 self-end sm:self-center shrink-0">
                      <div className="flex items-center gap-1 text-[11px] text-[#718096] font-mono">
                        <Clock className="h-3 w-3" />
                        {new Date(project.created_at).toLocaleDateString()}
                      </div>

                      {/* Delete button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setProjectToDelete(project);
                        }}
                        className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1.5 rounded text-slate-400 hover:text-[#941B1B] hover:bg-[#FDF2F2] transition"
                        title={`Delete project "${project.topic}"`}
                        aria-label={`Delete project "${project.topic}"`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>

                      <Link
                        href={`/projects/${project.id}`}
                        className="p-1.5 rounded text-slate-400 hover:text-[#002B49] hover:bg-slate-100 group-hover:translate-x-0.5 transition"
                        aria-label="View engagement details"
                      >
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Delete confirmation modal */}
      <DeleteProjectDialog
        isOpen={projectToDelete !== null}
        onClose={() => setProjectToDelete(null)}
        project={projectToDelete}
      />
    </main>
  );
}
