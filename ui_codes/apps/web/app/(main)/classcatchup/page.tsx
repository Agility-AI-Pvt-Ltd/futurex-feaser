"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/app/stores/authStore";
import {
  BookOpen,
  Bot,
  ChevronRight,
  GraduationCap,
  Loader2,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Send,
  X,
} from "lucide-react";

/* ─── Types ─────────────────────────────────────────────────────────────────── */

interface TranscriptAsset {
  id: number;
  session_name: string;
  source_name: string;
  file_name: string;
  file_type: string;
  chunks_indexed: number;
  created_at: string;
  metadata_entry?: {
    course_name: string;
    instructor_name: string;
    session_date: string;
    description: string;
    tags: string;
  };
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

interface Conversation {
  id: string;         // local uuid
  sessionId: string;  // lecturebot session_id
  transcriptId: number | null;
  transcriptName: string;
  messages: ChatMessage[];
  createdAt: string;
}

interface SessionPayload {
  session_id: string;
  created_at?: string;
  transcript?: {
    id?: number | null;
    session_name?: string | null;
    source_name?: string | null;
  } | null;
  messages?: unknown[];
}

interface SessionsResponse {
  sessions: SessionPayload[];
  hasMore: boolean;
  limit: number;
  offset: number;
}

interface MessagePayload {
  role?: "user" | "assistant";
  content?: string;
  sources?: string[];
}

const CONVERSATIONS_PAGE_SIZE = 5;

/* ─── Helpers ────────────────────────────────────────────────────────────────── */

function renderInlineMarkdown(text: string) {
  return text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold text-white/92">{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  );
}

function MarkdownText({ text, className = "" }: { text: string; className?: string }) {
  const lines = text.replace(/```json|```/g, "").split("\n").map((l) => l.trim()).filter(Boolean);
  type Block =
    | { type: "heading"; text: string }
    | { type: "list"; items: string[] }
    | { type: "paragraph"; text: string };
  const blocks: Block[] = [];
  for (const line of lines) {
    if (line.startsWith("### ")) { blocks.push({ type: "heading", text: line.replace(/^###\s+/, "") }); continue; }
    const bullet = line.match(/^[-*]\s+(.*)$/)?.[1] || line.match(/^\d+\.\s+(.*)$/)?.[1];
    if (bullet) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "list") last.items.push(bullet);
      else blocks.push({ type: "list", items: [bullet] });
      continue;
    }
    blocks.push({ type: "paragraph", text: line });
  }
  return (
    <div className={`space-y-2 ${className}`}>
      {blocks.map((b, i) => {
        if (b.type === "heading") return <h4 key={i} className="text-[15px] font-semibold text-[#7DD3C8]">{renderInlineMarkdown(b.text)}</h4>;
        if (b.type === "list") return (
          <ul key={i} className="space-y-1 pl-5 text-[13px] leading-6 text-white/70">
            {b.items.map((item, j) => <li key={j} className="list-disc">{renderInlineMarkdown(item)}</li>)}
          </ul>
        );
        return <p key={i} className="text-[13px] leading-7 text-white/70">{renderInlineMarkdown(b.text)}</p>;
      })}
    </div>
  );
}

function normalizeMessages(payload: unknown): ChatMessage[] {
  if (!Array.isArray(payload)) return [];

  return payload.flatMap((item) => {
    if (!item || typeof item !== "object") return [];

    const message = item as MessagePayload;
    if (
      (message.role !== "user" && message.role !== "assistant") ||
      typeof message.content !== "string"
    ) {
      return [];
    }

    return [{
      role: message.role,
      content: message.content,
      sources: Array.isArray(message.sources) ? message.sources : [],
    }];
  });
}

function normalizeConversation(session: SessionPayload): Conversation {
  const sessionId = session.session_id;

  return {
    id: sessionId,
    sessionId,
    transcriptId: session.transcript?.id ?? null,
    transcriptName:
      session.transcript?.session_name ||
      session.transcript?.source_name ||
      "Unknown Session",
    messages: normalizeMessages(session.messages),
    createdAt: session.created_at || new Date().toISOString(),
  };
}

function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  if (incoming.length <= current.length) {
    return current;
  }

  return [...current, ...incoming.slice(current.length)];
}

function mergeConversation(current: Conversation, incoming: Conversation): Conversation {
  return {
    ...current,
    transcriptId: incoming.transcriptId ?? current.transcriptId,
    transcriptName: incoming.transcriptName || current.transcriptName,
    createdAt: incoming.createdAt || current.createdAt,
    messages: mergeMessages(current.messages, incoming.messages),
  };
}

function mergeConversationLists(
  current: Conversation[],
  incoming: Conversation[],
): Conversation[] {
  const currentBySessionId = new Map(
    current.map((conversation) => [conversation.sessionId, conversation]),
  );

  const merged = incoming.map((conversation) => {
    const existing = currentBySessionId.get(conversation.sessionId);
    return existing ? mergeConversation(existing, conversation) : conversation;
  });

  const seen = new Set(merged.map((conversation) => conversation.sessionId));
  const localOnly = current.filter(
    (conversation) => !seen.has(conversation.sessionId),
  );

  return [...merged, ...localOnly];
}

function appendConversationPage(
  current: Conversation[],
  incoming: Conversation[],
): Conversation[] {
  const next = [...current];
  const indexBySessionId = new Map(
    next.map((conversation, index) => [conversation.sessionId, index]),
  );

  for (const conversation of incoming) {
    const existingIndex = indexBySessionId.get(conversation.sessionId);
    if (existingIndex == null) {
      indexBySessionId.set(conversation.sessionId, next.length);
      next.push(conversation);
      continue;
    }

    next[existingIndex] = mergeConversation(next[existingIndex]!, conversation);
  }

  return next;
}

/* ─── Page ───────────────────────────────────────────────────────────────────── */

export default function ClassCatchupPage() {
  const getToken = useAuthStore((s) => s.getToken);

  const authHeaders = useCallback((): HeadersInit => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);

  /* state */
  const [transcripts, setTranscripts] = useState<TranscriptAsset[]>([]);
  const [loadingTranscripts, setLoadingTranscripts] = useState(true);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [loadedConversationCount, setLoadedConversationCount] = useState(0);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);

  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  /* transcript picker modal */
  const [showPicker, setShowPicker] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const loadedConversationCountRef = useRef(0);
  const activeConv = conversations.find((c) => c.id === activeConvId) ?? null;

  useEffect(() => {
    loadedConversationCountRef.current = loadedConversationCount;
  }, [loadedConversationCount]);

  /* auto-scroll */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConv?.messages.length]);

  const loadTranscripts = useCallback(async () => {
    try {
      const res = await fetch("/api/classcatchup/transcripts", {
        headers: authHeaders(),
      });
      const data = (await res.json()) as TranscriptAsset[] | { error?: string };
      if (!res.ok) {
        throw new Error((data as { error?: string }).error || "Failed");
      }
      setTranscripts(Array.isArray(data) ? data : []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [authHeaders]);

  const fetchConversationPage = useCallback(async (offset: number) => {
    const url = new URL("/api/classcatchup/sessions", window.location.origin);
    url.searchParams.set("limit", String(CONVERSATIONS_PAGE_SIZE));
    url.searchParams.set("offset", String(offset));

    const res = await fetch(url.toString(), {
      headers: authHeaders(),
    });
    const data = (await res.json()) as SessionsResponse | { error?: string };

    if (!res.ok) {
      throw new Error((data as { error?: string }).error || "Failed to load sessions");
    }

    if (!("sessions" in data) || !Array.isArray(data.sessions)) {
      return {
        sessions: [],
        hasMore: false,
        limit: CONVERSATIONS_PAGE_SIZE,
        offset,
      };
    }

    return data;
  }, [authHeaders]);

  const syncConversations = useCallback(async () => {
    const data = await fetchConversationPage(0);

    const normalized = data.sessions.map(normalizeConversation);
    setConversations((prev) => mergeConversationLists(prev, normalized));
    setHasMoreConversations((prev) =>
      loadedConversationCountRef.current > data.sessions.length ? prev : data.hasMore,
    );
    setLoadedConversationCount((prev) =>
      prev > 0 ? Math.max(prev, data.sessions.length) : data.sessions.length,
    );
  }, [fetchConversationPage]);

  const loadMoreConversations = useCallback(async () => {
    if (loadingConversations || loadingMoreConversations || !hasMoreConversations) {
      return;
    }

    setLoadingMoreConversations(true);
    try {
      const data = await fetchConversationPage(loadedConversationCountRef.current);
      const normalized = data.sessions.map(normalizeConversation);
      setConversations((prev) => appendConversationPage(prev, normalized));
      setHasMoreConversations(data.hasMore);
      setLoadedConversationCount((prev) => prev + data.sessions.length);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMoreConversations(false);
    }
  }, [
    fetchConversationPage,
    hasMoreConversations,
    loadingConversations,
    loadingMoreConversations,
  ]);

  const syncActiveMessages = useCallback(async (sessionId: string) => {
    const res = await fetch(
      `/api/classcatchup/sessions/${encodeURIComponent(sessionId)}/messages`,
      { headers: authHeaders() },
    );
    const data = (await res.json()) as unknown;

    if (!res.ok) {
      const errorPayload = data as { error?: string };
      throw new Error(errorPayload.error || "Failed to load messages");
    }

    const messages = normalizeMessages(
      Array.isArray(data)
        ? data
        : typeof data === "object" && data !== null && "messages" in data
          ? (data as { messages?: unknown[] }).messages
          : [],
    );

    setConversations((prev) =>
      prev.map((conversation) =>
        conversation.sessionId === sessionId
          ? { ...conversation, messages: mergeMessages(conversation.messages, messages) }
          : conversation,
      ),
    );
  }, [authHeaders]);

  /* load transcripts once */
  useEffect(() => {
    void (async () => {
      setLoadingTranscripts(true);
      try {
        await loadTranscripts();
      } finally {
        setLoadingTranscripts(false);
      }
    })();
  }, [loadTranscripts]);

  /* load and incrementally sync past conversations */
  useEffect(() => {
    void (async () => {
      setLoadingConversations(true);
      try {
        loadedConversationCountRef.current = 0;
        setLoadedConversationCount(0);
        await syncConversations();
      } catch (e) {
        console.error("Failed to load previous sessions:", e);
      } finally {
        setLoadingConversations(false);
      }
    })();
  }, [syncConversations]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void syncConversations().catch((e) => {
        console.error("Failed to sync sessions:", e);
      });
    }, 10000);

    return () => window.clearInterval(interval);
  }, [syncConversations]);

  useEffect(() => {
    if (!activeConv?.sessionId) return;

    const initialSync = window.setTimeout(() => {
      void syncActiveMessages(activeConv.sessionId).catch((e) => {
        console.error("Failed to sync active messages:", e);
      });
    }, 0);

    const interval = window.setInterval(() => {
      void syncActiveMessages(activeConv.sessionId).catch((e) => {
        console.error("Failed to sync active messages:", e);
      });
    }, 3000);

    return () => {
      window.clearTimeout(initialSync);
      window.clearInterval(interval);
    };
  }, [activeConv?.sessionId, syncActiveMessages]);

  /* start a new conversation with chosen transcript */
  function startConversation(transcript: TranscriptAsset) {
    const sessionId = crypto.randomUUID();
    const conv: Conversation = {
      id: sessionId,
      sessionId,
      transcriptId: transcript.id,
      transcriptName: transcript.session_name || transcript.source_name,
      messages: [],
      createdAt: new Date().toISOString(),
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveConvId(conv.id);
    setShowPicker(false);
    setSidebarOpen(false);
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() || !activeConv || sending) return;
    setError(null);
    const userMsg = message.trim();
    setMessage("");

    /* optimistic add */
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeConvId
          ? { ...c, messages: [...c.messages, { role: "user", content: userMsg }] }
          : c,
      ),
    );

    setSending(true);
    try {
      const res = await fetch("/api/classcatchup/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          session_id: activeConv.sessionId,
          message: userMsg,
          transcript_id: activeConv.transcriptId,
        }),
      });
      const data = (await res.json()) as { answer?: string; sources?: string[]; error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to get answer");

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConvId
            ? {
                ...c,
                messages:
                  c.messages.at(-1)?.role === "assistant" &&
                  c.messages.at(-1)?.content === (data.answer || "No answer.")
                    ? c.messages
                    : [
                        ...c.messages,
                        {
                          role: "assistant",
                          content: data.answer || "No answer.",
                          sources: data.sources,
                        },
                      ],
              }
            : c,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  /* ─── Render ─────────────────────────────────────────────────────────────── */

  return (
    <div
      className={`grid gap-4 transition-all duration-300 ${
        sidebarOpen
          ? "xl:grid-cols-[280px_minmax(0,1fr)]"
          : "xl:grid-cols-[72px_minmax(0,1fr)]"
      }`}
    >
      {/* ── Sidebar ── */}
      <aside className="rounded-3xl border border-white/[0.07] bg-[#171717] p-4 transition-all duration-300">
        {sidebarOpen ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#7DD3C8]/70">
                  ClassCatchup AI
                </p>
                <h1 className="mt-2 text-xl font-black text-white">Conversations</h1>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowPicker(true)}
                  className="inline-flex items-center gap-2 rounded-full border border-[#7DD3C8]/25 bg-[#7DD3C8]/10 px-3 py-2 text-[12px] font-semibold text-[#7DD3C8] transition hover:bg-[#7DD3C8]/18"
                >
                  <Plus size={14} />
                  New
                </button>
                <button
                  type="button"
                  onClick={() => setSidebarOpen(false)}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] bg-[#111111] text-white/55 transition hover:border-[#7DD3C8]/25 hover:text-[#7DD3C8]"
                  aria-label="Close sidebar"
                >
                  <PanelLeftClose size={16} />
                </button>
              </div>
            </div>

            <div className="mt-4 rounded-2xl border border-[#7DD3C8]/12 bg-[#111111] p-3">
              <div className="flex items-center gap-2 text-[#7DD3C8]">
                <MessageSquare size={15} />
                <p className="text-[12px] font-semibold">Conversations</p>
              </div>
              <div className="mt-3 space-y-2">
                {loadingConversations ? (
                  <div className="flex items-center justify-center py-6 text-[#7DD3C8]">
                    <Loader2 size={18} className="animate-spin" />
                  </div>
                ) : conversations.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-white/10 px-3 py-6 text-center text-[12px] text-white/35">
                    Start a new conversation to catch up on a session.
                  </p>
                ) : (
                  conversations.map((conv) => (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => { setActiveConvId(conv.id); setSidebarOpen(false); }}
                      className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                        activeConvId === conv.id
                          ? "border-[#7DD3C8]/40 bg-[#7DD3C8]/12"
                          : "border-white/[0.06] bg-white/[0.02] hover:border-[#7DD3C8]/18 hover:bg-white/[0.04]"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <BookOpen size={13} className="mt-0.5 shrink-0 text-[#7DD3C8]/70" />
                        <div className="min-w-0">
                          <p className="truncate text-[13px] font-semibold text-white/90">
                            {conv.transcriptName}
                          </p>
                          <p className="mt-0.5 text-[11px] text-white/38">
                            {conv.messages.length} messages · {new Date(conv.createdAt).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
              {!loadingConversations && conversations.length > 0 && (
                <div className="mt-3 border-t border-white/[0.06] pt-3">
                  <p className="text-center text-[11px] text-white/35">
                    Showing {conversations.length} conversation
                    {conversations.length === 1 ? "" : "s"}
                  </p>
                  {hasMoreConversations ? (
                    <button
                      type="button"
                      onClick={() => {
                        void loadMoreConversations();
                      }}
                      disabled={loadingMoreConversations}
                      className="mt-3 inline-flex min-h-[38px] w-full items-center justify-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-[12px] font-semibold text-white/85 transition hover:border-[#7DD3C8]/30 hover:bg-[#7DD3C8]/10 disabled:opacity-60"
                    >
                      {loadingMoreConversations ? (
                        <>
                          <Loader2 size={14} className="animate-spin text-[#7DD3C8]" />
                          Loading…
                        </>
                      ) : (
                        "Load more conversations"
                      )}
                    </button>
                  ) : (
                    <p className="mt-3 text-center text-[11px] text-white/25">
                      End of conversations
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex h-full flex-col items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-[#7DD3C8]/25 bg-[#7DD3C8]/10 text-[#7DD3C8] transition hover:bg-[#7DD3C8]/18"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen size={18} />
            </button>
            <button
              type="button"
              onClick={() => setShowPicker(true)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/[0.08] bg-[#111111] text-white/65 transition hover:border-[#7DD3C8]/25 hover:text-[#7DD3C8]"
              aria-label="New conversation"
              title="New conversation"
            >
              <Plus size={16} />
            </button>
            <div className="mt-2 flex w-full flex-1 flex-col items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#7DD3C8]/10 text-[#7DD3C8]">
                <GraduationCap size={18} />
              </div>
              <div className="h-full w-px bg-gradient-to-b from-[#7DD3C8]/20 via-white/8 to-transparent" />
            </div>
          </div>
        )}
      </aside>

      {/* ── Main workspace ── */}
      <section 
        className="flex flex-col gap-4"
        onClick={() => sidebarOpen && setSidebarOpen(false)}
      >
        {error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-[13px] text-red-200 flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}

        {/* Chat area */}
        {!activeConv ? (
          /* ── Empty state (Merged with Header) ── */
          <div className="flex flex-col rounded-3xl border border-[#7DD3C8]/16 bg-[#171717] px-8 py-12 text-center">
             <div className="flex flex-col items-center justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#7DD3C8]/14 text-[#7DD3C8]">
                <GraduationCap size={28} />
              </div>
              <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#7DD3C8]/70">
                AI-Powered Learning
              </p>
              <h2 className="mt-2 text-2xl font-black text-white">ClassCatchup AI</h2>
              <p className="mt-2 max-w-sm text-[13px] leading-6 text-white/48">
                Select a lecture session, then ask anything — the AI answers grounded in the actual class transcript.
              </p>
              
              <div className="mt-8 border-t border-white/[0.06] pt-8 w-full max-w-md">
                 <h3 className="text-[18px] font-bold text-white">No session selected</h3>
                  <p className="mt-2 text-[13px] leading-6 text-white/40">
                    Start a new conversation by picking one of the uploaded lecture sessions.
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowPicker(true)}
                    className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#7DD3C8] px-6 py-3 text-[13px] font-bold text-[#0d0d0d] transition hover:bg-[#9de2d8]"
                  >
                    <Plus size={15} />
                    Pick a session
                  </button>
              </div>
            </div>
          </div>
        ) : (
          /* ── Active conversation ── */
          <div className="flex flex-1 flex-col rounded-3xl border border-white/[0.07] bg-[#171717] overflow-hidden" style={{ minHeight: 520 }}>
            {/* conv header */}
            <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#7DD3C8]/14 text-[#7DD3C8]">
                <BookOpen size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-semibold text-white/90">{activeConv.transcriptName}</p>
                <p className="text-[11px] text-white/38">{activeConv.messages.length} messages in this session</p>
              </div>
              <button
                type="button"
                onClick={() => setShowPicker(true)}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#7DD3C8]/25 bg-[#7DD3C8]/10 px-3 py-1.5 text-[11px] font-semibold text-[#7DD3C8] transition hover:bg-[#7DD3C8]/18"
              >
                <Plus size={11} />
                New session
              </button>
            </div>

            {/* messages */}
            <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
              {activeConv.messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <Bot size={32} className="text-[#7DD3C8]/40" />
                  <p className="mt-4 text-[13px] text-white/35">
                    Ask anything about <span className="text-white/60 font-medium">{activeConv.transcriptName}</span>
                  </p>
                </div>
              ) : (
                activeConv.messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.role === "assistant" && (
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#7DD3C8]/14 text-[#7DD3C8] mt-0.5">
                        <Bot size={15} />
                      </div>
                    )}
                    <div
                      className={`max-w-[78%] rounded-2xl px-4 py-3 ${
                        msg.role === "user"
                          ? "rounded-tr-sm bg-[#7DD3C8]/15 border border-[#7DD3C8]/20"
                          : "rounded-tl-sm bg-[#111111] border border-white/[0.06]"
                      }`}
                    >
                      {msg.role === "user" ? (
                        <p className="text-[13px] leading-6 text-white/88">{msg.content}</p>
                      ) : (
                        <MarkdownText text={msg.content} />
                      )}
                      {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/[0.06] pt-3">
                          {msg.sources.map((src, si) => (
                            <span
                              key={si}
                              className="rounded-full border border-[#7DD3C8]/20 bg-[#7DD3C8]/8 px-2.5 py-0.5 text-[10px] text-[#7DD3C8]/75"
                            >
                              {src}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    {msg.role === "user" && (
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-white/50 mt-0.5">
                        <span className="text-[11px] font-bold">You</span>
                      </div>
                    )}
                  </div>
                ))
              )}
              {sending && (
                <div className="flex gap-3 justify-start">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#7DD3C8]/14 text-[#7DD3C8]">
                    <Bot size={15} />
                  </div>
                  <div className="rounded-2xl rounded-tl-sm bg-[#111111] border border-white/[0.06] px-4 py-3">
                    <div className="flex items-center gap-2 text-[#7DD3C8]/60">
                      <Loader2 size={14} className="animate-spin" />
                      <span className="text-[12px]">Thinking…</span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* input */}
            <div className="border-t border-white/[0.06] px-5 py-4">
              <form onSubmit={handleSend} className="flex gap-3">
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={`Ask about "${activeConv.transcriptName}"…`}
                  disabled={sending}
                  className="min-w-0 flex-1 rounded-full border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#7DD3C8]/35 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={sending || !message.trim()}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#7DD3C8] text-[#0d0d0d] transition hover:bg-[#9de2d8] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </form>
            </div>
          </div>
        )}
      </section>

      {/* ── Transcript picker modal ── */}
      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-3xl border border-white/[0.09] bg-[#1a1a1a] p-6 shadow-2xl">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#7DD3C8]/70">Step 1</p>
                <h2 className="mt-1 text-[18px] font-black text-white">Choose a Lecture Session</h2>
              </div>
              <button
                type="button"
                onClick={() => setShowPicker(false)}
                className="flex h-9 w-9 items-center justify-center rounded-full border border-white/[0.08] bg-[#111111] text-white/50 transition hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="mt-5 max-h-[420px] overflow-y-auto space-y-2 pr-1">
              {loadingTranscripts ? (
                <div className="flex items-center justify-center py-12 text-[#7DD3C8]">
                  <Loader2 size={22} className="animate-spin" />
                </div>
              ) : transcripts.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 px-4 py-10 text-center">
                  <BookOpen size={28} className="mx-auto text-white/20" />
                  <p className="mt-3 text-[13px] text-white/40">No lecture sessions uploaded yet.</p>
                  <p className="mt-1 text-[12px] text-white/25">Ask your instructor to upload transcripts.</p>
                </div>
              ) : (
                transcripts.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => startConversation(t)}
                    className="group w-full rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 py-4 text-left transition hover:border-[#7DD3C8]/30 hover:bg-[#7DD3C8]/8"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#7DD3C8]/10 text-[#7DD3C8] transition group-hover:bg-[#7DD3C8]/16">
                        <BookOpen size={17} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-semibold text-white/90 group-hover:text-white">
                          {t.session_name}
                        </p>
                        <p className="mt-0.5 truncate text-[12px] text-white/40">{t.source_name}</p>
                        {t.metadata_entry?.course_name && (
                          <p className="mt-1 text-[11px] text-[#7DD3C8]/60">
                            {t.metadata_entry.course_name}
                            {t.metadata_entry.instructor_name && ` · ${t.metadata_entry.instructor_name}`}
                          </p>
                        )}
                        <div className="mt-2 flex items-center gap-3 text-[11px] text-white/30">
                          <span>{t.chunks_indexed} chunks indexed</span>
                          <span>·</span>
                          <span>{new Date(t.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <ChevronRight size={16} className="mt-1 shrink-0 text-white/20 transition group-hover:text-[#7DD3C8]/60" />
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
