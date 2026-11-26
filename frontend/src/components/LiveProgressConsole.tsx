"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Layers,
  Radio,
  Sparkles,
  Terminal,
} from "lucide-react";
import { AgentLogEntry } from "@/lib/useProjectWebSocket";

interface LiveProgressConsoleProps {
  projectId: string;
  isConnected: boolean;
  activeAgent: string | null;
  currentStep: string | null;
  progress: number;
  logs: AgentLogEntry[];
  reviewAlert: boolean;
  projectStatus: string;
}

export function LiveProgressConsole({
  projectId,
  isConnected,
  activeAgent,
  currentStep,
  progress,
  logs,
  reviewAlert,
  projectStatus,
}: LiveProgressConsoleProps) {
  const [isConsoleOpen, setIsConsoleOpen] = useState(true);

  // If status is running or awaiting review, show live execution
  const isRunning = projectStatus === "running";
  const isAwaitingReview = projectStatus === "awaiting_review" || reviewAlert;
  const isCompleted = projectStatus === "completed";
  const displayProgress = isCompleted ? 100 : progress;

  return (
    <div className="space-y-4">
      {/* ── Delivery Completed Banner ────────────────────────────── */}
      {isCompleted && (
        <div className="rounded-lg border border-[#B4DFD4] bg-[#EDF7F4] dark:bg-[#0D5E4D]/20 p-5 shadow-sm border-l-4 border-l-[#0D5E4D] animate-in fade-in duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="rounded bg-[#0D5E4D]/15 p-2 text-[#0D5E4D] dark:text-[#34D399]">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] kicker bg-[#0D5E4D] text-white">
                    Deliverable Complete
                  </span>
                  <span className="text-xs font-mono font-medium text-[#0D5E4D] dark:text-[#34D399]">
                    100% Finalized
                  </span>
                </div>
                <h4 className="text-base font-serif font-semibold text-[#051C2C] dark:text-white">
                  Executive PowerPoint Presentation & Strategic Deliverables Ready
                </h4>
                <p className="text-xs text-[#4A5568] dark:text-slate-300 max-w-xl">
                  The executive presentation deck has been synthesized, audited against evidence, reviewed, and rendered. You may download PPTX or review storylines at any time.
                </p>
              </div>
            </div>

            <Link
              href={`/projects/${projectId}/storyline`}
              className="inline-flex items-center justify-center gap-2 rounded bg-[#002B49] hover:bg-[#051C2C] px-4 py-2 text-xs font-semibold text-white shadow-sm transition shrink-0"
            >
              <Layers className="h-4 w-4" />
              View Storyline Studio
            </Link>
          </div>
        </div>
      )}

      {/* ── Review Alert Push Notification ───────────────────────── */}
      {isAwaitingReview && (
        <div className="rounded-lg border border-[#F5D6A0] bg-[#FFF8EC] dark:bg-[#8D5B00]/20 p-5 shadow-sm border-l-4 border-l-[#8D5B00] animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="rounded bg-[#8D5B00]/15 p-2 text-[#8D5B00]">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] kicker bg-[#8D5B00] text-white">
                    Gate 1 Active
                  </span>
                  <span className="text-xs font-mono text-[#8D5B00] font-medium">
                    Human Review Required
                  </span>
                </div>
                <h4 className="text-base font-serif font-semibold text-[#051C2C] dark:text-white">
                  Research Synthesis Ready for Human Approval
                </h4>
                <p className="text-xs text-[#4A5568] dark:text-slate-300 max-w-xl">
                  Evidence extraction and 5-point QA audit are complete. Review findings, citations, and risk matrices before slide storyline generation.
                </p>
              </div>
            </div>

            <Link
              href={`/projects/${projectId}/review`}
              className="inline-flex items-center justify-center gap-2 rounded bg-[#8D5B00] hover:bg-[#704800] px-4 py-2 text-xs font-semibold text-white shadow-sm transition shrink-0"
            >
              Enter Review Gate
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      )}

      {/* ── Real-Time Agent Execution Console ───────────────────────── */}
      <div className="rounded-lg border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#051C2C] p-6 shadow-sm space-y-5 border-t-2 border-t-[#002B49]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded bg-[#F0F6FC] dark:bg-slate-800 p-2.5 text-[#002B49] dark:text-[#60A5FA]">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-serif font-semibold text-[#051C2C] dark:text-white">
                  Autonomous Research Intelligence Stream
                </h3>
                <span className="flex items-center gap-1.5 text-[10px] kicker px-2 py-0.5 rounded border border-[#E2E6EB] dark:border-slate-700 bg-[#F7F9FB] dark:bg-slate-800 text-[#4A5568] dark:text-slate-300">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      isConnected
                        ? "bg-[#0D5E4D] animate-ping"
                        : "bg-slate-400"
                    }`}
                  />
                  {isConnected ? "Live Telemetry" : "Connecting..."}
                </span>
              </div>
              <p className="text-xs text-[#718096] dark:text-slate-400">
                Multi-agent LangGraph orchestration telemetry & live step telemetry
              </p>
            </div>
          </div>

          {/* Active Agent Pill */}
          {activeAgent && (
            <div className="flex items-center gap-2 self-start sm:self-auto rounded border border-[#B9D7F2] dark:border-slate-700 bg-[#F0F6FC] dark:bg-slate-800 px-3 py-1 text-xs font-medium text-[#002B49] dark:text-[#60A5FA]">
              <Cpu className="h-3.5 w-3.5 animate-spin text-[#005A9C]" />
              <span className="kicker text-[10px]">Active Agent: {activeAgent}</span>
            </div>
          )}
        </div>

        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-[#4A5568] dark:text-slate-300 flex items-center gap-1.5">
              <Activity className={`h-3.5 w-3.5 ${isCompleted ? "text-[#0D5E4D]" : "text-[#005A9C]"}`} />
              {isCompleted
                ? "Delivery Completed: Presentation Deck Ready"
                : currentStep
                ? `Current Step: ${currentStep.replace("_", " ").toUpperCase()}`
                : isRunning
                ? "Executing Research Workflow..."
                : "Awaiting Trigger"}
            </span>
            <span className={`font-mono font-bold tabular-nums ${isCompleted ? "text-[#0D5E4D]" : "text-[#051C2C] dark:text-white"}`}>
              {displayProgress}%
            </span>
          </div>

          <div className="w-full h-1.5 rounded-none bg-[#E2E6EB] dark:bg-slate-800 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ease-out ${
                isCompleted
                  ? "bg-[#0D5E4D]"
                  : "bg-[#002B49]"
              }`}
              style={{ width: `${displayProgress}%` }}
            />
          </div>
        </div>

        {/* Activity Feed Toggle Header */}
        <div className="border-t border-[#ECEFF2] dark:border-slate-800 pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#051C2C] dark:text-slate-200">
              <Terminal className="h-3.5 w-3.5 text-[#718096]" />
              <span className="kicker">Agent Execution Telemetry Log</span>
              {logs.length > 0 && (
                <span className="rounded bg-[#F7F9FB] dark:bg-slate-800 border border-[#E2E6EB] dark:border-slate-700 px-2 py-0.2 text-[10px] text-[#4A5568] dark:text-slate-400 font-mono">
                  {logs.length} events
                </span>
              )}
            </div>

            <button
              onClick={() => setIsConsoleOpen(!isConsoleOpen)}
              className="inline-flex items-center gap-1 text-xs text-[#718096] hover:text-[#051C2C] dark:hover:text-white transition"
            >
              {isConsoleOpen ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" /> Hide Logs
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" /> View Logs
                </>
              )}
            </button>
          </div>

          {/* Collapsible Log Stream */}
          {isConsoleOpen && (
            <div className="mt-3 rounded border border-[#E2E6EB] dark:border-slate-800 bg-[#051C2C] p-4 font-mono text-xs text-slate-300 max-h-60 overflow-y-auto space-y-2 scrollbar-thin">
              {logs.length === 0 ? (
                <p className="text-slate-400 italic text-[11px]">
                  {projectStatus === "failed"
                    ? "Workflow run failed before streaming live events. See the error details above or click Retry."
                    : "No agent events received yet. Start the research workflow to observe live agent telemetry."}
                </p>
              ) : (
                logs.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-start gap-2.5 text-[11px] leading-relaxed border-b border-slate-800/80 pb-1.5 last:border-none"
                  >
                    <span className="text-slate-500 shrink-0 font-mono">
                      {new Date(log.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                    <span className="font-semibold text-[#60A5FA] shrink-0">
                      [{log.agent.toUpperCase()}]
                    </span>
                    <span className="text-slate-200">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
