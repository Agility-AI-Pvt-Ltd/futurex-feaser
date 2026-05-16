"use client";

import Link from "next/link";

export default function AdminSidebar() {
  return (
    <aside className="hidden w-64 shrink-0 pt-4 md:block">
      <div className="space-y-6 rounded-xl border border-[rgba(212,180,104,0.35)] bg-white dark:bg-[rgba(7,20,12,0.98)] p-4 text-xs text-stone-800 dark:text-white/80 shadow-md dark:shadow-[0_18px_60px_rgba(0,0,0,0.65)]">
        {/* Management */}
        <div>
          <p className="mb-2 text-[10px] font-semibold tracking-[0.28em] uppercase text-[#e3c777]/85">
            Management
          </p>
          <nav className="space-y-1">
            <Link
              href="/admin"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-800 dark:text-white/80 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Dashboard
            </Link>
            <Link
              href="/admin/cohort"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Cohort
            </Link>
            <Link
              href="/admin/communities"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Communities
            </Link>
            <Link
              href="/admin/users"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Users
            </Link>
            <Link
              href="/admin/chats"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Chats
            </Link>
            <Link
              href="/admin/moderation"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Journal moderation
            </Link>
            <Link
              href="/admin/spark-wall"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Spark Wall
            </Link>
            <Link
              href="/admin/consent"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Consent Forms
            </Link>
            <Link
              href="/admin/xp"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              XP Management
            </Link>
          </nav>
        </div>

        {/* AI */}
        <div>
          <p className="mb-2 text-[10px] font-semibold tracking-[0.28em] uppercase text-[#e3c777]/85">
            AI Tools
          </p>
          <nav className="space-y-1">
            <Link
              href="/admin/lecturebot"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/70 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Lecturebot Transcripts
            </Link>
          </nav>
        </div>

        {/* System */}
        <div>
          <p className="mb-2 text-[10px] font-semibold tracking-[0.28em] uppercase text-[#e3c777]/85">
            System
          </p>
          <nav className="space-y-1">
            <Link
              href="/admin/metrics"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/65 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Metrics
            </Link>
            <Link
              href="/admin/settings"
              className="block rounded px-2 py-1.5 text-[11px] tracking-[0.18em] uppercase text-stone-700 dark:text-white/65 transition hover:bg-stone-100 dark:hover:bg-white/5 hover:text-[#e3c777]"
            >
              Settings
            </Link>
          </nav>
        </div>
      </div>
    </aside>
  );
}

