"use client";

import React from "react";
import Link from "next/link";
import { Settings } from "lucide-react";

export const UserMenu: React.FC = () => {
  return (
    <Link
      href="/settings/webhooks"
      className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[#E2E6EB] dark:border-slate-800 bg-white dark:bg-[#0A2234] hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 transition"
      title="Settings & Webhooks"
    >
      <Settings className="w-3.5 h-3.5 text-slate-500" />
      <span className="hidden sm:inline">Settings</span>
    </Link>
  );
};

export default UserMenu;