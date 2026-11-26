"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Briefcase,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Compass,
  FileText,
  FileUp,
  Loader2,
  Paperclip,
  Sparkles,
  Trash2,
  UploadCloud,
  Users,
} from "lucide-react";
import { createProject, uploadProjectDocuments, ProjectBrief, ResearchDepth } from "@/lib/api";

const depths: {
  id: ResearchDepth;
  name: string;
  sources: string;
  desc: string;
  badge: string;
}[] = [
  {
    id: "quick",
    name: "Quick Pulse",
    sources: "~5-8 sources",
    desc: "Rapid exploration for initial scoping, orientation, or high-level sanity checks.",
    badge: "1-2 mins",
  },
  {
    id: "standard",
    name: "Standard Engagement",
    sources: "~12-18 sources",
    desc: "Balanced consulting depth with multi-angle cross-verification and structured evidence.",
    badge: "Recommended",
  },
  {
    id: "deep",
    name: "Deep Diligence",
    sources: "~25-35 sources",
    desc: "Exhaustive research with strict contradiction discovery, risk analysis, and gap coverage.",
    badge: "Most Thorough",
  },
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function NewProjectPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState<ProjectBrief>({
    topic: "",
    objective: "",
    audience: "",
    time_horizon: "",
    additional_context: "",
    research_depth: "standard",
  });

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatusText, setSubmitStatusText] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof ProjectBrief, string>>>({});

  const validate = (): boolean => {
    const errors: Partial<Record<keyof ProjectBrief, string>> = {};
    if (!formData.topic.trim() || formData.topic.trim().length < 3) {
      errors.topic = "Topic must be at least 3 characters long.";
    }
    if (!formData.objective.trim() || formData.objective.trim().length < 10) {
      errors.objective = "Objective must be at least 10 characters long.";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleFilesAdded = (files: FileList | File[]) => {
    setFileError(null);
    const allowedExtensions = [".pdf", ".txt"];
    const maxFiles = 3;
    const maxBytes = 10 * 1024 * 1024; // 10 MB

    const currentCount = selectedFiles.length;
    const incoming = Array.from(files);

    if (currentCount + incoming.length > maxFiles) {
      setFileError(`You can attach a maximum of ${maxFiles} documents in total.`);
      return;
    }

    const newFiles: File[] = [];
    for (const file of incoming) {
      const lower = file.name.toLowerCase();
      const isValidExt = allowedExtensions.some((ext) => lower.endsWith(ext));
      if (!isValidExt) {
        setFileError(`Unsupported format for '${file.name}'. Only .pdf and .txt are allowed.`);
        return;
      }
      if (file.size > maxBytes) {
        setFileError(`'${file.name}' exceeds the 10 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);
        return;
      }
      if (selectedFiles.some((f) => f.name === file.name)) {
        continue;
      }
      newFiles.push(file);
    }

    if (newFiles.length > 0) {
      setSelectedFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    setSubmitStatusText("Initializing project brief...");

    try {
      const project = await createProject(formData);

      if (selectedFiles.length > 0) {
        setSubmitStatusText(`Ingesting & extracting ${selectedFiles.length} research document(s)...`);
        await uploadProjectDocuments(project.id, selectedFiles);
      }

      setSubmitStatusText("Finalizing project space...");
      router.push(`/projects/${project.id}`);
    } catch (err: any) {
      setIsSubmitting(false);
      setSubmitStatusText(null);
      setFormErrors({ topic: err.message || "Failed to create project." });
    }
  };

  const loadExample = () => {
    setFormData({
      topic: "Generative AI in Retail Banking & Wealth Management",
      objective:
        "Evaluate high-impact commercial use cases, operational cost reduction potential, and regulatory/compliance risks for tier-1 institutions over the next 3 years.",
      audience: "Chief Strategy Officer, Head of Retail Banking, Head of Digital Transformation",
      time_horizon: "2025-2028 (3-year horizon)",
      additional_context:
        "Focus on fraud mitigation, customer service automation, and agentic wealth advisory. Benchmark tier-1 banks in North America.",
      research_depth: "standard",
    });
    setFormErrors({});
    setFileError(null);
  };

  return (
    <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] pb-20 font-sans">
      {/* ── Top Header ────────────────────────────────────────────── */}
      <header className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#051C2C]/95 backdrop-blur sticky top-0 z-10 px-6 py-4">
        <div className="mx-auto max-w-4xl flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-semibold text-[#4A5568] dark:text-slate-300 hover:text-[#051C2C] dark:hover:text-white transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Engagements
          </Link>
          <button
            type="button"
            onClick={loadExample}
            className="inline-flex items-center gap-1.5 text-xs text-[#005A9C] dark:text-[#60A5FA] font-semibold border border-[#B9D7F2] dark:border-slate-700 bg-[#F0F6FC] dark:bg-slate-800 rounded px-3 py-1.5 hover:bg-[#E8F1F8] transition"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Load Banking Case Example
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 pt-10">
        <div className="mb-8">
          <span className="kicker text-[#005A9C] dark:text-[#60A5FA] block mb-1">
            Engagement Scoping • Intake Gate
          </span>
          <h1 className="text-3xl font-serif font-semibold text-[#051C2C] dark:text-white tracking-tight">
            New Strategic Engagement Brief
          </h1>
          <p className="text-[#4A5568] text-xs mt-1 leading-relaxed">
            Define your inquiry parameters. Autonomous research agents build an evidence-traceable
            dossier grounded strictly in retrieved institutional sources and uploaded documents.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Card: Topic & Objective */}
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm space-y-6 border-l-4 border-l-[#002B49]">
            <div>
              <label
                htmlFor="topic"
                className="block text-xs font-semibold text-[#051C2C] dark:text-slate-100 mb-1"
              >
                Central Research Question or Topic <span className="text-[#941B1B]">*</span>
              </label>
              <input
                id="topic"
                type="text"
                value={formData.topic}
                onChange={(e) =>
                  setFormData({ ...formData, topic: e.target.value })
                }
                placeholder="e.g. Commercial Viability of Small Modular Nuclear Reactors (SMRs)"
                className="w-full rounded border border-[#D1D7E0] dark:border-slate-700 bg-white dark:bg-slate-800/60 px-3.5 py-2 text-sm text-[#121820] dark:text-white placeholder-[#718096] focus:border-[#002B49] focus:outline-none focus:ring-1 focus:ring-[#002B49]"
              />
              {formErrors.topic && (
                <p className="mt-1.5 text-xs text-[#941B1B]">{formErrors.topic}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="objective"
                className="block text-xs font-semibold text-[#051C2C] dark:text-slate-100 mb-1"
              >
                Strategic Objective &amp; Decision Deliverable <span className="text-[#941B1B]">*</span>
              </label>
              <textarea
                id="objective"
                rows={3}
                value={formData.objective}
                onChange={(e) =>
                  setFormData({ ...formData, objective: e.target.value })
                }
                placeholder="What strategic question or decision should this deliverable resolve for executive leadership?"
                className="w-full rounded border border-[#D1D7E0] dark:border-slate-700 bg-white dark:bg-slate-800/60 px-3.5 py-2 text-sm text-[#121820] dark:text-white placeholder-[#718096] focus:border-[#002B49] focus:outline-none focus:ring-1 focus:ring-[#002B49]"
              />
              {formErrors.objective && (
                <p className="mt-1.5 text-xs text-[#941B1B]">
                  {formErrors.objective}
                </p>
              )}
            </div>
          </div>

          {/* Card: Contextual Parameters & Boundaries */}
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm space-y-6 border-l-4 border-l-[#002B49]">
            <h3 className="text-sm font-serif font-semibold text-[#051C2C] dark:text-white flex items-center gap-2">
              <Briefcase className="h-4 w-4 text-[#002B49]" />
              Executive Audience &amp; Scoping Boundaries
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <label
                  htmlFor="audience"
                  className="block text-xs font-semibold text-[#4A5568] dark:text-slate-300 mb-1 flex items-center gap-1.5"
                >
                  <Users className="h-3.5 w-3.5 text-[#002B49]" />
                  Target Audience
                </label>
                <input
                  id="audience"
                  type="text"
                  value={formData.audience || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, audience: e.target.value })
                  }
                  placeholder="e.g. Chief Strategy Officer, Board of Directors"
                  className="w-full rounded border border-[#D1D7E0] dark:border-slate-700 bg-white dark:bg-slate-800/60 px-3.5 py-2 text-sm text-[#121820] dark:text-white placeholder-[#718096] focus:border-[#002B49] focus:outline-none focus:ring-1 focus:ring-[#002B49]"
                />
              </div>

              <div>
                <label
                  htmlFor="time_horizon"
                  className="block text-xs font-semibold text-[#4A5568] dark:text-slate-300 mb-1 flex items-center gap-1.5"
                >
                  <Calendar className="h-3.5 w-3.5 text-[#002B49]" />
                  Strategic Time Horizon
                </label>
                <input
                  id="time_horizon"
                  type="text"
                  value={formData.time_horizon || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, time_horizon: e.target.value })
                  }
                  placeholder="e.g. 2025-2030, Next 18-24 months"
                  className="w-full rounded border border-[#D1D7E0] dark:border-slate-700 bg-white dark:bg-slate-800/60 px-3.5 py-2 text-sm text-[#121820] dark:text-white placeholder-[#718096] focus:border-[#002B49] focus:outline-none focus:ring-1 focus:ring-[#002B49]"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label
                  htmlFor="additional_context"
                  className="block text-xs font-semibold text-[#4A5568] dark:text-slate-300 flex items-center gap-1.5"
                >
                  <FileText className="h-3.5 w-3.5 text-[#002B49]" />
                  Additional Strategic Context &amp; Hypotheses (Optional)
                </label>
                <span className="text-[11px] text-[#718096] font-mono">
                  {(formData.additional_context || "").length}/300
                </span>
              </div>
              <textarea
                id="additional_context"
                rows={2}
                maxLength={300}
                value={formData.additional_context || ""}
                onChange={(e) =>
                  setFormData({ ...formData, additional_context: e.target.value.slice(0, 300) })
                }
                placeholder="Concise scoping note, specific hypotheses, key focal points, or constraints..."
                className="w-full rounded border border-[#D1D7E0] dark:border-slate-700 bg-white dark:bg-slate-800/60 px-3.5 py-2 text-sm text-[#121820] dark:text-white placeholder-[#718096] focus:border-[#002B49] focus:outline-none focus:ring-1 focus:ring-[#002B49]"
              />
              <p className="mt-1 text-[11px] text-[#718096]">
                Injected into research decomposition to steer analytical focus and source priorities.
              </p>
            </div>
          </div>

          {/* Card: Document Upload */}
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm space-y-4 border-l-4 border-l-[#002B49]">
            <div>
              <h3 className="text-sm font-serif font-semibold text-[#051C2C] dark:text-white flex items-center gap-2">
                <Paperclip className="h-4 w-4 text-[#002B49]" />
                Proprietary Internal Knowledge Documents (Optional)
              </h3>
              <p className="text-xs text-[#718096] mt-0.5">
                Attach proprietary client PDF or TXT documents (up to 3 files, max 10 MB each). These serve as ground-truth evidence for the research agent.
              </p>
            </div>

            {fileError && (
              <div className="flex items-center gap-2 rounded border border-[#F5C2C2] bg-[#FDF2F2] p-3 text-xs text-[#941B1B] font-medium">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{fileError}</span>
              </div>
            )}

            {/* Dropzone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragOver(true);
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragOver(false);
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                  handleFilesAdded(e.dataTransfer.files);
                }
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                isDragOver
                  ? "border-[#002B49] bg-[#F0F6FC] dark:bg-blue-950/40"
                  : "border-[#D1D7E0] dark:border-slate-700 hover:border-[#002B49] bg-[#F7F9FB] dark:bg-slate-800/30"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files.length > 0) {
                    handleFilesAdded(e.target.files);
                  }
                }}
              />
              <UploadCloud className="h-8 w-8 text-blue-500 mx-auto mb-2" />
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Click to browse or drag and drop documents here
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Supported formats: PDF (.pdf), Plain Text (.txt) • Max 3 files, 10 MB each
              </p>
            </div>

            {/* Selected Files List */}
            {selectedFiles.length > 0 && (
              <div className="space-y-2 pt-2">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  Attached Documents ({selectedFiles.length})
                </span>
                <div className="divide-y divide-slate-100 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40">
                  {selectedFiles.map((file, idx) => (
                    <div
                      key={`${file.name}-${idx}`}
                      className="flex items-center justify-between px-4 py-2.5 text-xs"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <FileUp className="h-4 w-4 text-blue-600 flex-shrink-0" />
                        <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                          {file.name}
                        </span>
                        <span className="text-slate-400 flex-shrink-0">
                          ({formatFileSize(file.size)})
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(idx);
                        }}
                        className="text-slate-400 hover:text-rose-500 p-1 rounded transition"
                        title="Remove file"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Card: Research Depth */}
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm space-y-4 border-l-4 border-l-[#002B49]">
            <div>
              <h3 className="text-sm font-serif font-semibold text-[#051C2C] dark:text-white flex items-center gap-2">
                <Compass className="h-4 w-4 text-[#002B49]" />
                Evidence Depth &amp; Source Budget
              </h3>
              <p className="text-xs text-[#718096] mt-0.5">
                Controls the breadth of target search vectors and extraction rigor.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {depths.map((d) => {
                const selected = formData.research_depth === d.id;
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() =>
                      setFormData({ ...formData, research_depth: d.id })
                    }
                    className={`text-left rounded-lg p-4 border transition-all ${
                      selected
                        ? "border-[#002B49] bg-[#F0F6FC] dark:bg-blue-950/30 ring-1 ring-[#005A9C]"
                        : "border-[#E2E6EB] dark:border-slate-800 hover:border-[#002B49]/40 bg-white dark:bg-slate-900"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-serif font-semibold text-sm text-[#051C2C] dark:text-white">
                        {d.name}
                      </span>
                      {selected && (
                        <CheckCircle2 className="h-4 w-4 text-[#002B49]" />
                      )}
                    </div>
                    <span className="inline-block text-[10px] font-mono font-medium text-[#002B49] dark:text-blue-300 bg-[#E8F1F8] dark:bg-blue-900/50 px-2 py-0.5 rounded mb-2">
                      {d.sources}
                    </span>
                    <p className="text-xs text-[#718096] dark:text-slate-400 font-sans">
                      {d.desc}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Submit CTA */}
          <div className="flex items-center justify-end gap-4 pt-4">
            <Link
              href="/"
              className="text-xs font-semibold text-[#4A5568] dark:text-slate-400 hover:text-[#051C2C] dark:hover:text-white transition"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-6 py-2.5 text-xs font-semibold text-white shadow-sm transition disabled:opacity-60"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {submitStatusText || "Initializing..."}
                </>
              ) : (
                <>
                  Initialize Strategic Engagement
                  <ChevronRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
