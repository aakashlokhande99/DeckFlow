"use client";

import React, { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Presentation,
  Globe,
  Download,
  ExternalLink,
  X,
  CheckCircle2,
  Palette,
  Sparkles,
} from "lucide-react";
import { getExportUrl } from "@/lib/api";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  projectTopic?: string;
}

interface TemplateOption {
  id: string;
  name: string;
  description: string;
  primaryColor: string;
  accentColor: string;
  font: string;
}

const TEMPLATES: TemplateOption[] = [
  {
    id: "mckinsey_navy",
    name: "McKinsey Navy",
    description: "Classic executive consulting theme with deep slate navy and royal blue accents.",
    primaryColor: "#051C2C",
    accentColor: "#002B49",
    font: "Georgia / Calibri",
  },
  {
    id: "bcg_emerald",
    name: "BCG Emerald",
    description: "Strategy-focused corporate theme with deep emerald and vibrant green accents.",
    primaryColor: "#064E3B",
    accentColor: "#0D5E4D",
    font: "Arial",
  },
  {
    id: "bain_crimson",
    name: "Bain Crimson",
    description: "Results-driven executive theme featuring deep burgundy and crimson red accents.",
    primaryColor: "#881337",
    accentColor: "#941B1B",
    font: "Georgia",
  },
  {
    id: "goldman_slate",
    name: "Goldman Slate",
    description: "High-finance corporate identity with charcoal slate and warm amber gold.",
    primaryColor: "#18181B",
    accentColor: "#8D5B00",
    font: "Trebuchet MS",
  },
  {
    id: "modern_tech",
    name: "Modern Tech",
    description: "Modern venture and technology consulting theme with midnight slate and cyber teal.",
    primaryColor: "#0F172A",
    accentColor: "#005A9C",
    font: "Segoe UI",
  },
];

type ExportFormat = "pptx" | "pdf" | "html";

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  projectId,
  projectTopic,
}) => {
  const [format, setFormat] = useState<ExportFormat>("pptx");
  const [template, setTemplate] = useState<string>("mckinsey_navy");
  const [htmlView, setHtmlView] = useState<"presentation" | "document">("presentation");
  const [isDownloading, setIsDownloading] = useState(false);
  const queryClient = useQueryClient();

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleDownload = () => {
    setIsDownloading(true);
    const url = getExportUrl(projectId, format, template, htmlView);
    window.open(url, "_blank");
    setTimeout(() => {
      setIsDownloading(false);
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["storyline", projectId] });
      onClose();
    }, 1000);
  };

  const handlePreview = () => {
    const url = getExportUrl(projectId, "html", template, htmlView);
    window.open(url, "_blank");
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["storyline", projectId] });
    }, 1000);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#051C2C]/70 backdrop-blur-sm animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-modal-title"
    >
      <div
        className="w-full max-w-2xl bg-white rounded-lg shadow-xl border border-[#E2E6EB] overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 bg-[#051C2C] text-white flex items-center justify-between border-b border-[#002B49]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#002B49] text-blue-200 border border-blue-400/30 flex items-center justify-center">
              <Download className="w-4 h-4" />
            </div>
            <div>
              <h2 id="export-modal-title" className="text-sm font-serif font-bold text-white tracking-tight">
                Export Executive Deliverables
              </h2>
              <p className="text-[11px] text-slate-300 truncate max-w-md">
                {projectTopic || "Select format and corporate brand template"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-[#002B49] transition"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Format Selector */}
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-2.5">
              1. Choose Export Format
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* PPTX Option */}
              <button
                type="button"
                onClick={() => setFormat("pptx")}
                className={`p-3.5 rounded-lg border text-left flex flex-col justify-between transition-all ${
                  format === "pptx"
                    ? "border-[#002B49] bg-[#F7F9FB] shadow-sm ring-1 ring-[#002B49]"
                    : "border-[#E2E6EB] bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="w-7 h-7 rounded-md bg-[#FFF8EC] border border-[#F5D6A0] text-[#8D5B00] flex items-center justify-center">
                    <Presentation className="w-4 h-4" />
                  </div>
                  {format === "pptx" && (
                    <CheckCircle2 className="w-4 h-4 text-[#002B49]" />
                  )}
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-900">PowerPoint (.pptx)</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    16:9 widescreen deck with editable tables and cards
                  </div>
                </div>
              </button>

              {/* PDF Option */}
              <button
                type="button"
                onClick={() => setFormat("pdf")}
                className={`p-3.5 rounded-lg border text-left flex flex-col justify-between transition-all ${
                  format === "pdf"
                    ? "border-[#002B49] bg-[#F7F9FB] shadow-sm ring-1 ring-[#002B49]"
                    : "border-[#E2E6EB] bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="w-7 h-7 rounded-md bg-[#FDEDED] border border-[#F8C4C4] text-[#941B1B] flex items-center justify-center">
                    <FileText className="w-4 h-4" />
                  </div>
                  {format === "pdf" && (
                    <CheckCircle2 className="w-4 h-4 text-[#002B49]" />
                  )}
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-900">Executive PDF (.pdf)</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    Publication memo with running headers &amp; risk matrix
                  </div>
                </div>
              </button>

              {/* HTML Option */}
              <button
                type="button"
                onClick={() => setFormat("html")}
                className={`p-3.5 rounded-lg border text-left flex flex-col justify-between transition-all ${
                  format === "html"
                    ? "border-[#002B49] bg-[#F7F9FB] shadow-sm ring-1 ring-[#002B49]"
                    : "border-[#E2E6EB] bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="w-7 h-7 rounded-md bg-[#EBF7F2] border border-[#BCE3D2] text-[#0D5E4D] flex items-center justify-center">
                    <Globe className="w-4 h-4" />
                  </div>
                  {format === "html" && (
                    <CheckCircle2 className="w-4 h-4 text-[#002B49]" />
                  )}
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-900">Interactive Web (.html)</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    Standalone offline deck with speaker notes &amp; keyboard nav
                  </div>
                </div>
              </button>
            </div>
          </div>

          {/* HTML View Mode (Conditional for HTML format) */}
          {format === "html" && (
            <div className="p-3.5 bg-[#F7F9FB] rounded-lg border border-[#E2E6EB]">
              <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-2">
                Initial HTML View Mode
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-xs font-medium text-slate-800 cursor-pointer">
                  <input
                    type="radio"
                    name="htmlView"
                    value="presentation"
                    checked={htmlView === "presentation"}
                    onChange={() => setHtmlView("presentation")}
                    className="text-[#002B49] focus:ring-[#002B49]"
                  />
                  16:9 Presentation Mode (Widescreen Stage)
                </label>
                <label className="flex items-center gap-2 text-xs font-medium text-slate-800 cursor-pointer">
                  <input
                    type="radio"
                    name="htmlView"
                    value="document"
                    checked={htmlView === "document"}
                    onChange={() => setHtmlView("document")}
                    className="text-[#002B49] focus:ring-[#002B49]"
                  />
                  Executive Document Mode (Vertical Scroll)
                </label>
              </div>
            </div>
          )}

          {/* Corporate Brand Template Selector */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                <Palette className="w-3.5 h-3.5 text-slate-500" />
                2. Corporate Brand Theme &amp; Palette
              </label>
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">5 Enterprise Presets</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {TEMPLATES.map((tmpl) => {
                const isSelected = template === tmpl.id;
                return (
                  <button
                    key={tmpl.id}
                    type="button"
                    onClick={() => setTemplate(tmpl.id)}
                    className={`p-3 rounded-lg border text-left flex items-start gap-3 transition-all ${
                      isSelected
                        ? "border-[#002B49] bg-[#F7F9FB] ring-1 ring-[#002B49] shadow-sm"
                        : "border-[#E2E6EB] hover:border-slate-300 bg-white"
                    }`}
                  >
                    {/* Color Swatch Circle */}
                    <div className="flex -space-x-1 flex-shrink-0 mt-0.5">
                      <div
                        className="w-4 h-4 rounded-full border border-white shadow-sm"
                        style={{ backgroundColor: tmpl.primaryColor }}
                        title={`Primary: ${tmpl.primaryColor}`}
                      />
                      <div
                        className="w-4 h-4 rounded-full border border-white shadow-sm"
                        style={{ backgroundColor: tmpl.accentColor }}
                        title={`Accent: ${tmpl.accentColor}`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-900 truncate">
                          {tmpl.name}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          {tmpl.font}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                        {tmpl.description}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-[#F7F9FB] border-t border-[#E2E6EB] flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <Sparkles className="w-3.5 h-3.5 text-[#002B49]" />
            <span>Strict Human Review Gate Enforced</span>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 rounded-md border border-[#E2E6EB] transition"
            >
              Cancel
            </button>

            {format === "html" && (
              <button
                type="button"
                onClick={handlePreview}
                className="px-4 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-[#E2E6EB] hover:bg-slate-50 rounded-md flex items-center gap-1.5 transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Live Preview
              </button>
            )}

            <button
              type="button"
              onClick={handleDownload}
              disabled={isDownloading}
              className="px-4 py-1.5 text-xs font-bold text-white bg-[#002B49] hover:bg-[#051C2C] rounded-md shadow-sm flex items-center gap-1.5 transition disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              {isDownloading ? "Generating..." : `Download .${format}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExportModal;