"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";
import { deleteProject } from "@/lib/api";

interface DeleteProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  project: { id: string; topic: string } | null;
  onSuccess?: () => void;
}

export function DeleteProjectDialog({
  isOpen,
  onClose,
  project,
  onSuccess,
}: DeleteProjectDialogProps) {
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: async (projectId: string) => {
      setErrorMessage(null);
      await deleteProject(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      if (onSuccess) {
        onSuccess();
      }
    },
    onError: (err: Error) => {
      setErrorMessage(err.message || "Failed to delete project. Please try again.");
    },
  });

  if (!isOpen || !project) return null;

  const handleDelete = () => {
    deleteMutation.mutate(project.id);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#051C2C]/70 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget && !deleteMutation.isPending) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
    >
      <div className="relative w-full max-w-md rounded-lg bg-white dark:bg-[#0A2234] p-6 shadow-xl border border-[#E2E6EB] dark:border-slate-800 animate-in zoom-in-95 duration-200">
        {/* Close icon button */}
        <button
          onClick={onClose}
          disabled={deleteMutation.isPending}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition disabled:opacity-50"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="flex items-start gap-4">
          <div className="rounded-md bg-[#FDEDED] dark:bg-rose-950/60 p-2.5 text-[#941B1B] dark:text-rose-400 shrink-0 border border-[#F8C4C4]">
            <Trash2 className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3
              id="delete-dialog-title"
              className="text-base font-serif font-bold text-[#051C2C] dark:text-white"
            >
              Delete Project
            </h3>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Are you sure you want to delete{" "}
              <span className="font-semibold text-slate-900 dark:text-slate-200 break-words">
                &ldquo;{project.topic}&rdquo;
              </span>
              ?
            </p>
            <p className="mt-1 text-[11px] text-[#941B1B] dark:text-rose-400 font-medium">
              This action cannot be undone. All research sources, evidence claims,
              synthesis insights, and generated slide decks will be permanently removed.
            </p>

            {errorMessage && (
              <div className="mt-3 flex items-start gap-2 rounded-md bg-[#FDEDED] dark:bg-rose-950/50 p-2.5 text-xs text-[#941B1B] dark:text-rose-300 border border-[#F8C4C4] dark:border-rose-900">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2.5 pt-4 border-t border-[#E2E6EB] dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={deleteMutation.isPending}
            className="rounded-md px-3.5 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 border border-[#E2E6EB] transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-[#941B1B] px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[#7A1616] transition disabled:opacity-50"
          >
            {deleteMutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="h-3.5 w-3.5" />
                Delete Project
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default DeleteProjectDialog;