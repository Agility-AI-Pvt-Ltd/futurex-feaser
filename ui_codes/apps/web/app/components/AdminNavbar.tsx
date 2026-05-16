"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Menu, X } from "lucide-react";

export default function AdminNavbar() {
  const pathname = usePathname();
  const menuId = useId();
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const navLinks = [
    { href: "/admin", label: "Overview" },
    { href: "/admin/cohort", label: "Cohort" },
    { href: "/admin/communities", label: "Communities" },
    { href: "/admin/users", label: "Users" },
    { href: "/admin/chats", label: "Chats" },
    { href: "/admin/moderation", label: "Journal moderation" },
    { href: "/admin/spark-wall", label: "Spark Wall" },
    { href: "/admin/consent", label: "Consent Data" },
    { href: "/admin/quiz", label: "Quizzes" },
    { href: "/admin/lecturebot", label: "Lecturebot" },
  ];

  const closeMenu = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    closeMenu();
  }, [pathname, closeMenu]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMenu();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen, closeMenu]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (panelRef.current?.contains(t)) return;
      if (closeBtnRef.current?.contains(t)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [mobileOpen, closeMenu]);

  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-stone-200 bg-white/95 backdrop-blur dark:border-[rgba(212,180,104,0.3)] dark:bg-[rgba(5,18,11,0.98)]/95">
      <div className="relative">
        <div className="flex h-14 w-full min-w-0 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
          {/* Brand */}
          <Link
            href="/admin"
            className="flex min-w-0 shrink items-baseline gap-2 text-xs font-semibold tracking-[0.26em] text-[#e3c777]"
            onClick={closeMenu}
          >
            <span className="truncate font-serif text-sm font-black tracking-[0.28em] text-[#e3c777] drop-shadow-[0_0_18px_rgba(198,167,94,0.4)]">
              FutureX
            </span>
            <span className="hidden truncate text-[9px] font-semibold tracking-[0.36em] text-stone-600 dark:text-white/70 sm:inline">
              Admin Console
            </span>
          </Link>

          {/* Primary admin nav — xl and up */}
          <nav
            className="hidden min-w-0 flex-1 items-center justify-center gap-4 text-[10px] font-semibold uppercase tracking-[0.24em] xl:flex xl:gap-6"
            aria-label="Admin primary"
          >
            {navLinks.map(({ href, label }) => {
              const active =
                href === "/admin"
                  ? pathname === "/admin"
                  : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`relative shrink-0 transition ${active ? "text-[#e3c777]" : "text-stone-600 hover:text-[#e3c777] dark:text-white/50"}`}
                >
                  {label}
                  {active && (
                    <span className="absolute -bottom-px inset-x-0 h-px bg-[#e3c777] opacity-70" />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Right actions */}
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <Link
              href="/"
              className="rounded-full border border-[rgba(212,180,104,0.45)] bg-stone-50 px-2.5 py-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-[#b8860b] shadow-sm transition hover:border-[rgba(227,199,119,0.9)] hover:text-[#a67c00] dark:bg-[rgba(12,30,20,0.9)] dark:text-[#e3c777] dark:shadow-[0_0_12px_rgba(227,199,119,0.35)] dark:hover:text-[#f5e5a4] sm:px-3 sm:text-[10px] sm:tracking-[0.22em]"
            >
              ← Back
            </Link>

            <div className="hidden items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-emerald-300/80 xl:flex">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]" />
              </span>
              <span>Admin</span>
            </div>

            <button
              ref={closeBtnRef}
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-stone-200 text-stone-700 transition hover:bg-stone-100 dark:border-[rgba(212,180,104,0.35)] dark:text-[#e3c777] dark:hover:bg-white/5 xl:hidden"
              aria-expanded={mobileOpen}
              aria-controls={menuId}
              aria-label={mobileOpen ? "Close admin menu" : "Open admin menu"}
              onClick={() => setMobileOpen((o) => !o)}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {/* Mobile / tablet menu — below xl */}
        {mobileOpen ? (
          <>
            <div
              className="fixed inset-0 top-14 z-40 bg-black/40 xl:hidden"
              aria-hidden
            />
            <div
              ref={panelRef}
              id={menuId}
              className="absolute left-0 right-0 top-full z-50 max-h-[min(70vh,calc(100dvh-3.5rem))] overflow-y-auto border-b border-stone-200 bg-white shadow-lg dark:border-[rgba(212,180,104,0.25)] dark:bg-[rgba(7,20,12,0.98)] xl:hidden"
              role="navigation"
              aria-label="Admin menu"
            >
              <nav className="flex flex-col px-2 py-2">
                {navLinks.map(({ href, label }) => {
                  const active =
                    href === "/admin"
                      ? pathname === "/admin"
                      : pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={closeMenu}
                      className={`rounded-lg px-3 py-2.5 text-[12px] font-semibold uppercase tracking-[0.18em] transition ${
                        active
                          ? "bg-[#E1C068]/20 text-[#a67c00] dark:bg-[#E1C068]/10 dark:text-[#e3c777]"
                          : "text-stone-700 hover:bg-stone-100 dark:text-white/75 dark:hover:bg-white/5"
                      }`}
                    >
                      {label}
                    </Link>
                  );
                })}
              </nav>
              <div className="flex items-center gap-2 border-t border-stone-200 px-4 py-3 text-[10px] font-medium uppercase tracking-[0.2em] text-emerald-600/90 dark:border-white/10 dark:text-emerald-300/80">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]" />
                </span>
                <span>Admin session</span>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </header>
  );
}
