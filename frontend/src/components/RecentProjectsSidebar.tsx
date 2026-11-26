"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Layers,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  PlusCircle,
  Search,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import { listProjects, Project, ProjectStatus } from "@/lib/api";
import { DeleteProjectDialog } from "./DeleteProjectDialog";

const statusDotColors: Record<ProjectStatus, string> = {
  draft: "bg-[#718096]",
  running: "bg-[#005A9C] animate-pulse",
  awaiting_review: "bg-[#8D5B00]",
  revision_requested: "bg-[#8D5B00]",
  approved: "bg-[#0D5E4D]",
  generating: "bg-[#002B49] animate-pulse",
  completed: "bg-[#0D5E4D]",
  failed: "bg-[#941B1B]",
};

const statusLabels: Record<ProjectStatus, string> = {
  draft: "Draft",
  running: "Researching",
  awaiting_review: "Review Gate Ready",
  revision_requested: "Revising",
  approved: "Approved",
  generating: "Generating PPTX",
  completed: "Deck Ready",
  failed: "Needs Attention",
};

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (diffMs < 0) return "Just now";
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

interface RecentProjectsSidebarProps {
  isMobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function RecentProjectsSidebar({
  isMobileOpen = false,
  onMobileClose,
}: RecentProjectsSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);

  // Read collapsed state from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("consulting_sidebar_collapsed");
      if (saved !== null) {
        setIsCollapsed(saved === "true");
      }
    } catch {
      // localStorage may fail in some environments
    }
  }, []);

  const toggleCollapsed = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("consulting_sidebar_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  const {
    data: projects = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const filteredProjects = projects.filter((project) =>
    project.topic.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (project.objective && project.objective.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const handleDeleteSuccess = () => {
    if (projectToDelete && pathname.includes(projectToDelete.id)) {
      router.push("/");
    }
    setProjectToDelete(null);
  };

  return (
    <>
      {/* ── Desktop Sidebar ─────────────────────────────────────────── */}
      <aside
        className={`hidden md:flex flex-col bg-white dark:bg-[#051C2C] border-r border-[#E2E6EB] dark:border-slate-800 transition-all duration-300 ease-in-out shrink-0 select-none z-20 ${
          isCollapsed ? "w-16" : "w-72"
        }`}
        style={{ height: "100vh", position: "sticky", top: 0 }}
        aria-label="Recent Projects Sidebar"
      >
        {/* Top Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#ECEFF2] dark:border-slate-800/80 min-h-[64px]">
          {!isCollapsed && (
            <Link
              href="/"
              className="flex items-center gap-2.5 overflow-hidden text-[#051C2C] dark:text-white group"
            >
              <div className="rounded bg-[#002B49] p-1.5 text-white shadow-sm shrink-0 group-hover:bg-[#051C2C] transition">
                <Layers className="h-5 w-5" />
              </div>
              <div className="truncate">
                <span className="font-serif font-bold text-sm tracking-tight block truncate text-[#051C2C] dark:text-white">
                  AI Consulting
                </span>
                <span className="kicker text-[#005A9C] dark:text-[#60A5FA]">
                  Executive Workspace
                </span>
              </div>
            </Link>
          )}

          {isCollapsed && (
            <Link
              href="/"
              className="mx-auto rounded bg-[#002B49] p-2 text-white shadow-sm hover:bg-[#051C2C] transition"
              title="AI Consulting Home"
            >
              <Layers className="h-5 w-5" />
            </Link>
          )}

          <button
            onClick={toggleCollapsed}
            className={`p-1.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition ${
              isCollapsed ? "hidden" : "block"
            }`}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Collapsed Expand Toggle */}
        {isCollapsed && (
          <div className="p-2 flex justify-center border-b border-[#ECEFF2] dark:border-slate-800">
            <button
              onClick={toggleCollapsed}
              className="p-2 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              title="Expand sidebar"
              aria-label="Expand sidebar"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Action: New Project */}
        <div className="p-3">
          {isCollapsed ? (
            <Link
              href="/projects/new"
              className="w-10 h-10 mx-auto flex items-center justify-center rounded bg-[#002B49] hover:bg-[#051C2C] text-white shadow-sm transition"
              title="Create New Project"
            >
              <PlusCircle className="h-5 w-5" />
            </Link>
          ) : (
            <Link
              href="/projects/new"
              className="w-full flex items-center justify-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-3.5 py-2.5 text-xs font-semibold text-white shadow-sm transition"
            >
              <PlusCircle className="h-4 w-4" />
              <span>New Strategic Engagement</span>
            </Link>
          )}
        </div>

        {/* Recent Projects Section Header & Search */}
        {!isCollapsed && (
          <div className="px-3 pt-2 pb-1 space-y-2">
            <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 px-1">
              <span className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Recent Projects
              </span>
              <span className="text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500">
                {projects.length}
              </span>
            </div>

            {/* Quick search input if more than 3 projects */}
            {projects.length > 3 && (
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter projects..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-lg text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-2 top-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs"
                  >
                    ×
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Scrollable Recent Projects List */}
        <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1 scrollbar-thin">
          {isLoading && (
            <div className="p-3 space-y-2">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="h-10 rounded-lg bg-slate-100 dark:bg-slate-800/60 animate-pulse"
                />
              ))}
            </div>
          )}

          {!isLoading && isError && !isCollapsed && (
            <div className="p-3 text-center text-xs text-rose-500">
              Failed to load recent projects
            </div>
          )}

          {!isLoading && !isError && filteredProjects.length === 0 && (
            <div className="p-4 text-center">
              {!isCollapsed && (
                <p className="text-xs text-slate-400">
                  {searchQuery ? "No matching projects" : "No recent projects"}
                </p>
              )}
            </div>
          )}

          {!isLoading &&
            !isError &&
            filteredProjects.map((project) => {
              const isActive = pathname.startsWith(`/projects/${project.id}`);
              const dotColor = statusDotColors[project.status] || "bg-slate-400";
              const statusLabel = statusLabels[project.status] || project.status;

              if (isCollapsed) {
                return (
                  <div key={project.id} className="relative group/item">
                    <Link
                      href={`/projects/${project.id}`}
                      className={`w-10 h-10 mx-auto flex items-center justify-center rounded transition ${
                        isActive
                          ? "bg-[#E8F1F8] dark:bg-[#002B49] text-[#002B49] dark:text-[#E8F1F8] ring-1 ring-[#005A9C]"
                          : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                      }`}
                      title={`${project.topic} (${statusLabel})`}
                    >
                      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                    </Link>
                  </div>
                );
              }

              return (
                <div
                  key={project.id}
                  className={`group/item relative flex items-center justify-between rounded p-2.5 text-xs transition border ${
                    isActive
                      ? "bg-[#F0F6FC] dark:bg-[#002B49]/50 border-[#B9D7F2] dark:border-[#005A9C]/50 text-[#002B49] dark:text-[#E8F1F8] font-semibold border-l-4 border-l-[#002B49]"
                      : "border-transparent text-[#334155] dark:text-slate-300 hover:bg-[#F7F9FB] dark:hover:bg-slate-800/60 hover:text-[#051C2C] dark:hover:text-white"
                  }`}
                >
                  <Link
                    href={`/projects/${project.id}`}
                    className="flex-1 min-w-0 pr-2 flex flex-col gap-1"
                    title={project.topic}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`}
                        title={`Status: ${statusLabel}`}
                      />
                      <span className="truncate font-medium leading-tight">
                        {project.topic}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[#718096] dark:text-slate-400 pl-3.5">
                      <span className="truncate max-w-[110px]">{statusLabel}</span>
                      <span className="font-mono text-[10px]">{formatRelativeTime(project.created_at)}</span>
                    </div>
                  </Link>

                  {/* Delete button: accessible on hover/focus */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setProjectToDelete(project);
                    }}
                    className="opacity-0 group-hover/item:opacity-100 focus:opacity-100 p-1.5 rounded text-slate-400 hover:text-[#941B1B] hover:bg-[#FDF2F2] transition shrink-0"
                    title={`Delete project "${project.topic}"`}
                    aria-label={`Delete project "${project.topic}"`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
        </div>

        {/* Bottom Nav Links */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800/80 space-y-1">
          {isCollapsed ? (
            <>
              <Link
                href="/"
                className="w-10 h-10 mx-auto flex items-center justify-center rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition"
                title="Dashboard"
              >
                <LayoutDashboard className="h-4 w-4" />
              </Link>
              <Link
                href="/settings/webhooks"
                className="w-10 h-10 mx-auto flex items-center justify-center rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition"
                title="Webhook Settings"
              >
                <Settings className="h-4 w-4" />
              </Link>
            </>
          ) : (
            <>
              <Link
                href="/"
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                  pathname === "/"
                    ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-semibold"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <LayoutDashboard className="h-4 w-4 text-slate-500" />
                <span>Dashboard</span>
              </Link>

              <Link
                href="/settings/webhooks"
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                  pathname.startsWith("/settings/webhooks")
                    ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-semibold"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Settings className="h-4 w-4 text-slate-500" />
                <span>Webhook Notifications</span>
              </Link>
            </>
          )}
        </div>
      </aside>

      {/* ── Mobile Drawer (Slide-Over) ──────────────────────────────── */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true">
          {/* Backdrop overlay */}
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity"
            onClick={onMobileClose}
            aria-hidden="true"
          />

          {/* Drawer content */}
          <div className="relative flex flex-col w-4/5 max-w-xs bg-white dark:bg-slate-900 h-full shadow-2xl z-10 border-r border-slate-200 dark:border-slate-800 animate-in slide-in-from-left duration-200">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-[#E2E6EB] dark:border-slate-800">
              <Link
                href="/"
                onClick={onMobileClose}
                className="flex items-center gap-2 text-[#051C2C] dark:text-white"
              >
                <div className="rounded bg-[#002B49] p-1.5 text-white shadow-sm">
                  <Layers className="h-5 w-5" />
                </div>
                <span className="font-serif font-bold text-sm tracking-tight">AI Consulting</span>
              </Link>
              <button
                onClick={onMobileClose}
                className="p-1.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                aria-label="Close menu"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Action */}
            <div className="p-3">
              <Link
                href="/projects/new"
                onClick={onMobileClose}
                className="w-full flex items-center justify-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-3.5 py-2.5 text-xs font-semibold text-white shadow-sm transition"
              >
                <PlusCircle className="h-4 w-4" />
                <span>New Strategic Engagement</span>
              </Link>
            </div>

            {/* Title & Filter */}
            <div className="px-3 pt-2 pb-1 space-y-2">
              <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 px-1">
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" />
                  Recent Projects
                </span>
                <span className="text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500">
                  {projects.length}
                </span>
              </div>

              {projects.length > 3 && (
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Filter projects..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-lg text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              )}
            </div>

            {/* Projects list */}
            <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1">
              {filteredProjects.map((project) => {
                const isActive = pathname.startsWith(`/projects/${project.id}`);
                const dotColor = statusDotColors[project.status] || "bg-slate-400";
                const statusLabel = statusLabels[project.status] || project.status;

                return (
                  <div
                    key={project.id}
                    className={`flex items-center justify-between rounded-xl p-2.5 text-xs transition border ${
                      isActive
                        ? "bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-900/60 text-blue-900 dark:text-blue-100 font-medium"
                        : "border-transparent text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                    }`}
                  >
                    <Link
                      href={`/projects/${project.id}`}
                      onClick={onMobileClose}
                      className="flex-1 min-w-0 pr-2 flex flex-col gap-1"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
                        <span className="truncate font-semibold">{project.topic}</span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-400 pl-3.5">
                        <span>{statusLabel}</span>
                        <span>{formatRelativeTime(project.created_at)}</span>
                      </div>
                    </Link>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setProjectToDelete(project);
                      }}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 transition shrink-0"
                      title="Delete project"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Bottom Nav */}
            <div className="p-3 border-t border-slate-200 dark:border-slate-800 space-y-1">
              <Link
                href="/"
                onClick={onMobileClose}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              >
                <LayoutDashboard className="h-4 w-4 text-slate-500" />
                <span>Dashboard</span>
              </Link>
              <Link
                href="/settings/webhooks"
                onClick={onMobileClose}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              >
                <Settings className="h-4 w-4 text-slate-500" />
                <span>Webhook Notifications</span>
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <DeleteProjectDialog
        isOpen={projectToDelete !== null}
        onClose={() => setProjectToDelete(null)}
        project={projectToDelete}
        onSuccess={handleDeleteSuccess}
      />
    </>
  );
}

export default RecentProjectsSidebar;
