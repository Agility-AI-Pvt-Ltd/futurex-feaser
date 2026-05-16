"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/app/stores/authStore";
import { useSocketStore } from "@/app/stores/socketStore";
import { SERVER_EVENTS } from "@/app/lib/socket-events";
import type { LucideIcon } from "lucide-react";
import {
  Home,
  Users,
  Bookmark,
  MoreHorizontal,
  ChevronDown,
  ChevronUp,
  GraduationCap,
  LifeBuoy,
  Plus,
  BookOpen,
  Megaphone,
  ClipboardList,
  Trophy,
  Lightbulb,
  Bot,
} from "lucide-react";

interface SidebarCommunity {
  id: string;
  name: string;
  displayName: string;
  image: string | null;
  _count?: { members: number };
}

type NavItem = { href: string; label: string; icon: LucideIcon };

const DISCOVER_NAV: NavItem[] = [
  { href: "/communities", label: "Home", icon: Home },
  { href: "/communities/joined", label: "Communities", icon: Users },
];

const LEARN_NAV: NavItem[] = [
  { href: "/quiz", label: "Quizzes", icon: ClipboardList },
  { href: "/journal", label: "Journal", icon: BookOpen },
  { href: "/idea-lab", label: "Idea Lab", icon: Lightbulb },
  { href: "/ai-playground", label: "AI Playground", icon: Bot },
  { href: "/classcatchup", label: "ClassCatchup AI", icon: GraduationCap },
];

const PRIMARY_NAV_TAIL = [
  { href: "/bookmarks", label: "Saved", icon: Bookmark },
];

export function Sidebar() {
  const pathname = usePathname();
  const getToken = useAuthStore((s) => s.getToken);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);
  const [open, setOpen] = useState(false);
  const [showAllJoined, setShowAllJoined] = useState(false);
  const [joinedCommunities, setJoinedCommunities] = useState<
    SidebarCommunity[]
  >([]);
  const leaderboardHidden = useSocketStore((s) => s.leaderboardHidden);
  const setLeaderboardHidden = useSocketStore((s) => s.setLeaderboardHidden);

  // Announcements
  const [announcementUnread, setAnnouncementUnread] = useState(0);
  const socket = useSocketStore((s) => s.socket);
  const storeAnnouncementUnread = useSocketStore((s) => s.announcementUnread);
  const setStoreAnnouncementUnread = useSocketStore((s) => s.setAnnouncementUnread);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch("/api/announcements", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (typeof data.unreadCount === "number") {
          setAnnouncementUnread(data.unreadCount);
          setStoreAnnouncementUnread(data.unreadCount);
        }
      })
      .catch(() => {});
  }, [getToken, setStoreAnnouncementUnread]);

  useEffect(() => {
    if (!socket) return;
    const handler = () => {
      setAnnouncementUnread((c) => c + 1);
    };
    socket.on(SERVER_EVENTS.ANNOUNCEMENT, handler);
    return () => {
      socket.off(SERVER_EVENTS.ANNOUNCEMENT, handler);
    };
  }, [socket]);

  // Sync from store (e.g. after mark-read from /announcements page)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAnnouncementUnread(storeAnnouncementUnread);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [storeAnnouncementUnread]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch("/api/communities/joined", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setJoinedCommunities(data);
      })
      .catch(() => {});
  }, [getToken, isAuthenticated]);

  useEffect(() => {
    const token = getToken();
    if (!token || !isAuthenticated) return;
    fetch("/api/app/features", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (typeof data.leaderboardHidden === "boolean") {
          setLeaderboardHidden(data.leaderboardHidden);
        }
      })
      .catch(() => {});
  }, [getToken, isAuthenticated, setLeaderboardHidden]);

  const isActive = (href: string) => pathname === href;

  const visibleJoined = showAllJoined
    ? joinedCommunities
    : joinedCommunities.slice(0, 4);

  const showLeaderboardNav =
    isAuthenticated &&
    (user?.role === "ADMIN" || !leaderboardHidden);

  const activityNav: NavItem[] = [
    ...(showLeaderboardNav
      ? [{ href: "/leaderboard", label: "Leaderboard", icon: Trophy }]
      : []),
    { href: "/bookmarks", label: "Saved", icon: Bookmark },
  ];

  const sectionClass =
    "mb-2 px-3 text-[11px] font-semibold uppercase tracking-wide text-stone-500 dark:text-white/40";

  const renderNavLinks = (items: NavItem[]) =>
    items.map(({ href, label, icon: Icon }) => (
      <Link
        key={href + label}
        href={href}
        className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium transition ${
          isActive(href)
            ? "bg-[#E1C068] text-[#0d0d0d]"
            : "text-stone-700 hover:bg-stone-900/[0.04] hover:text-stone-900 dark:text-white/75 dark:hover:bg-white/6 dark:hover:text-white"
        }`}
      >
        <Icon
          size={18}
          className={
            isActive(href)
              ? "text-[#0d0d0d]"
              : "text-stone-500 group-hover:text-stone-700 dark:text-white/50 dark:group-hover:text-white/75"
          }
        />
        <span>{label}</span>
      </Link>
    ));

  return (
    <aside className="relative">
      {/* Mobile toggle */}
      <button
        type="button"
        className="mb-3 flex w-full items-center justify-between rounded-2xl border border-border bg-white px-3 py-2.5 text-[13px] font-medium text-stone-700 dark:bg-[#1a1a1a] dark:text-white/80 md:hidden"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Navigation</span>
        <span className="flex h-5 w-5 items-center justify-center rounded-lg border border-border">
          <MoreHorizontal size={12} />
        </span>
      </button>

      <div
        className={`md:static md:block ${
          open
            ? "absolute left-0 top-12 z-30 w-64"
            : "absolute left-0 top-12 hidden w-64 md:w-auto"
        }`}
      >
        <div className="space-y-1">
          {/* Pinned: Announcements */}
          {isAuthenticated && (
            <Link
              href="/announcements"
              className={`group mb-3 flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[13px] font-semibold transition ${
                pathname === "/announcements"
                  ? "border-[#E1C068]/60 bg-[#E1C068]/25 text-[#E1C068] shadow-[0_0_28px_rgba(225,192,104,0.42)] dark:border-[#E1C068]/50 dark:bg-[#E1C068]/22 dark:shadow-[0_0_32px_rgba(225,192,104,0.28)]"
                  : "border-[#E1C068]/45 bg-[#E1C068]/16 text-[#E1C068] hover:border-[#E1C068]/60 hover:bg-[#E1C068]/24 dark:border-[#E1C068]/40 dark:bg-[#E1C068]/14 dark:hover:border-[#E1C068]/55 dark:hover:bg-[#E1C068]/22"
              }`}
            >
              <Megaphone
                size={18}
                className={
                  pathname === "/announcements"
                    ? "text-[#E1C068] drop-shadow-[0_0_12px_rgba(225,192,104,0.75)]"
                    : "text-[#E1C068] drop-shadow-[0_0_6px_rgba(225,192,104,0.35)] group-hover:drop-shadow-[0_0_12px_rgba(225,192,104,0.55)]"
                }
              />
              <span className="min-w-0 flex-1 truncate">Announcements</span>
              {announcementUnread > 0 && (
                <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[#E1C068] px-1.5 text-[10px] font-black text-[#0d0d0d]">
                  {announcementUnread > 99 ? "99+" : announcementUnread}
                </span>
              )}
            </Link>
          )}

          <div className="mt-4 space-y-5">
            <div>
              <p className={sectionClass}>Discover</p>
              <nav className="space-y-0.5">{renderNavLinks(DISCOVER_NAV)}</nav>
            </div>
            <div>
              <p className={sectionClass}>Learn</p>
              <nav className="space-y-0.5">{renderNavLinks(LEARN_NAV)}</nav>
            </div>
            <div>
              <p className={sectionClass}>Activity</p>
              <nav className="space-y-0.5">{renderNavLinks(activityNav)}</nav>
            </div>
          </div>

          {/* Your Community section */}
          {isAuthenticated && joinedCommunities.length > 0 && (
            <div className="mt-6 pt-4 border-t border-border-muted">
              <div className="mb-2 flex items-center justify-between px-3">
                <p className="text-[11px] font-semibold text-stone-500 dark:text-white/40">
                  Your Community
                </p>
                <button
                  type="button"
                  className="flex h-5 w-5 items-center justify-center rounded-md text-stone-400 transition hover:bg-stone-900/[0.06] hover:text-stone-600 dark:text-white/30 dark:hover:bg-white/8 dark:hover:text-white/60"
                >
                  <Plus size={13} />
                </button>
              </div>
              <ul className="space-y-0.5">
                {visibleJoined.map((c) => (
                  <li key={c.id}>
                    <Link
                      href={`/communities/${c.id}`}
                      className={`flex items-center gap-3 rounded-xl px-3 py-2 text-[13px] font-medium transition ${
                        pathname === `/communities/${c.id}`
                          ? "bg-[#E1C068]/10 text-[#E1C068]"
                          : "text-stone-600 hover:bg-stone-900/[0.05] hover:text-stone-900 dark:text-white/65 dark:hover:bg-white/5 dark:hover:text-white/90"
                      }`}
                    >
                      {c.image ? (
                        <img
                          src={c.image}
                          alt=""
                          className="h-7 w-7 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#E1C068]/10 text-[11px] font-bold text-[#E1C068]">
                          {c.displayName.charAt(0)}
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <span className="block truncate">{c.displayName}</span>
                        {c._count?.members != null && (
                          <span className="block text-[10px] text-stone-500 dark:text-white/35">
                            {c._count.members.toLocaleString()} Members
                          </span>
                        )}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              {joinedCommunities.length > 4 && (
                <button
                  type="button"
                  onClick={() => setShowAllJoined((v) => !v)}
                  className="mt-1 flex w-full items-center gap-1 rounded-xl px-3 py-1.5 text-[12px] text-stone-500 transition hover:text-stone-700 dark:text-white/40 dark:hover:text-white/65"
                >
                  {showAllJoined ? (
                    <ChevronUp size={12} />
                  ) : (
                    <ChevronDown size={12} />
                  )}
                  {showAllJoined
                    ? "Show less"
                    : `+${joinedCommunities.length - 4} more`}
                </button>
              )}
            </div>
          )}

          {/* Bottom links */}
          <div className="mt-6 pt-4 border-t border-border-muted">
            <nav className="space-y-0.5">
              <Link
                href="/support"
                className="group flex items-center gap-3 rounded-xl px-3 py-2 text-[13px] text-stone-500 transition hover:bg-stone-900/[0.05] hover:text-stone-800 dark:text-white/50 dark:hover:bg-white/5 dark:hover:text-white/75"
              >
                <LifeBuoy
                  size={16}
                  className="text-stone-400 group-hover:text-stone-600 dark:text-white/35 dark:group-hover:text-white/55"
                />
                Help Center
              </Link>
            </nav>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
