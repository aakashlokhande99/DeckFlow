"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileCheck2,
  FileText,
  Layers,
  Lightbulb,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import {
  getProjectReview,
  submitProjectReview,
  ReviewDecisionPayload,
  FindingItem,
} from "@/lib/api";

export default function ProjectReviewPage({
  params,
}: {
  params: { id: string };
}) {
  const id = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [comments, setComments] = useState("");
  const [rejectedFindingIds, setRejectedFindingIds] = useState<string[]>([]);
  const [editedFindings, setEditedFindings] = useState<Record<string, string>>({});
  const [editingFindingId, setEditingFindingId] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const {
    data: review,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["project_review", id],
    queryFn: () => getProjectReview(id),
  });

  const mutation = useMutation({
    mutationFn: (decision: ReviewDecisionPayload) => submitProjectReview(id, decision),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["project_review", id] });
      setActionSuccess(data.message || "Decision recorded.");
      if (data.action === "approve") {
        setTimeout(() => {
          router.push(`/projects/${id}/storyline`);
        }, 1500);
      }
    },
  });

  const handleToggleRejectFinding = (fid: string) => {
    setRejectedFindingIds((prev) =>
      prev.includes(fid) ? prev.filter((item) => item !== fid) : [...prev, fid]
    );
  };

  const handleSaveFindingEdit = (fid: string, newText: string) => {
    setEditedFindings((prev) => ({ ...prev, [fid]: newText }));
    setEditingFindingId(null);
  };

  const handleSubmitDecision = (action: "approve" | "revise" | "research_more") => {
    const payload: ReviewDecisionPayload = {
      action,
      comments: comments.trim() || undefined,
      rejected_ids: rejectedFindingIds,
      edited_items: Object.keys(editedFindings).length > 0 ? { findings: editedFindings } : undefined,
    };
    mutation.mutate(payload);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] p-8 flex items-center justify-center">
        <div className="text-center space-y-3">
          <Loader2 className="h-8 w-8 text-[#002B49] dark:text-blue-300 animate-spin mx-auto" />
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300 tracking-wide uppercase">
            Loading evidence and synthesis review payload...
          </p>
        </div>
      </div>
    );
  }

  if (isError || !review) {
    return (
      <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] p-8 flex items-center justify-center">
        <div className="max-w-md w-full rounded-lg border border-[#F8C4C4] dark:border-rose-900 bg-white dark:bg-[#0A2234] p-8 text-center space-y-4 shadow-sm">
          <p className="text-[#941B1B] dark:text-rose-400 font-bold text-sm tracking-wide">Failed to Load Review Payload</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{error?.message}</p>
          <Link
            href={`/projects/${id}`}
            className="inline-block rounded-md bg-[#002B49] px-5 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-[#051C2C] transition"
          >
            Return to Project
          </Link>
        </div>
      </div>
    );
  }

  const insight = review.insight;
  const qa = insight?.qa_report;

  return (
    <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] pb-36">
      {/* ── Top Bar ──────────────────────────────────────────────── */}
      <header className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#0A2234]/95 backdrop-blur sticky top-0 z-20 px-6 py-4">
        <div className="mx-auto max-w-5xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href={`/projects/${id}`}
              className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-[#002B49] dark:hover:text-white transition"
            >
              <ArrowLeft className="h-4 w-4" />
              Project Dashboard
            </Link>
            <span className="text-[#E2E6EB] dark:text-slate-700">|</span>
            <span className="text-[11px] font-semibold text-[#8D5B00] dark:text-amber-300 bg-[#FFF8EC] dark:bg-amber-950/60 px-2.5 py-1 rounded border border-[#F5D6A0] dark:border-amber-900 flex items-center gap-1.5 uppercase tracking-wider">
              <FileCheck2 className="h-3.5 w-3.5" />
              Human Review Pause Gate (v{insight?.version || 1})
            </span>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-300 border border-[#E2E6EB] dark:border-slate-700 rounded-md px-3 py-1.5 bg-white dark:bg-[#0A2234] hover:bg-slate-50 transition font-medium"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pt-8 space-y-8">
        {/* Banner: Action Feedback */}
        {actionSuccess && (
          <div className="rounded-lg border border-[#BCE3D2] dark:border-emerald-900 bg-[#EBF7F2] dark:bg-emerald-950/50 p-4 text-[#0D5E4D] dark:text-emerald-200 text-xs font-semibold flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-[#0D5E4D] shrink-0" />
            {actionSuccess}
          </div>
        )}

        {/* ── Section: QA Gate Report ──────────────────────────────── */}
        {qa && (
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E6EB] dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-[#002B49] dark:text-blue-300" />
                <span className="text-xs font-bold uppercase tracking-wider text-[#051C2C] dark:text-white">
                  Automated Synthesis Quality Gate
                </span>
              </div>
              <span
                className={`text-[11px] font-semibold px-2.5 py-0.5 rounded border uppercase tracking-wider ${
                  qa.passed
                    ? "bg-[#EBF7F2] text-[#0D5E4D] border-[#BCE3D2] dark:bg-emerald-950 dark:text-emerald-300"
                    : "bg-[#FFF8EC] text-[#8D5B00] border-[#F5D6A0] dark:bg-amber-950 dark:text-amber-300"
                }`}
              >
                {qa.passed ? "QA Standards Met" : "Quality Warning"} (Score: {(qa.overall_score * 100).toFixed(0)}%)
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1 text-xs">
              <div className="rounded-md border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-900/50">
                <span className="text-slate-500 dark:text-slate-400 block mb-1 text-[11px] uppercase tracking-wider">Citation Completeness</span>
                <span className="font-bold text-[#051C2C] dark:text-slate-100 text-base">
                  {(qa.citation_completeness_score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="rounded-md border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-900/50">
                <span className="text-slate-500 dark:text-slate-400 block mb-1 text-[11px] uppercase tracking-wider">Question Coverage</span>
                <span className="font-bold text-[#051C2C] dark:text-slate-100 text-base">
                  {(qa.question_coverage_score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="rounded-md border border-[#E2E6EB] dark:border-slate-800 p-3 bg-[#F7F9FB] dark:bg-slate-900/50">
                <span className="text-slate-500 dark:text-slate-400 block mb-1 text-[11px] uppercase tracking-wider">Recommendation Actionability</span>
                <span className="font-bold text-[#051C2C] dark:text-slate-100 text-base">
                  {(qa.actionability_score * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {qa.issues && qa.issues.length > 0 && (
              <div className="mt-3 space-y-1.5 pt-2 border-t border-[#E2E6EB] dark:border-slate-800">
                {qa.issues.map((issue, idx) => (
                  <p key={idx} className="text-xs text-[#8D5B00] dark:text-amber-300 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                    {issue}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Section: Executive Summary ────────────────────────────── */}
        {insight && (
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 border-l-4 border-l-[#002B49] bg-white dark:bg-[#0A2234] p-6 sm:p-8 shadow-sm space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-[#002B49] dark:text-blue-300" />
              <h2 className="text-lg font-serif font-bold text-[#051C2C] dark:text-white tracking-tight">
                Executive Summary
              </h2>
            </div>
            <p className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed whitespace-pre-line">
              {insight.executive_summary}
            </p>
          </div>
        )}

        {/* ── Section: Key Findings ─────────────────────────────────── */}
        {insight && insight.findings && insight.findings.length > 0 && (
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 sm:p-8 shadow-sm space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E6EB] dark:border-slate-800">
              <div>
                <h2 className="text-lg font-serif font-bold text-[#051C2C] dark:text-white flex items-center gap-2 tracking-tight">
                  <Lightbulb className="h-4 w-4 text-[#002B49] dark:text-blue-300" />
                  Key Findings &amp; Evidence Backing
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Verify empirical claims. Reject unsupported items or edit wording inline.
                </p>
              </div>
              <span className="text-xs text-slate-500 font-semibold uppercase tracking-wider">
                {insight.findings.length} findings
              </span>
            </div>

            <div className="space-y-4">
              {insight.findings.map((f: FindingItem) => {
                const isRejected = rejectedFindingIds.includes(f.id);
                const currentText = editedFindings[f.id] || f.finding;
                const isEditing = editingFindingId === f.id;

                return (
                  <div
                    key={f.id}
                    className={`rounded-lg border p-4 transition ${
                      isRejected
                        ? "border-[#F8C4C4] dark:border-rose-900 bg-[#FDEDED]/50 dark:bg-rose-950/20 opacity-60"
                        : "border-[#E2E6EB] dark:border-slate-800 bg-[#F7F9FB]/60 dark:bg-slate-900/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-[11px] px-2 py-0.5 rounded bg-[#002B49] text-white">
                            {f.id}
                          </span>
                          {f.is_uncertain ? (
                            <span className="text-[11px] font-semibold text-[#8D5B00] dark:text-amber-300 bg-[#FFF8EC] dark:bg-amber-950/60 px-2 py-0.5 rounded border border-[#F5D6A0] dark:border-amber-900 uppercase tracking-wider">
                              Uncertain / Lacks Proof
                            </span>
                          ) : (
                            <span className="text-[11px] font-semibold text-[#0D5E4D] dark:text-emerald-300 bg-[#EBF7F2] dark:bg-emerald-950/60 px-2 py-0.5 rounded border border-[#BCE3D2] dark:border-emerald-900 uppercase tracking-wider">
                              Supported ({f.confidence || "high"})
                            </span>
                          )}
                          {isRejected && (
                            <span className="text-[11px] font-bold text-[#941B1B] uppercase tracking-wider">
                              • Rejected for slides
                            </span>
                          )}
                        </div>

                        {isEditing ? (
                          <div className="space-y-2">
                            <textarea
                              rows={3}
                              defaultValue={currentText}
                              id={`edit-${f.id}`}
                              className="w-full rounded-md border border-[#E2E6EB] dark:border-slate-700 bg-white dark:bg-slate-900 p-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-[#002B49]"
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => {
                                  const el = document.getElementById(
                                    `edit-${f.id}`
                                  ) as HTMLTextAreaElement;
                                  if (el) handleSaveFindingEdit(f.id, el.value);
                                }}
                                className="px-3 py-1 bg-[#002B49] text-white rounded-md text-xs font-semibold hover:bg-[#051C2C] transition"
                              >
                                Save Edit
                              </button>
                              <button
                                onClick={() => setEditingFindingId(null)}
                                className="px-3 py-1 border border-[#E2E6EB] text-slate-600 rounded-md text-xs hover:bg-slate-50 transition"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p
                            className={`text-sm text-slate-800 dark:text-slate-200 leading-relaxed ${
                              isRejected ? "line-through" : ""
                            }`}
                          >
                            {currentText}
                          </p>
                        )}

                        <div className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-2 pt-1">
                          <span className="uppercase tracking-wider text-[10px]">Evidence links:</span>
                          {f.evidence_ids && f.evidence_ids.length > 0 ? (
                            f.evidence_ids.map((eid) => (
                              <code
                                key={eid}
                                className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-800 border border-[#E2E6EB] dark:border-slate-700 text-slate-700 dark:text-slate-300 text-[10px] font-mono"
                              >
                                {eid.slice(0, 8)}...
                              </code>
                            ))
                          ) : (
                            <span className="text-[#8D5B00] font-semibold text-[10px] uppercase">None (Ungrounded)</span>
                          )}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setEditingFindingId(isEditing ? null : f.id)}
                          className="text-xs text-slate-700 hover:text-[#002B49] dark:hover:text-white border border-[#E2E6EB] dark:border-slate-700 px-2.5 py-1 rounded-md bg-white dark:bg-slate-800 transition font-medium"
                        >
                          {isEditing ? "Cancel" : "Edit"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleRejectFinding(f.id)}
                          className={`text-xs px-2.5 py-1 rounded-md border transition font-medium ${
                            isRejected
                              ? "border-[#BCE3D2] text-[#0D5E4D] bg-[#EBF7F2] dark:bg-emerald-950/50 font-semibold"
                              : "border-[#F8C4C4] text-[#941B1B] bg-[#FDEDED] dark:bg-rose-950/50 hover:bg-[#FCDCDC]"
                          }`}
                        >
                          {isRejected ? "Restore" : "Reject"}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Section: Recommendations & Implications ───────────────── */}
        {insight && insight.recommendations && (
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 sm:p-8 shadow-sm space-y-4">
            <h2 className="text-lg font-serif font-bold text-[#051C2C] dark:text-white flex items-center gap-2 tracking-tight">
              <Layers className="h-4 w-4 text-[#002B49] dark:text-blue-300" />
              Strategic Recommendations
            </h2>
            <div className="space-y-3">
              {insight.recommendations.map((r, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 p-4 bg-[#F7F9FB]/60 dark:bg-slate-900/30 flex items-start justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-xs text-[#002B49] dark:text-blue-300 uppercase">
                        {r.id || `R${i + 1}`}
                      </span>
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-[#EBF2F7] text-[#002B49] border border-[#CCDCE8]">
                        {r.priority} Priority
                      </span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">
                        Horizon: {r.timeframe}
                      </span>
                    </div>
                    <p className="text-sm text-slate-900 dark:text-slate-200 font-medium leading-relaxed">
                      {r.action}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Section: Verified Sources ─────────────────────────────── */}
        {review.sources && review.sources.length > 0 && (
          <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 sm:p-8 shadow-sm space-y-4">
            <h2 className="text-lg font-serif font-bold text-[#051C2C] dark:text-white flex items-center gap-2 tracking-tight">
              <Search className="h-4 w-4 text-[#002B49] dark:text-blue-300" />
              Consulted Sources ({review.sources.length})
            </h2>
            <div className="divide-y divide-[#E2E6EB] dark:divide-slate-800">
              {review.sources.map((s) => (
                <div key={s.id} className="py-3 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-semibold text-slate-900 dark:text-slate-200 block">
                      {s.title || "Untitled Web Document"}
                    </span>
                    <span className="text-slate-500 dark:text-slate-400 text-[11px]">
                      {s.publisher || "Publisher not stated"} {s.pub_date ? `• ${s.pub_date}` : ""}
                    </span>
                  </div>
                  <a
                    href={s.canonical_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[#005A9C] hover:underline shrink-0 font-medium"
                  >
                    View Source
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* ── Sticky Bottom Decision Bar ────────────────────────────── */}
      <footer className="fixed bottom-0 left-0 right-0 border-t border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#0A2234]/95 backdrop-blur z-30 p-4 shadow-lg">
        <div className="mx-auto max-w-5xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="w-full sm:flex-1">
            <input
              type="text"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Add optional reviewer guidance, revisions, or feedback..."
              className="w-full rounded-md border border-[#E2E6EB] dark:border-slate-700 bg-[#F7F9FB] dark:bg-slate-900 px-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#002B49]"
            />
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => handleSubmitDecision("research_more")}
              className="rounded-md border border-[#002B49] text-[#002B49] dark:text-blue-300 dark:border-blue-400 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-semibold hover:bg-[#F7F9FB] transition disabled:opacity-50"
            >
              Research More
            </button>

            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => handleSubmitDecision("revise")}
              className="rounded-md border border-[#F5D6A0] text-[#8D5B00] dark:text-amber-300 dark:border-amber-900 bg-[#FFF8EC] dark:bg-amber-950/40 px-4 py-2 text-xs font-semibold hover:bg-[#FDF0D5] transition disabled:opacity-50"
            >
              Request Revision
            </button>

            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => handleSubmitDecision("approve")}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#0D5E4D] px-5 py-2 text-xs font-bold text-white shadow-sm hover:bg-[#0A473A] transition disabled:opacity-50"
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Recording...
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  Approve Synthesis
                </>
              )}
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}