"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/app/stores/authStore";
import {
  Bot,
  FlaskConical,
  Lightbulb,
  Loader2,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  SearchCheck,
  Send,
  Sparkles,
} from "lucide-react";

interface HistoryItem {
  conversation_id: string;
  idea: string;
  timestamp: string;
  user_name: string;
}

interface IdeaLabChatResponse {
  response: string;
  conversation_id: string;
  analysis: string | null;
}

interface IdeaLabQaResponse {
  answer: string;
}

interface ConversationDetail {
  conversation_id: string;
  idea: string;
  user_name: string;
  ideal_customer: string;
  problem_solved: string;
  analysis: string | null;
  qa_history: Array<{ q?: string; a?: string }>;
}

interface ReportData {
  chain_of_thought?: string[];
  idea_fit?: string;
  competitors?: string;
  opportunity?: string;
  score?: string;
  targeting?: string;
  next_step?: string;
}

function parseReport(raw: string | null): ReportData | null {
  if (!raw?.trim()) return null;
  try {
    return JSON.parse(raw.replace(/```json|```/g, "").trim()) as ReportData;
  } catch {
    return null;
  }
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={`${part}-${index}`} className="font-semibold text-white/92">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

function MarkdownLikeText({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  const lines = text
    .replace(/```json|```/g, "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const blocks: Array<
    | { type: "heading"; text: string }
    | { type: "list"; items: string[] }
    | { type: "paragraph"; text: string }
  > = [];

  for (const line of lines) {
    if (line.startsWith("### ")) {
      blocks.push({ type: "heading", text: line.replace(/^###\s+/, "") });
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.*)$/);
    const numberedMatch = line.match(/^\d+\.\s+(.*)$/);
    const listItem = bulletMatch?.[1] || numberedMatch?.[1];

    if (listItem) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "list") {
        last.items.push(listItem);
      } else {
        blocks.push({ type: "list", items: [listItem] });
      }
      continue;
    }

    blocks.push({ type: "paragraph", text: line });
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <h4
              key={`${block.text}-${index}`}
              className="text-[16px] font-semibold text-[#E1C068]"
            >
              {renderInlineMarkdown(block.text)}
            </h4>
          );
        }

        if (block.type === "list") {
          return (
            <ul
              key={`${block.items.join("-")}-${index}`}
              className="space-y-2 pl-5 text-[13px] leading-6 text-white/68"
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`} className="list-disc">
                  {renderInlineMarkdown(item)}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p
            key={`${block.text}-${index}`}
            className="text-[13px] leading-7 text-white/68"
          >
            {renderInlineMarkdown(block.text)}
          </p>
        );
      })}
    </div>
  );
}

/** Full Idea Lab UI — wire this back as `page.tsx` default export when Idea Lab launches. */
export function IdeaLabFullPage() {
  const user = useAuthStore((s) => s.user);
  const getToken = useAuthStore((s) => s.getToken);

  const [idea, setIdea] = useState("");
  const [idealCustomer, setIdealCustomer] = useState("");
  const [problemSolved, setProblemSolved] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [qaQuestion, setQaQuestion] = useState("");

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [clarifyingQuestion, setClarifyingQuestion] = useState<string | null>(null);
  const [analysisRaw, setAnalysisRaw] = useState<string | null>(null);
  const [qaHistory, setQaHistory] = useState<Array<{ q: string; a: string }>>([]);

  const [loadingHistory, setLoadingHistory] = useState(true);
  const [submittingIdea, setSubmittingIdea] = useState(false);
  const [submittingClarification, setSubmittingClarification] = useState(false);
  const [submittingQa, setSubmittingQa] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const report = useMemo(() => parseReport(analysisRaw), [analysisRaw]);
  const hasFinalReport = Boolean(report);

  const authHeaders = useCallback((): HeadersInit => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch("/api/idea-lab/history", {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load Idea Lab history");
      setHistory(Array.isArray(data) ? data : []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingHistory(false);
    }
  }, [authHeaders]);

  const loadConversation = useCallback(
    async (id: string) => {
      setLoadingConversation(true);
      setLoadingConversationId(id);
      setError(null);
      try {
        const res = await fetch(`/api/idea-lab/history/${encodeURIComponent(id)}`, {
          headers: authHeaders(),
        });
        const data = (await res.json()) as ConversationDetail & { error?: string };
        if (!res.ok) throw new Error(data.error || "Failed to load conversation");

        setConversationId(data.conversation_id);
        setIdea(data.idea || "");
        setIdealCustomer(data.ideal_customer || "");
        setProblemSolved(data.problem_solved || "");
        setAnalysisRaw(data.analysis || null);
        const parsed = parseReport(data.analysis || null);
        setClarifyingQuestion(parsed ? null : data.analysis || null);
        setQaHistory(
          Array.isArray(data.qa_history)
            ? data.qa_history
                .filter((item) => item.q && item.a)
                .map((item) => ({ q: item.q || "", a: item.a || "" }))
            : [],
        );
        setClarificationAnswer("");
        setQaQuestion("");
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoadingConversation(false);
        setLoadingConversationId(null);
      }
    },
    [authHeaders],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadHistory();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadHistory]);

  async function handleIdeaSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmittingIdea(true);
    setError(null);
    try {
      const res = await fetch("/api/idea-lab/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          idea,
          user_name: user?.name || user?.username || user?.email || "Founder",
          ideal_customer: idealCustomer,
          problem_solved: problemSolved,
          conversation_id: null,
        }),
      });
      const data = (await res.json()) as IdeaLabChatResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to analyze idea");

      setConversationId(data.conversation_id);
      setClarifyingQuestion(data.analysis);
      setAnalysisRaw(null);
      setQaHistory([]);
      setClarificationAnswer("");
      await loadHistory();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmittingIdea(false);
    }
  }

  async function handleClarificationSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!conversationId) return;
    setSubmittingClarification(true);
    setError(null);
    try {
      const res = await fetch("/api/idea-lab/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          idea: clarificationAnswer,
          user_name: user?.name || user?.username || user?.email || "Founder",
          ideal_customer: idealCustomer,
          problem_solved: problemSolved,
          conversation_id: conversationId,
        }),
      });
      const data = (await res.json()) as IdeaLabChatResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to complete analysis");
      setAnalysisRaw(data.analysis);
      setClarifyingQuestion(null);
      setClarificationAnswer("");
      await loadHistory();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmittingClarification(false);
    }
  }

  async function handleQaSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!conversationId || !qaQuestion.trim()) return;
    setSubmittingQa(true);
    setError(null);
    try {
      const res = await fetch("/api/idea-lab/qa", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          question: qaQuestion,
        }),
      });
      const data = (await res.json()) as IdeaLabQaResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to answer question");
      setQaHistory((prev) => [...prev, { q: qaQuestion, a: data.answer }]);
      setQaQuestion("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmittingQa(false);
    }
  }

  function resetComposer() {
    setConversationId(null);
    setIdea("");
    setIdealCustomer("");
    setProblemSolved("");
    setClarifyingQuestion(null);
    setClarificationAnswer("");
    setAnalysisRaw(null);
    setQaHistory([]);
    setQaQuestion("");
    setError(null);
  }

  function collapseSidebarForWorkspace() {
    setSidebarOpen(false);
  }

  return (
    <div
      className={`grid gap-4 transition-all duration-300 ${
        sidebarOpen
          ? "xl:grid-cols-[280px_minmax(0,1fr)]"
          : "xl:grid-cols-[72px_minmax(0,1fr)]"
      }`}
    >
      <aside className="rounded-3xl border border-white/[0.07] bg-[#171717] p-4 transition-all duration-300">
        {sidebarOpen ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#E1C068]/70">
                  Idea Lab
                </p>
                <h1 className="mt-2 text-xl font-black text-white">Research Workspace</h1>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={resetComposer}
                  className="inline-flex items-center gap-2 rounded-full border border-[#E1C068]/25 bg-[#E1C068]/10 px-3 py-2 text-[12px] font-semibold text-[#E1C068] transition hover:bg-[#E1C068]/16"
                >
                  <Plus size={14} />
                  New
                </button>
                <button
                  type="button"
                  onClick={() => setSidebarOpen(false)}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] bg-[#111111] text-white/55 transition hover:border-[#E1C068]/25 hover:text-[#E1C068]"
                  aria-label="Close sidebar"
                  title="Close sidebar"
                >
                  <PanelLeftClose size={16} />
                </button>
              </div>
            </div>

            <div className="mt-4 rounded-2xl border border-[#E1C068]/12 bg-[#111111] p-3">
              <div className="flex items-center gap-2 text-[#E1C068]">
                <FlaskConical size={15} />
                <p className="text-[12px] font-semibold">Saved Analyses</p>
              </div>
              <div className="mt-3 space-y-2">
                {loadingHistory ? (
                  <div className="flex items-center justify-center py-8 text-white/45">
                    <Loader2 size={18} className="animate-spin" />
                  </div>
                ) : history.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-white/10 px-3 py-6 text-center text-[12px] text-white/35">
                    Your Idea Lab conversations will appear here.
                  </p>
                ) : (
                  history.map((item) => (
                    <button
                      key={item.conversation_id}
                      type="button"
                      onClick={() => void loadConversation(item.conversation_id)}
                      disabled={loadingConversation}
                      className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                        conversationId === item.conversation_id
                          ? "border-[#E1C068]/40 bg-[#E1C068]/12"
                          : "border-white/[0.06] bg-white/[0.02] hover:border-[#E1C068]/18 hover:bg-white/[0.04]"
                      } ${loadingConversation ? "cursor-wait" : ""} ${
                        loadingConversationId === item.conversation_id
                          ? "opacity-90"
                          : ""
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-semibold text-white/90">
                            {item.idea}
                          </p>
                          <p className="mt-1 text-[11px] text-white/40">
                            {new Date(item.timestamp).toLocaleString()}
                          </p>
                        </div>
                        {loadingConversationId === item.conversation_id && (
                          <Loader2
                            size={15}
                            className="mt-0.5 shrink-0 animate-spin text-[#E1C068]"
                          />
                        )}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full flex-col items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-[#E1C068]/25 bg-[#E1C068]/10 text-[#E1C068] transition hover:bg-[#E1C068]/16"
              aria-label="Open sidebar"
              title="Open sidebar"
            >
              <PanelLeftOpen size={18} />
            </button>
            <button
              type="button"
              onClick={resetComposer}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/[0.08] bg-[#111111] text-white/65 transition hover:border-[#E1C068]/25 hover:text-[#E1C068]"
              aria-label="New analysis"
              title="New analysis"
            >
              <Plus size={16} />
            </button>
            <div className="mt-2 flex w-full flex-1 flex-col items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#E1C068]/10 text-[#E1C068]">
                <FlaskConical size={18} />
              </div>
              <div className="h-full w-px bg-gradient-to-b from-[#E1C068]/20 via-white/8 to-transparent" />
            </div>
          </div>
        )}
      </aside>

      <section
        className="space-y-4"
        onPointerDown={collapseSidebarForWorkspace}
        onFocusCapture={collapseSidebarForWorkspace}
      >
        <div className="rounded-3xl border border-[#E1C068]/16 bg-[#171717] p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#E1C068]/14 text-[#E1C068]">
              <Lightbulb size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#E1C068]/70">
                Founder Research
              </p>
              <h2 className="mt-2 text-2xl font-black text-white">
                Turn an idea into a feasibility brief
              </h2>
              <p className="mt-2 max-w-3xl text-[13px] leading-6 text-white/48">
                Submit the idea, answer one clarification question, then keep asking follow-up questions against the generated report.
              </p>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-[13px] text-red-200">
            {error}
          </div>
        )}

        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
          <div className="space-y-4">
            {loadingConversation && (
              <div className="rounded-3xl border border-[#E1C068]/18 bg-[#171717] p-5">
                <div className="flex items-center gap-3 text-[#E1C068]">
                  <Loader2 size={18} className="animate-spin" />
                  <div>
                    <p className="text-[13px] font-semibold">Loading saved analysis</p>
                    <p className="text-[12px] text-white/40">
                      Fetching idea details and report content...
                    </p>
                  </div>
                </div>
              </div>
            )}

            <form
              onSubmit={handleIdeaSubmit}
              className="rounded-3xl border border-white/[0.07] bg-[#171717] p-5"
            >
              <div className="flex items-center gap-2 text-white/80">
                <Sparkles size={16} className="text-[#E1C068]" />
                <h3 className="text-[15px] font-semibold">Start a New Analysis</h3>
              </div>

              <div className="mt-4 space-y-4">
                <label className="block">
                  <span className="mb-2 block text-[12px] font-medium text-white/55">
                    Startup idea
                  </span>
                  <textarea
                    value={idea}
                    onChange={(e) => setIdea(e.target.value)}
                    placeholder="Example: AI mentor for student founders building their first venture."
                    rows={4}
                    className="w-full rounded-2xl border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                    required
                  />
                </label>

                <div className="grid gap-4 md:grid-cols-2">
                  <label className="block">
                    <span className="mb-2 block text-[12px] font-medium text-white/55">
                      Ideal customer
                    </span>
                    <textarea
                      value={idealCustomer}
                      onChange={(e) => setIdealCustomer(e.target.value)}
                      rows={3}
                      className="w-full rounded-2xl border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                      required
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-[12px] font-medium text-white/55">
                      Problem solved
                    </span>
                    <textarea
                      value={problemSolved}
                      onChange={(e) => setProblemSolved(e.target.value)}
                      rows={3}
                      className="w-full rounded-2xl border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                      required
                    />
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={submittingIdea}
                  className="inline-flex items-center gap-2 rounded-full bg-[#E1C068] px-5 py-3 text-[13px] font-bold text-[#0d0d0d] transition hover:bg-[#ecd078] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {submittingIdea ? <Loader2 size={16} className="animate-spin" /> : <SearchCheck size={16} />}
                  Analyze idea
                </button>
              </div>
            </form>

            {clarifyingQuestion && !hasFinalReport && (
              <form
                onSubmit={handleClarificationSubmit}
                className="rounded-3xl border border-[#E1C068]/18 bg-[#171717] p-5"
              >
                <div className="flex items-center gap-2 text-[#E1C068]">
                  <Bot size={16} />
                  <h3 className="text-[15px] font-semibold">Clarifying Question</h3>
                </div>
                <div className="mt-4 rounded-2xl border border-[#E1C068]/12 bg-[#E1C068]/8 px-4 py-4">
                  <MarkdownLikeText text={clarifyingQuestion} className="space-y-2" />
                </div>
                <label className="mt-4 block">
                  <span className="mb-2 block text-[12px] font-medium text-white/55">
                    Your answer
                  </span>
                  <textarea
                    value={clarificationAnswer}
                    onChange={(e) => setClarificationAnswer(e.target.value)}
                    rows={4}
                    className="w-full rounded-2xl border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={submittingClarification}
                  className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#E1C068] px-5 py-3 text-[13px] font-bold text-[#0d0d0d] transition hover:bg-[#ecd078] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {submittingClarification ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Send size={15} />
                  )}
                  Complete analysis
                </button>
              </form>
            )}

            <div className="rounded-3xl border border-white/[0.07] bg-[#171717] p-5">
              <div className="flex items-center gap-2 text-white/80">
                <MessageSquare size={16} className="text-[#E1C068]" />
                <h3 className="text-[15px] font-semibold">Ask Follow-up Questions</h3>
              </div>

              {!conversationId || !hasFinalReport ? (
                <p className="mt-4 rounded-2xl border border-dashed border-white/10 px-4 py-6 text-[13px] text-white/35">
                  Finish one analysis first, then you can ask grounded questions about competitors, market size, GTM, or next steps.
                </p>
              ) : (
                <>
                  <form onSubmit={handleQaSubmit} className="mt-4 flex gap-3">
                    <input
                      value={qaQuestion}
                      onChange={(e) => setQaQuestion(e.target.value)}
                      placeholder="Ask a follow-up question about this idea..."
                      className="min-w-0 flex-1 rounded-full border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                      required
                    />
                    <button
                      type="submit"
                      disabled={submittingQa}
                      className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#E1C068] text-[#0d0d0d] transition hover:bg-[#ecd078] disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {submittingQa ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Send size={16} />
                      )}
                    </button>
                  </form>

                  <div className="mt-4 space-y-3">
                    {qaHistory.length === 0 ? (
                      <p className="rounded-2xl border border-dashed border-white/10 px-4 py-5 text-[13px] text-white/35">
                        No follow-up questions yet.
                      </p>
                    ) : (
                      qaHistory.map((item, index) => (
                        <div key={`${item.q}-${index}`} className="space-y-2 rounded-2xl border border-white/[0.06] bg-[#111111] p-4">
                          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
                            Question
                          </p>
                          <p className="text-[14px] text-white/88">{item.q}</p>
                          <p className="pt-2 text-[12px] font-semibold uppercase tracking-[0.18em] text-white/35">
                            Answer
                          </p>
                          <MarkdownLikeText text={item.a} />
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-3xl border border-white/[0.07] bg-[#171717] p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#E1C068]/70">
                    Feasibility Brief
                  </p>
                  <h3 className="mt-2 text-[18px] font-black text-white">
                    {idea || "Idea summary will appear here"}
                  </h3>
                </div>
                {loadingConversation && <Loader2 size={18} className="animate-spin text-white/35" />}
              </div>

              {!analysisRaw ? (
                <p className="mt-6 rounded-2xl border border-dashed border-white/10 px-4 py-10 text-center text-[13px] text-white/35">
                  Run an analysis and the generated feasibility brief will appear here.
                </p>
              ) : report ? (
                <div className="mt-5 space-y-4">
                  <MetricCard label="Score" value={report.score || "Pending"} />
                  <ReportSection title="Idea Fit" body={report.idea_fit} />
                  <ReportSection title="Competitors" body={report.competitors} />
                  <ReportSection title="Opportunity" body={report.opportunity} />
                  <ReportSection title="Targeting" body={report.targeting} />
                  <ReportSection title="Next Step" body={report.next_step} />

                  {Array.isArray(report.chain_of_thought) && report.chain_of_thought.length > 0 && (
                    <div className="rounded-2xl border border-white/[0.06] bg-[#111111] p-4">
                      <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
                        Reasoning Trail
                      </p>
                      <ol className="mt-3 space-y-2 text-[13px] leading-6 text-white/65">
                        {report.chain_of_thought.map((step, index) => (
                          <li key={`${step}-${index}`}>{index + 1}. {step}</li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-5 rounded-2xl border border-white/[0.06] bg-[#111111] p-4">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
                    Raw Analysis
                  </p>
                  <div className="mt-3">
                    <MarkdownLikeText text={analysisRaw} />
                  </div>
                </div>
              )}
            </div>

          </div>
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#E1C068]/18 bg-[#E1C068]/8 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
        {label}
      </p>
      <p className="mt-2 text-3xl font-black text-white">{value}</p>
    </div>
  );
}

function ReportSection({ title, body }: { title: string; body?: string }) {
  if (!body?.trim()) return null;
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#111111] p-4">
      <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
        {title}
      </p>
      <p className="mt-3 text-[13px] leading-6 text-white/68">{body}</p>
    </div>
  );
}
