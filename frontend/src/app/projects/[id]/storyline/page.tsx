"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUp,
  ArrowDown,
  Download,
  Save,
  RefreshCw,
  CheckCircle2,
  Layers,
  AlertCircle,
  Eye,
} from "lucide-react";

import {
  getProject,
  getProjectStoryline,
  updateProjectStoryline,
  regenerateProjectStoryline,
  SlideItem,
  SlideLayout,
} from "@/lib/api";
import { ExportModal } from "@/components/ExportModal";

const LAYOUT_OPTIONS: { value: SlideLayout; label: string; description: string }[] = [
  { value: "title", label: "Hero Title", description: "Executive cover slide with dark styling and metadata" },
  { value: "executive_summary", label: "Executive Summary", description: "Top takeaway banner with 3 pillar cards" },
  { value: "two_column", label: "Two Column", description: "Side-by-side strategic analysis and bulleted cards" },
  { value: "three_insight", label: "Three Insight", description: "Three numbered cards for empirical findings/recs" },
  { value: "comparison", label: "Comparison Table", description: "Tabular evaluation of status quo vs. proposed solution" },
  { value: "roadmap", label: "Roadmap", description: "Three phased timeline milestones across execution horizons" },
  { value: "risk_matrix", label: "Risk Matrix", description: "Severity badges, risk descriptions, and mitigations" },
  { value: "closing", label: "Closing Action Plan", description: "Decision gates, immediate next steps, and contacts" },
  { value: "scorecard" as any, label: "Evaluation Scorecard", description: "5-column strategic evaluation table with status badges" },
  { value: "metrics" as any, label: "KPI Metric Cards", description: "4 KPI cards with 32pt big numbers and delta badges" },
];

export default function StorylinePage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const projectId = params?.id as string;

  const [slides, setSlides] = useState<SlideItem[]>([]);
  const [selectedSlideIndex, setSelectedSlideIndex] = useState<number>(0);
  const [announcement, setAnnouncement] = useState<string>("");
  const [isSaved, setIsSaved] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);

  // 1. Fetch project info
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    enabled: !!projectId,
  });

  // 2. Fetch storyline outline
  const {
    data: outline,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["storyline", projectId],
    queryFn: () => getProjectStoryline(projectId),
    enabled: !!projectId,
    retry: false,
  });

  // Synchronize state when outline is loaded
  useEffect(() => {
    if (outline?.slides) {
      setSlides(outline.slides);
    }
  }, [outline]);

  // 3. Update mutation
  const updateMutation = useMutation({
    mutationFn: (payload: { slides: SlideItem[]; approve_all?: boolean }) =>
      updateProjectStoryline(projectId, payload),
    onSuccess: (data) => {
      setSlides(data.slides);
      setIsSaved(true);
      setErrorMessage(null);
      setTimeout(() => setIsSaved(false), 3000);
      queryClient.invalidateQueries({ queryKey: ["storyline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (err: any) => {
      setErrorMessage(err.message || "Failed to save storyline updates.");
    },
  });

  // 4. Force regenerate mutation
  const regenerateMutation = useMutation({
    mutationFn: () => regenerateProjectStoryline(projectId),
    onSuccess: (data) => {
      setSlides(data.slides);
      setSelectedSlideIndex(0);
      setAnnouncement("Storyline regenerated from approved synthesis.");
      queryClient.invalidateQueries({ queryKey: ["storyline", projectId] });
    },
    onError: (err: any) => {
      setErrorMessage(err.message || "Failed to regenerate storyline.");
    },
  });

  // Reorder Slide Handler (Move Up / Move Down)
  const moveSlide = (currentIndex: number, targetIndex: number) => {
    if (targetIndex < 0 || targetIndex >= slides.length) return;

    const newSlides = [...slides];
    const [moved] = newSlides.splice(currentIndex, 1);
    newSlides.splice(targetIndex, 0, moved);

    // Re-index contiguous 1..N slide_order
    const reordered = newSlides.map((s, idx) => ({
      ...s,
      slide_order: idx + 1,
    }));

    setSlides(reordered);
    setSelectedSlideIndex(targetIndex);

    // Announce to screen readers per modern-web-guidance
    setAnnouncement(`Moved slide "${moved.title}" to position ${targetIndex + 1} of ${reordered.length}`);
  };

  // Edit slide property
  const handleSlideChange = (
    index: number,
    field: keyof SlideItem,
    value: any
  ) => {
    const updated = [...slides];
    updated[index] = {
      ...updated[index],
      [field]: value,
    };
    setSlides(updated);
  };

  // Handle Save
  const handleSave = (approveAll: boolean = false) => {
    updateMutation.mutate({
      slides,
      approve_all: approveAll,
    });
  };

  // Trigger Export Modal
  const handleDownload = () => {
    setIsExportModalOpen(true);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#F7F9FB] flex flex-col items-center justify-center p-6">
        <div className="w-10 h-10 border-3 border-[#002B49] border-t-transparent rounded-full animate-spin mb-4" />
        <h2 className="text-base font-serif font-bold text-[#051C2C]">Loading Slide Storyline...</h2>
        <p className="text-slate-500 text-xs mt-1">Generating 11-slide consulting outline from approved synthesis</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen bg-[#F7F9FB] p-8 flex items-center justify-center">
        <div className="max-w-lg bg-white rounded-lg shadow-sm border border-[#F8C4C4] p-8 text-center">
          <div className="w-12 h-12 bg-[#FDEDED] text-[#941B1B] rounded-full flex items-center justify-center mx-auto mb-4 border border-[#F8C4C4]">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-serif font-bold text-[#051C2C] mb-2">Storyline Not Ready</h2>
          <p className="text-slate-600 text-xs mb-6 leading-relaxed">
            {(error as any)?.message ||
              "Cannot generate slide storyline before research synthesis has been approved by human reviewer."}
          </p>
          <div className="flex gap-3 justify-center">
            <Link
              href={`/projects/${projectId}/review`}
              className="px-4 py-2 bg-[#002B49] text-white rounded-md text-xs font-semibold hover:bg-[#051C2C] transition"
            >
              Go to Human Review
            </Link>
            <Link
              href={`/projects/${projectId}`}
              className="px-4 py-2 bg-white text-slate-700 border border-[#E2E6EB] rounded-md text-xs font-semibold hover:bg-slate-50 transition"
            >
              Back to Tracker
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const activeSlide = slides[selectedSlideIndex] || slides[0];

  return (
    <div className="min-h-screen bg-[#F7F9FB] pb-28 text-slate-900">
      {/* Screen reader live announcement region */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {/* Top Header */}
      <header className="bg-[#051C2C] text-white border-b border-[#002B49] sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link
              href={`/projects/${projectId}`}
              className="p-2 rounded-md bg-[#002B49] hover:bg-[#003B66] text-slate-300 transition"
              title="Back to project tracker"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[#002B49] text-blue-200 border border-blue-400/30 uppercase tracking-wider">
                  Track A: Storyline Studio
                </span>
                <span className="text-xs text-slate-400">
                  {slides.length} Slides Configured
                </span>
              </div>
              <h1 className="text-lg font-serif font-bold text-white tracking-tight truncate max-w-xl mt-0.5">
                {project?.topic || "Slide Storyline Editor"}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => regenerateMutation.mutate()}
              disabled={regenerateMutation.isPending}
              className="px-3.5 py-1.5 bg-[#002B49] hover:bg-[#003B66] text-slate-200 text-xs font-medium rounded-md flex items-center gap-2 transition border border-[#003B66]"
              title="Reset and regenerate default 11 slides"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${regenerateMutation.isPending ? "animate-spin" : ""}`} />
              Regenerate
            </button>
            <button
              onClick={() => handleSave(false)}
              disabled={updateMutation.isPending}
              className="px-3.5 py-1.5 bg-transparent border border-white/20 hover:bg-white/10 text-white text-xs font-medium rounded-md flex items-center gap-2 transition"
            >
              <Save className="w-3.5 h-3.5" />
              {updateMutation.isPending ? "Saving..." : "Save Draft"}
            </button>
            <button
              onClick={handleDownload}
              className="px-4 py-1.5 bg-[#005A9C] hover:bg-[#004A80] text-white text-xs font-semibold rounded-md shadow-sm flex items-center gap-2 transition"
            >
              <Download className="w-3.5 h-3.5" />
              Export Deck &amp; Summary
            </button>
          </div>
        </div>
      </header>

      {/* Main Workspace Layout: Left Sidebar List + Center/Right Slide Preview & Editor */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {errorMessage && (
          <div className="mb-6 p-4 bg-[#FDEDED] border border-[#F8C4C4] text-[#941B1B] rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-medium">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {errorMessage}
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-xs font-semibold underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {isSaved && (
          <div className="mb-6 p-4 bg-[#EBF7F2] border border-[#BCE3D2] text-[#0D5E4D] rounded-lg flex items-center gap-2 text-xs font-medium">
            <CheckCircle2 className="w-4 h-4 text-[#0D5E4D]" />
            Storyline changes saved successfully to database!
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Visual Slide Outline Navigator */}
          <div className="lg:col-span-5 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E6EB]">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-2">
                <Layers className="w-3.5 h-3.5 text-[#002B49]" />
                Deck Storyline Sequence
              </h2>
              <span className="text-[11px] font-medium text-slate-500">
                16:9 Widescreen Layout
              </span>
            </div>

            <div className="space-y-2.5 max-h-[calc(100vh-250px)] overflow-y-auto pr-1">
              {slides.map((slide, index) => {
                const isSelected = index === selectedSlideIndex;
                return (
                  <div
                    key={slide.id || index}
                    onClick={() => setSelectedSlideIndex(index)}
                    className={`group relative p-3.5 rounded-lg border transition-all cursor-pointer ${
                      isSelected
                        ? "bg-white border-l-4 border-l-[#002B49] border-[#E2E6EB] shadow-sm"
                        : "bg-white hover:bg-slate-50/80 border-[#E2E6EB]"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Slide Order Badge */}
                      <div
                        className={`w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold shrink-0 ${
                          isSelected
                            ? "bg-[#002B49] text-white"
                            : "bg-[#F7F9FB] border border-[#E2E6EB] text-slate-700 group-hover:bg-slate-100"
                        }`}
                      >
                        {String(slide.slide_order).padStart(2, "0")}
                      </div>

                      {/* Slide Summary */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-[#F7F9FB] text-slate-700 border border-[#E2E6EB]">
                            {slide.layout.replace("_", " ")}
                          </span>
                          {slide.source_ids?.length > 0 && (
                            <span className="text-[10px] font-medium text-slate-500 bg-white px-1.5 py-0.5 rounded border border-[#E2E6EB]">
                              {slide.source_ids.length} Sources
                            </span>
                          )}
                        </div>
                        <h3 className="text-xs font-serif font-bold text-[#051C2C] truncate">
                          {slide.title}
                        </h3>
                        <p className="text-[11px] text-slate-500 truncate mt-0.5">
                          {slide.key_message}
                        </p>
                      </div>

                      {/* Accessible Reorder Controls */}
                      <div
                        className="flex flex-col gap-1 shrink-0 ml-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          onClick={() => moveSlide(index, index - 1)}
                          disabled={index === 0}
                          aria-label={`Move Slide ${slide.slide_order} up`}
                          className="p-1 rounded bg-[#F7F9FB] border border-[#E2E6EB] hover:bg-slate-100 text-slate-600 disabled:opacity-30 disabled:pointer-events-none transition"
                        >
                          <ArrowUp className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveSlide(index, index + 1)}
                          disabled={index === slides.length - 1}
                          aria-label={`Move Slide ${slide.slide_order} down`}
                          className="p-1 rounded bg-[#F7F9FB] border border-[#E2E6EB] hover:bg-slate-100 text-slate-600 disabled:opacity-30 disabled:pointer-events-none transition"
                        >
                          <ArrowDown className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Slide Editor & Live Visual Consulting Card Preview */}
          <div className="lg:col-span-7 space-y-6">
            {activeSlide ? (
              <div className="bg-white rounded-lg border border-[#E2E6EB] shadow-sm p-6 space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-[#E2E6EB]">
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-md bg-[#002B49] text-white font-bold flex items-center justify-center text-xs">
                      {String(activeSlide.slide_order).padStart(2, "0")}
                    </span>
                    <div>
                      <h2 className="text-base font-serif font-bold text-[#051C2C]">
                        Slide Editor: Slide {activeSlide.slide_order}
                      </h2>
                      <p className="text-[11px] text-slate-500">
                        Edit action title, governing takeaway, and executive layout template
                      </p>
                    </div>
                  </div>

                  <span className="text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 bg-[#F7F9FB] text-slate-700 rounded border border-[#E2E6EB]">
                    Layout: {activeSlide.layout}
                  </span>
                </div>

                {/* Form Inputs */}
                <div className="space-y-4">
                  {/* Action Title */}
                  <div>
                    <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                      Action Title / Governing Thought
                    </label>
                    <input
                      type="text"
                      value={activeSlide.title}
                      onChange={(e) =>
                        handleSlideChange(selectedSlideIndex, "title", e.target.value)
                      }
                      className="w-full px-3.5 py-2 bg-[#F7F9FB] border border-[#E2E6EB] rounded-md text-slate-900 font-semibold focus:outline-none focus:ring-1 focus:ring-[#002B49] focus:bg-white transition text-xs"
                      placeholder="Enter executive action title..."
                    />
                  </div>

                  {/* Key Message Subtitle */}
                  <div>
                    <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                      Executive Key Message (Header Subtitle)
                    </label>
                    <textarea
                      rows={2}
                      value={activeSlide.key_message}
                      onChange={(e) =>
                        handleSlideChange(
                          selectedSlideIndex,
                          "key_message",
                          e.target.value
                        )
                      }
                      className="w-full px-3.5 py-2 bg-[#F7F9FB] border border-[#E2E6EB] rounded-md text-slate-800 text-xs focus:outline-none focus:ring-1 focus:ring-[#002B49] focus:bg-white transition resize-none"
                      placeholder="One-sentence executive takeaway..."
                    />
                  </div>

                  {/* Layout Selector */}
                  <div>
                    <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                      Consulting Slide Layout
                    </label>
                    <select
                      value={activeSlide.layout}
                      onChange={(e) =>
                        handleSlideChange(
                          selectedSlideIndex,
                          "layout",
                          e.target.value as SlideLayout
                        )
                      }
                      className="w-full px-3.5 py-2 bg-[#F7F9FB] border border-[#E2E6EB] rounded-md text-slate-800 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-[#002B49] focus:bg-white transition"
                    >
                      {LAYOUT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label} — {opt.description}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* 16:9 Widescreen Visual Slide Mockup Preview */}
                <div className="pt-4 border-t border-[#E2E6EB]">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                      <Eye className="w-3.5 h-3.5 text-slate-500" />
                      Live PowerPoint 16:9 Visual Preview
                    </h3>
                    <span className="text-[10px] text-slate-400 font-mono">
                      1920 × 1080 Aspect Ratio
                    </span>
                  </div>

                  <div
                    className={`relative w-full aspect-[16/9] rounded-lg overflow-hidden border p-6 flex flex-col justify-between ${
                      activeSlide.layout === "title"
                        ? "bg-[#051C2C] text-white border-[#002B49]"
                        : "bg-white text-slate-900 border-[#E2E6EB] border-t-4 border-t-[#002B49]"
                    }`}
                  >
                    {/* Slide Header */}
                    <div>
                      {activeSlide.layout === "title" ? (
                        <div className="h-full flex flex-col justify-center pt-8">
                          <div className="w-8 h-1 bg-[#005A9C] mb-4 rounded" />
                          <h1 className="text-xl font-serif font-bold tracking-tight text-white line-clamp-2">
                            {activeSlide.title}
                          </h1>
                          <p className="text-xs text-slate-300 mt-2 line-clamp-2">
                            {activeSlide.key_message}
                          </p>
                        </div>
                      ) : (
                        <div>
                          <h2 className="text-base font-serif font-bold text-[#051C2C] tracking-tight leading-snug">
                            {activeSlide.title}
                          </h2>
                          <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-1">
                            {activeSlide.key_message}
                          </p>
                          <div className="w-full h-px bg-[#E2E6EB] my-3" />
                        </div>
                      )}

                      {/* Middle Layout Preview Badges */}
                      {activeSlide.layout !== "title" && (
                        <div className="grid grid-cols-3 gap-3 my-2">
                          <div className="bg-[#F7F9FB] border border-[#E2E6EB] rounded-md p-3">
                            <span className="text-[10px] font-bold text-[#002B49] uppercase tracking-wider">
                              Section 01
                            </span>
                            <div className="h-2 w-3/4 bg-slate-200 rounded mt-1.5" />
                            <div className="h-2 w-1/2 bg-slate-200 rounded mt-1" />
                          </div>
                          <div className="bg-[#F7F9FB] border border-[#E2E6EB] rounded-md p-3">
                            <span className="text-[10px] font-bold text-[#002B49] uppercase tracking-wider">
                              Section 02
                            </span>
                            <div className="h-2 w-3/4 bg-slate-200 rounded mt-1.5" />
                            <div className="h-2 w-1/2 bg-slate-200 rounded mt-1" />
                          </div>
                          <div className="bg-[#F7F9FB] border border-[#E2E6EB] rounded-md p-3">
                            <span className="text-[10px] font-bold text-[#002B49] uppercase tracking-wider">
                              Section 03
                            </span>
                            <div className="h-2 w-3/4 bg-slate-200 rounded mt-1.5" />
                            <div className="h-2 w-1/2 bg-slate-200 rounded mt-1" />
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Footer Citations */}
                    <div className="text-[10px] text-slate-400 flex items-center justify-between pt-2 border-t border-[#E2E6EB]">
                      <span>
                        {activeSlide.source_ids?.length > 0
                          ? `Sources: ${activeSlide.source_ids.slice(0, 3).join(", ")}`
                          : "Internal Analysis"}
                      </span>
                      <span className="font-mono">Slide {activeSlide.slide_order}</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </main>

      {/* Sticky Bottom Action Bar */}
      <div className="fixed bottom-0 inset-x-0 bg-white/95 backdrop-blur-md border-t border-[#E2E6EB] py-3 px-6 z-40 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-semibold px-2.5 py-0.5 bg-[#EBF7F2] text-[#0D5E4D] border border-[#BCE3D2] rounded uppercase tracking-wider">
              Storyline Validated
            </span>
            <span className="text-xs text-slate-600">
              {slides.length} slides ready for presentation export
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleSave(true)}
              disabled={updateMutation.isPending}
              className="px-4 py-2 bg-[#0D5E4D] hover:bg-[#0A473A] text-white text-xs font-bold rounded-md shadow-sm flex items-center gap-2 transition"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Approve All &amp; Finalize
            </button>
            <button
              onClick={handleDownload}
              className="px-5 py-2 bg-[#002B49] hover:bg-[#051C2C] text-white text-xs font-bold rounded-md shadow-sm flex items-center gap-2 transition"
            >
              <Download className="w-3.5 h-3.5" />
              Export Deck &amp; Summary
            </button>
          </div>
        </div>
      </div>

      {/* Export Deliverables Modal */}
      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        projectId={projectId}
        projectTopic={project?.topic}
      />
    </div>
  );
}