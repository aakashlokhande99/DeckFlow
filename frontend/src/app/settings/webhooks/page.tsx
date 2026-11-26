"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  ArrowLeft,
  Plus,
  Trash2,
  AlertCircle,
  X,
} from "lucide-react";
import {
  listWebhookSubscriptions,
  createWebhookSubscription,
  deleteWebhookSubscription,
} from "@/lib/api";
import { UserMenu } from "@/components/UserMenu";

export default function WebhooksPage() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [targetType, setTargetType] = useState<"slack" | "teams" | "generic">("slack");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([
    "slide_review_gate",
    "synthesis_review_gate",
  ]);
  const [secret, setSecret] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    data: subscriptions = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["webhooks"],
    queryFn: listWebhookSubscriptions,
  });

  const createMutation = useMutation({
    mutationFn: createWebhookSubscription,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
      setIsModalOpen(false);
      resetForm();
    },
    onError: (err: any) => {
      setSubmitError(err.message || "Failed to register webhook subscription.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWebhookSubscription,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });

  const resetForm = () => {
    setUrl("");
    setTargetType("slack");
    setSelectedEvents(["slide_review_gate", "synthesis_review_gate"]);
    setSecret("");
    setSubmitError(null);
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (!url.startsWith("https://")) {
      setSubmitError("Webhook endpoint must use a secure public HTTPS URL.");
      return;
    }

    createMutation.mutate({
      url,
      target_type: targetType,
      events: selectedEvents,
      secret: secret ? secret : null,
    });
  };

  const toggleEvent = (eventName: string) => {
    if (selectedEvents.includes(eventName)) {
      if (selectedEvents.length === 1) return; // Keep at least one
      setSelectedEvents(selectedEvents.filter((e) => e !== eventName));
    } else {
      setSelectedEvents([...selectedEvents, eventName]);
    }
  };

  return (
    <div className="min-h-screen bg-[#F7F9FB] dark:bg-[#051C2C] pb-20">
      {/* ── Top Navigation ────────────────────────────────────────── */}
      <header className="border-b border-[#E2E6EB] dark:border-slate-800 bg-white/95 dark:bg-[#0A2234]/95 backdrop-blur sticky top-0 z-10 px-6 py-4">
        <div className="mx-auto max-w-5xl flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-[#002B49] dark:hover:text-white transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Projects
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                resetForm();
                setIsModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md bg-[#002B49] text-white hover:bg-[#051C2C] shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Webhook
            </button>
            <UserMenu />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pt-8 space-y-6">
        {/* Header Card */}
        <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 sm:p-8 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-md bg-[#002B49] text-white flex items-center justify-center">
              <Bell className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-serif font-bold text-[#051C2C] dark:text-white tracking-tight">
                Webhook Notification Endpoints
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Receive instant Slack Block Kit &amp; MS Teams Adaptive Card alerts when human review gates arrive
              </p>
            </div>
          </div>
        </div>

        {/* Subscriptions List */}
        <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] p-6 shadow-sm">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#051C2C] dark:text-white mb-4 flex items-center justify-between">
            <span>Configured Endpoints ({subscriptions.length})</span>
            <span className="text-[11px] font-normal text-slate-400">SSRF-protected dispatch</span>
          </h2>

          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 rounded-md bg-slate-100 dark:bg-slate-800/50 animate-pulse" />
              ))}
            </div>
          ) : isError ? (
            <div className="rounded-md border border-[#F8C4C4] dark:border-rose-900 bg-[#FDEDED] dark:bg-rose-950/30 p-4 text-xs text-[#941B1B] dark:text-rose-300">
              {error?.message || "Failed to load webhook subscriptions."}
            </div>
          ) : subscriptions.length === 0 ? (
            <div className="text-center py-12 border border-dashed border-[#E2E6EB] dark:border-slate-800 rounded-md">
              <Bell className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2" />
              <p className="text-sm font-serif font-bold text-[#051C2C] dark:text-slate-300">No Webhooks Configured</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
                Connect your Slack channel or Microsoft Teams team to receive automated alerts whenever a research review gate opens.
              </p>
              <button
                onClick={() => setIsModalOpen(true)}
                className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-[#002B49] text-white hover:bg-[#051C2C] transition"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Your First Webhook
              </button>
            </div>
          ) : (
            <div className="divide-y divide-[#E2E6EB] dark:divide-slate-800">
              {subscriptions.map((sub) => (
                <div key={sub.id} className="py-4 flex items-center justify-between gap-4">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${
                          sub.target_type === "slack"
                            ? "bg-[#EBF7F2] text-[#0D5E4D] border-[#BCE3D2] dark:bg-emerald-950/40 dark:text-emerald-300"
                            : sub.target_type === "teams"
                            ? "bg-[#EBF2F7] text-[#002B49] border-[#CCDCE8] dark:bg-indigo-950/40 dark:text-indigo-300"
                            : "bg-[#F7F9FB] text-slate-700 border-[#E2E6EB] dark:bg-slate-800 dark:text-slate-300"
                        }`}
                      >
                        {sub.target_type}
                      </span>
                      <span className="text-xs font-mono font-medium text-slate-800 dark:text-slate-200 truncate max-w-md">
                        {sub.url}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                      <span>Events: {sub.events.join(", ")}</span>
                      <span>•</span>
                      <span>Created {new Date(sub.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => deleteMutation.mutate(sub.id)}
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded-md text-slate-400 hover:text-[#941B1B] hover:bg-[#FDEDED] dark:hover:bg-rose-950/30 transition"
                      title="Delete webhook"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* ── Add Webhook Modal ────────────────────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#051C2C]/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-lg bg-white dark:bg-[#0A2234] rounded-lg shadow-2xl border border-[#E2E6EB] dark:border-slate-800 overflow-hidden">
            <div className="px-6 py-4 bg-[#051C2C] text-white flex items-center justify-between border-b border-[#002B49]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-md bg-[#002B49] text-blue-200 border border-blue-400/30 flex items-center justify-center">
                  <Bell className="w-4 h-4" />
                </div>
                <h2 className="text-xs font-serif font-bold text-white tracking-tight">Add Review Gate Webhook</h2>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-[#002B49] transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {submitError && (
                <div className="rounded-md border border-[#F8C4C4] dark:border-rose-900 bg-[#FDEDED] dark:bg-rose-950/30 p-3 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-[#941B1B] mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-[#941B1B] dark:text-rose-300">{submitError}</p>
                </div>
              )}

              <div>
                <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                  Target Service
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(["slack", "teams", "generic"] as const).map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setTargetType(type)}
                      className={`p-2.5 rounded-md border text-center text-xs font-bold capitalize transition ${
                        targetType === type
                          ? "border-[#002B49] bg-[#F7F9FB] dark:bg-blue-950/40 text-[#002B49] dark:text-blue-300 ring-1 ring-[#002B49]"
                          : "border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300"
                      }`}
                    >
                      {type === "slack" ? "Slack" : type === "teams" ? "MS Teams" : "Generic HTTP"}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                  Endpoint URL (HTTPS Only)
                </label>
                <input
                  type="url"
                  required
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={
                    targetType === "slack"
                      ? "https://hooks.slack.com/services/..."
                      : targetType === "teams"
                      ? "https://acme.webhook.office.com/webhookb2/..."
                      : "https://api.acme.com/webhook"
                  }
                  className="w-full rounded-md border border-[#E2E6EB] dark:border-slate-800 bg-[#F7F9FB] dark:bg-slate-950 px-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#002B49] transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                  Subscribed Review Events
                </label>
                <div className="space-y-2">
                  {[
                    { id: "slide_review_gate", label: "Slide-Level Storyline Review Gate" },
                    { id: "synthesis_review_gate", label: "Consulting Synthesis QA Review Gate" },
                  ].map((evt) => (
                    <label
                      key={evt.id}
                      className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedEvents.includes(evt.id)}
                        onChange={() => toggleEvent(evt.id)}
                        className="rounded border-[#E2E6EB] text-[#002B49] focus:ring-[#002B49]"
                      />
                      {evt.label}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                  Signing Secret (Optional HMAC SHA-256)
                </label>
                <input
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  placeholder="Optional secret for X-Webhook-Signature verification"
                  className="w-full rounded-md border border-[#E2E6EB] dark:border-slate-800 bg-[#F7F9FB] dark:bg-slate-950 px-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#002B49] transition"
                />
              </div>

              <div className="pt-3 border-t border-[#E2E6EB] dark:border-slate-800 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white rounded-md border border-[#E2E6EB] dark:border-slate-800 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-1.5 text-xs font-bold text-white bg-[#002B49] hover:bg-[#051C2C] rounded-md shadow-sm transition disabled:opacity-50"
                >
                  {createMutation.isPending ? "Registering..." : "Save Endpoint"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}