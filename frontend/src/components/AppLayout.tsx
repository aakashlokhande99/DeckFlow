"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Layers, Menu } from "lucide-react";
import { RecentProjectsSidebar } from "./RecentProjectsSidebar";
import { UserMenu } from "./UserMenu";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex bg-[#F7F9FB] dark:bg-[#051C2C] text-[#121820] dark:text-slate-100 font-sans">
      {/* Sidebar for Recent Projects */}
      <RecentProjectsSidebar
        isMobileOpen={mobileSidebarOpen}
        onMobileClose={() => setMobileSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Mobile Header Bar (visible only on small screens < md) */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white/95 dark:bg-[#051C2C]/95 backdrop-blur border-b border-[#E2E6EB] dark:border-slate-800 sticky top-0 z-30">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(true)}
              className="p-1.5 -ml-1 rounded text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              aria-label="Open sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
            <Link href="/" className="flex items-center gap-2">
              <div className="rounded bg-[#002B49] p-1.5 text-white shadow-sm">
                <Layers className="h-4 w-4" />
              </div>
              <span className="font-serif font-bold text-sm tracking-tight text-[#051C2C] dark:text-white">AI Consulting</span>
            </Link>
          </div>
          <UserMenu />
        </header>

        {/* Page Content */}
        <div className="flex-1 min-w-0">{children}</div>
      </div>
    </div>
  );
}

export default AppLayout;
