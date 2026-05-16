"use client";

<<<<<<< HEAD
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/app/stores/authStore";
import {
  AlertTriangle,
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
  X,
  CheckCircle2,
  ChevronDown,
  Search,
  Cpu,
  XCircle,
} from "lucide-react";

interface HistoryItem {
  conversation_id: string;
  idea: string;
  timestamp: string;
  user_name: string;
}

interface IdeaLabQaResponse {
  answer: string;
}

interface IdeaLabEngagementReplyResponse {
  answer: string;
}

interface ConversationDetail {
  conversation_id: string;
  idea: string;
  user_name: string;
  ideal_customer: string;
  problem_solved: string;
  analysis: string | null;
  engagement_question?: string | null;
  qa_history: Array<{
    q?: string;
    a?: string;
    kind?: string;
    engagement_question?: string;
  }>;
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

const IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS = 220;
const HISTORY_PAGE_SIZE = 10;

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
    | { type: "heading"; level: number; text: string }
    | { type: "list"; items: string[] }
    | { type: "paragraph"; text: string }
    | { type: "separator" }
  > = [];

  for (const line of lines) {
    if (line.startsWith("### ")) {
      blocks.push({ type: "heading", level: 3, text: line.replace(/^###\s+/, "") });
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push({ type: "heading", level: 2, text: line.replace(/^##\s+/, "") });
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push({ type: "heading", level: 1, text: line.replace(/^#\s+/, "") });
      continue;
    }
    if (line === "---" || line === "***") {
      blocks.push({ type: "separator" });
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
          const fontSize = block.level === 1 ? "text-[18px]" : block.level === 2 ? "text-[16px]" : "text-[15px]";
          return (
            <h4
              key={`${block.text}-${index}`}
              className={`${fontSize} font-bold text-[#E1C068] mt-4 first:mt-0`}
            >
              {renderInlineMarkdown(block.text)}
            </h4>
          );
        }

        if (block.type === "separator") {
          return <hr key={`sep-${index}`} className="my-4 border-white/10" />;
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
=======
import { Lightbulb, Sparkles } from "lucide-react";
>>>>>>> 29a9781f514391037f7e29fa43b4ccf8a602ec18

interface NodeStep {
  type: "node";
  node?: string;
  message: string;
  timestamp: number;
}
interface ScrapeUrlStep {
  type: "scrape_url";
  url: string;
  title: string;
  status: "crawling" | "done" | "skipped";
  domain?: string;
  source_type?: "web" | "reddit" | string;
  message?: string;
  extraction_method?: string;
  subreddit?: string;
  expanded_comment_count?: number;
  crawl_url?: string;
  timestamp: number;
}
type ReasoningStep = NodeStep | ScrapeUrlStep;

type StreamScrapeStatus = "crawling" | "done" | "skipped";

interface IdeaLabStreamEvent {
  type: "node" | "scrape_url" | "log" | "final";
  node?: string;
  message?: string;
  url?: string;
  title?: string;
  status?: StreamScrapeStatus;
  domain?: string;
  source_type?: "web" | "reddit" | string;
  extraction_method?: string;
  subreddit?: string;
  expanded_comment_count?: number;
  crawl_url?: string;
  analysis?: string;
  conversation_id?: string;
  engagement_question?: string | null;
  is_vague?: boolean;
  is_report?: boolean;
}

function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function UrlCard({
  step,
  status,
}: {
  step: ScrapeUrlStep;
  status: "crawling" | "done" | "skipped";
}) {
  const domain = step.domain || getDomain(step.url);
  const isReddit = step.source_type === "reddit" || domain.includes("reddit.com") || domain.includes("redd.it");
  const activeUrl = step.crawl_url || step.url;
  const metadata =
    isReddit && step.subreddit
      ? `r/${step.subreddit}${typeof step.expanded_comment_count === "number" ? ` · ${step.expanded_comment_count} comments` : ""}`
      : step.extraction_method?.replaceAll("_", " ");

  return (
    <div className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 animate-in fade-in slide-in-from-bottom-1 duration-300">
      <img
        src={`https://www.google.com/s2/favicons?domain=${domain}&sz=16`}
        alt=""
        className="mt-0.5 h-4 w-4 shrink-0 rounded-sm opacity-80"
      />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-[12px] font-medium text-white/80">
            {step.title || domain}
          </p>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.14em] ${
            isReddit
              ? "bg-orange-500/15 text-orange-300"
              : "bg-sky-500/12 text-sky-300"
          }`}>
            {isReddit ? "Reddit" : "Web"}
          </span>
        </div>
        <p className="mt-1 truncate text-[10px] text-white/35">{activeUrl}</p>
        {step.message && (
          <p className="mt-1 text-[10px] leading-4 text-white/48">{step.message}</p>
        )}
        {metadata && (
          <p className="mt-1 text-[10px] font-medium capitalize text-[#E1C068]/65">
            {metadata}
          </p>
        )}
      </div>
      <div className="shrink-0">
        {status === "crawling" ? (
          <Loader2 size={13} className="animate-spin text-[#E1C068]/70" />
        ) : status === "done" ? (
          <CheckCircle2 size={13} className="text-emerald-400" />
        ) : (
          <XCircle size={13} className="text-white/25" />
        )}
      </div>
    </div>
  );
}

function ResearchTrailPanel({
  steps,
  urlStatuses,
  countdown,
  activeNode,
}: {
  steps: ReasoningStep[];
  urlStatuses: Record<string, "crawling" | "done" | "skipped">;
  countdown: number;
  activeNode: string;
}) {
  const nodeSteps = steps.filter((s): s is NodeStep => s.type === "node");
  const urlSteps = steps.filter((s): s is ScrapeUrlStep => s.type === "scrape_url");
  const lastNode = nodeSteps[nodeSteps.length - 1];
  const activeSource = [...urlSteps]
    .reverse()
    .find((s) => (urlStatuses[s.url] ?? s.status) === "crawling");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const visibleActiveNode = activeSource ? "web_research" : activeNode;
  const displayNodeSteps =
    activeSource && !nodeSteps.some((step) => step.node === "web_research")
      ? [
          ...nodeSteps,
          {
            type: "node" as const,
            node: "web_research",
            message: "Conducting deep web research and scraping...",
            timestamp: activeSource.timestamp,
          },
        ]
      : nodeSteps;
  const hasVisibleActiveNode = displayNodeSteps.some((step) => step.node === visibleActiveNode);
  const activeSourceCount = urlSteps.filter((s) => (urlStatuses[s.url] ?? s.status) === "crawling").length;

  const phaseIcon =
    visibleActiveNode === "web_research" ? <Search size={14} /> :
    visibleActiveNode === "analyzer" ? <Cpu size={14} /> :
    visibleActiveNode === "modify_query" ? <Search size={14} /> :
    <Loader2 size={14} className="animate-spin" />;

  const phaseLabel =
    activeSource?.message ||
    (activeSource ? `Scraping ${activeSource.title || getDomain(activeSource.url)}...` : lastNode?.message) ||
    "Initializing research context...";

  return (
    <div className="rounded-3xl border border-[#E1C068]/20 bg-[#171717] p-5 animate-in fade-in duration-300">
      {/* Phase header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#E1C068]/12 text-[#E1C068]">
          {phaseIcon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#E1C068]/60">
            Research in Progress
          </p>
          <p className="mt-0.5 truncate text-[13px] font-semibold text-white/90">
            {phaseLabel}
          </p>
          {activeSource && (
            <p className="mt-1 truncate text-[11px] text-white/42">
              Current URL: {activeSource.crawl_url || activeSource.url}
            </p>
          )}
        </div>
        <span className="shrink-0 text-xl font-black tabular-nums text-white">
          {String(Math.floor(Math.max(0, countdown) / 60)).padStart(2, "0")}:
          {String(Math.max(0, countdown) % 60).padStart(2, "0")}
        </span>
      </div>

      <div className="mt-4 rounded-2xl border border-[#E1C068]/14 bg-[#E1C068]/8 px-4 py-3 text-[12px] leading-5 text-[#E8D69C]/80">
        Do not panic if you see random or unrelated-looking websites. The research agent checks nearby sources too because unexpected links, forums, and Reddit threads can reveal useful competitors, complaints, or customer language.
      </div>

      {/* Pipeline steps */}
      {displayNodeSteps.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {displayNodeSteps.map((s, i) => {
            const isActive = hasVisibleActiveNode
              ? s.node === visibleActiveNode
              : i === displayNodeSteps.length - 1;

            return (
              <span
                key={`${s.timestamp}-${s.node}-${i}`}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] ${
                  isActive
                  ? "border border-[#E1C068]/30 bg-[#E1C068]/12 text-[#E1C068]"
                  : "border border-white/10 bg-white/5 text-white/40"
                }`}
              >
                {isActive ? (
                  <Loader2 size={9} className="animate-spin" />
                ) : (
                  <CheckCircle2 size={9} />
                )}
                {s.node ?? "step"}
              </span>
            );
          })}
        </div>
      )}

      {/* URL cards */}
      {urlSteps.length > 0 && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setSourcesOpen((current) => !current)}
            className="flex w-full items-center justify-between gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-left transition hover:border-[#E1C068]/20 hover:bg-white/[0.05]"
          >
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/40">
                Live sources being analysed
              </p>
              <p className="mt-1 text-[12px] text-white/62">
                {urlSteps.length} source{urlSteps.length === 1 ? "" : "s"}
                {activeSourceCount > 0 ? ` · ${activeSourceCount} active` : ""}
              </p>
            </div>
            <ChevronDown
              size={17}
              className={`shrink-0 text-[#E1C068] transition-transform ${sourcesOpen ? "rotate-180" : ""}`}
            />
          </button>
          {sourcesOpen && (
            <div className="mt-3 space-y-1.5 max-h-[320px] overflow-y-auto pr-1 animate-in fade-in slide-in-from-top-1 duration-200">
              {urlSteps.map((s, i) => (
                <UrlCard
                  key={`${s.url}-${i}`}
                  step={s}
                  status={urlStatuses[s.url] ?? s.status}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {urlSteps.length === 0 && (
        <p className="mt-4 rounded-2xl border border-dashed border-white/10 px-4 py-5 text-[12px] text-white/35">
          Waiting for the first search or scrape source from the backend...
        </p>
      )}

      {/* Progress bar */}
      <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#E1C068]/60 to-[#E1C068] transition-all duration-1000"
          style={{
            width: `${Math.max(4, 100 - (countdown / IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS) * 100)}%`,
          }}
        />
      </div>
    </div>
  );
}

export default function IdeaLabPage() {
<<<<<<< HEAD
  const user = useAuthStore((s) => s.user);
  const getToken = useAuthStore((s) => s.getToken);

  const [idea, setIdea] = useState("");
  const [idealCustomer, setIdealCustomer] = useState("");
  const [problemSolved, setProblemSolved] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [engagementAnswer, setEngagementAnswer] = useState("");
  const [qaQuestion, setQaQuestion] = useState("");

  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyTotalPages, setHistoryTotalPages] = useState(1);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [clarifyingQuestion, setClarifyingQuestion] = useState<string | null>(null);
  const [analysisRaw, setAnalysisRaw] = useState<string | null>(null);
  const [engagementQuestion, setEngagementQuestion] = useState<string | null>(null);
  const [qaHistory, setQaHistory] = useState<
    Array<{ q: string; a: string; kind?: string; engagement_question?: string }>
  >([]);

  const [loadingHistory, setLoadingHistory] = useState(true);
  const [submittingIdea, setSubmittingIdea] = useState(false);
  const [submittingClarification, setSubmittingClarification] = useState(false);
  const [submittingEngagement, setSubmittingEngagement] = useState(false);
  const [submittingQa, setSubmittingQa] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vagueMessage, setVagueMessage] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [researchCountdown, setResearchCountdown] = useState(IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>([]);
  const [urlStatuses, setUrlStatuses] = useState<Record<string, "crawling" | "done" | "skipped">>({});
  const [activeNode, setActiveNode] = useState<string>("");

  const report = useMemo(() => parseReport(analysisRaw), [analysisRaw]);
  const hasFinalReport = Boolean(report);
  const engagementExchange = useMemo(
    () => qaHistory.find((item) => item.kind === "engagement") || null,
    [qaHistory],
  );
  const followUpQaHistory = useMemo(
    () => qaHistory.filter((item) => item.kind !== "engagement"),
    [qaHistory],
  );
  const engagementAnswered = Boolean(engagementExchange);
  const canShowFollowUpQa = hasFinalReport && (!engagementQuestion || engagementAnswered);

  const authHeaders = useCallback((): HeadersInit => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);

  const loadHistory = useCallback(async (page = 1) => {
    setLoadingHistory(true);
    try {
      const res = await fetch(
        `/api/idea-lab/history?page=${page}&limit=${HISTORY_PAGE_SIZE}`,
        { headers: authHeaders() },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load Idea Lab history");

      setHistoryItems((data.items as HistoryItem[]) ?? []);
      setHistoryTotal(data.total ?? 0);
      setHistoryTotalPages(data.totalPages ?? 1);
      setHistoryPage(data.page ?? page);
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
        setEngagementQuestion(data.engagement_question || null);
        const parsed = parseReport(data.analysis || null);
        setClarifyingQuestion(parsed ? null : data.analysis || null);
        setQaHistory(
          Array.isArray(data.qa_history)
            ? data.qa_history
                .filter((item) => item.q && item.a)
                .map((item) => ({
                  q: item.q || "",
                  a: item.a || "",
                  kind: item.kind,
                  engagement_question: item.engagement_question,
                }))
            : [],
        );
        setClarificationAnswer("");
        setEngagementAnswer("");
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
    void loadHistory(1);
  }, [loadHistory]);

  useEffect(() => {
    const researchRunning = submittingIdea || submittingClarification;
    if (!researchRunning) return;

    const resetTimerId = window.setTimeout(() => {
      setResearchCountdown(IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS);
    }, 0);
    const intervalId = window.setInterval(() => {
      setResearchCountdown((current) => {
        if (current <= 1) {
          window.clearInterval(intervalId);
          return 0;
        }
        return current - 1;
      });
    }, 1000);

    return () => {
      window.clearTimeout(resetTimerId);
      window.clearInterval(intervalId);
    };
  }, [submittingIdea, submittingClarification]);

  const applyResearchStreamEvent = useCallback((data: IdeaLabStreamEvent) => {
    if (data.type === "node") {
      setActiveNode(data.node ?? "");
      setReasoningSteps((prev) => [
        ...prev,
        {
          type: "node",
          node: data.node,
          message: data.message || `Executing ${data.node || "research step"}...`,
          timestamp: Date.now(),
        },
      ]);
      return;
    }

    if (data.type === "scrape_url" && data.url) {
      const status = data.status || "crawling";
      setActiveNode("web_research");
      setUrlStatuses((prev) => ({ ...prev, [data.url as string]: status }));
      setReasoningSteps((prev) => {
        const existingIndex = prev.findIndex(
          (step) => step.type === "scrape_url" && step.url === data.url,
        );
        const nextStep: ScrapeUrlStep = {
          type: "scrape_url",
          url: data.url as string,
          title: data.title || data.domain || data.url || "",
          status,
          domain: data.domain,
          source_type: data.source_type,
          message: data.message,
          extraction_method: data.extraction_method,
          subreddit: data.subreddit,
          expanded_comment_count: data.expanded_comment_count,
          crawl_url: data.crawl_url,
          timestamp: Date.now(),
        };

        if (existingIndex === -1) return [...prev, nextStep];

        return prev.map((step, index) => {
          if (index !== existingIndex || step.type !== "scrape_url") return step;
          return {
            ...step,
            ...nextStep,
            title: nextStep.title || step.title,
            domain: nextStep.domain || step.domain,
            source_type: nextStep.source_type || step.source_type,
            crawl_url: nextStep.crawl_url || step.crawl_url,
            timestamp: step.timestamp,
          };
        });
      });
    }
  }, []);

  async function handleIdeaSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmittingIdea(true);
    setError(null);
    setVagueMessage(null);
    setResearchCountdown(IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS);
    setReasoningSteps([]);
    setUrlStatuses({});
    setActiveNode("");
    try {
      const res = await fetch("/api/idea-lab/chat/stream", {
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
          authorId: user?.id || "anonymous",
          conversation_id: null,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to analyze idea");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6)) as IdeaLabStreamEvent;
            applyResearchStreamEvent(data);
            if (data.type === "final") {
              if (data.is_vague) {
                setVagueMessage(data.analysis || null);
              } else if (data.is_report) {
                setConversationId(data.conversation_id || null);
                setAnalysisRaw(data.analysis || null);
                setEngagementQuestion(data.engagement_question || null);
                setClarifyingQuestion(null);
              } else {
                setConversationId(data.conversation_id || null);
                setClarifyingQuestion(data.analysis || null);
                setAnalysisRaw(null);
              }
            }
          }
        }
      }

      await loadHistory(1);
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
    setResearchCountdown(IDEA_LAB_RESEARCH_COUNTDOWN_SECONDS);
    setReasoningSteps([]);
    setUrlStatuses({});
    setActiveNode("");
    try {
      const res = await fetch("/api/idea-lab/chat/stream", {
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
          authorId: user?.id || "anonymous",
          conversation_id: conversationId,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to complete analysis");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6)) as IdeaLabStreamEvent;
            applyResearchStreamEvent(data);
            if (data.type === "final") {
              if (data.is_report) {
                setAnalysisRaw(data.analysis || null);
                setEngagementQuestion(data.engagement_question || null);
                setClarifyingQuestion(null);
                setClarificationAnswer("");
              } else {
                setClarifyingQuestion(data.analysis || null);
                setAnalysisRaw(null);
              }
            }
          }
        }
      }

      await loadHistory(1);
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

  async function handleEngagementSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!conversationId || !engagementQuestion || !engagementAnswer.trim()) return;
    setSubmittingEngagement(true);
    setError(null);
    try {
      const res = await fetch("/api/idea-lab/engagement-reply", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          engagement_question: engagementQuestion,
          answer: engagementAnswer,
        }),
      });
      const data = (await res.json()) as IdeaLabEngagementReplyResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to save engagement answer");

      setQaHistory((prev) => [
        ...prev,
        {
          kind: "engagement",
          engagement_question: engagementQuestion,
          q: engagementAnswer,
          a: data.answer,
        },
      ]);
      setEngagementAnswer("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmittingEngagement(false);
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
    setEngagementQuestion(null);
    setEngagementAnswer("");
    setQaHistory([]);
    setQaQuestion("");
    setError(null);
    setVagueMessage(null);
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
              <div className="flex items-center justify-between gap-2 text-[#E1C068]">
                <div className="flex items-center gap-2">
                  <FlaskConical size={15} />
                  <p className="text-[12px] font-semibold">Saved Analyses</p>
                </div>
                {historyTotal > 0 && (
                  <span className="text-[11px] text-white/35">{historyTotal} total</span>
                )}
              </div>
              <div className="mt-3 space-y-2">
                {loadingHistory ? (
                  <div className="flex items-center justify-center py-8 text-white/45">
                    <Loader2 size={18} className="animate-spin" />
                  </div>
                ) : historyItems.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-white/10 px-3 py-6 text-center text-[12px] text-white/35">
                    Your Idea Lab conversations will appear here.
                  </p>
                ) : (
                  historyItems.map((item) => (
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

              {/* Pagination controls */}
              {historyTotalPages > 1 && (
                <div className="mt-3 flex items-center justify-between gap-2 border-t border-white/[0.06] pt-3">
                  <button
                    type="button"
                    disabled={historyPage <= 1 || loadingHistory}
                    onClick={() => void loadHistory(historyPage - 1)}
                    className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/55 transition hover:border-[#E1C068]/25 hover:text-[#E1C068] disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    ← Prev
                  </button>
                  <span className="text-[11px] text-white/35">
                    {historyPage} / {historyTotalPages}
                  </span>
                  <button
                    type="button"
                    disabled={historyPage >= historyTotalPages || loadingHistory}
                    onClick={() => void loadHistory(historyPage + 1)}
                    className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/55 transition hover:border-[#E1C068]/25 hover:text-[#E1C068] disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    Next →
                  </button>
                </div>
              )}
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

        {vagueMessage && (
          <div className="rounded-2xl border border-amber-500/35 bg-amber-500/10 px-5 py-4 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400">
                <AlertTriangle size={17} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-semibold uppercase tracking-[0.2em] text-amber-400">
                  Idea Too Vague
                </p>
                <p className="mt-2 text-[13px] leading-6 text-amber-200/85">
                  {vagueMessage}
                </p>
                <button
                  type="button"
                  onClick={() => setVagueMessage(null)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/15 px-3 py-1.5 text-[11px] font-semibold text-amber-300 transition hover:bg-amber-500/25"
                >
                  <X size={12} />
                  Dismiss &amp; try again
                </button>
              </div>
            </div>
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

            {(submittingIdea || submittingClarification) && (
              <ResearchTrailPanel
                steps={reasoningSteps}
                urlStatuses={urlStatuses}
                countdown={researchCountdown}
                activeNode={activeNode}
              />
            )}

            {clarifyingQuestion && !hasFinalReport && !submittingClarification && (
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
                  className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#E1C068] px-5 py-3 text-[13px] font-bold text-[#0d0d0d] transition hover:bg-[#ecd078]"
                >
                  <Send size={15} />
                  Complete analysis
                </button>
              </form>
            )}

            <div className="rounded-3xl border border-white/[0.07] bg-[#171717] p-5">
              <div className="flex items-center gap-2 text-white/80">
                <MessageSquare size={16} className="text-[#E1C068]" />
                <h3 className="text-[15px] font-semibold">Ask Follow-up Questions</h3>
              </div>

              {!conversationId || !canShowFollowUpQa ? (
                <p className="mt-4 rounded-2xl border border-dashed border-white/10 px-4 py-6 text-[13px] text-white/35">
                  {hasFinalReport && engagementQuestion && !engagementAnswered
                    ? "Answer the engagement question first, then you can ask grounded follow-up questions."
                    : "Finish one analysis first, then you can ask grounded questions about competitors, market size, GTM, or next steps."}
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
                    {followUpQaHistory.length === 0 ? (
                      <p className="rounded-2xl border border-dashed border-white/10 px-4 py-5 text-[13px] text-white/35">
                        No follow-up questions yet.
                      </p>
                    ) : (
                      followUpQaHistory.map((item, index) => (
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
                  {engagementQuestion && (
                    <div className="rounded-2xl border border-[#E1C068]/18 bg-[#E1C068]/8 p-4">
                      <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
                        Engagement Question
                      </p>
                      <p className="mt-3 text-[15px] font-semibold leading-7 text-white/92">
                        {engagementQuestion}
                      </p>
                      {!engagementAnswered ? (
                        <form onSubmit={handleEngagementSubmit} className="mt-4 space-y-3">
                          <textarea
                            value={engagementAnswer}
                            onChange={(e) => setEngagementAnswer(e.target.value)}
                            rows={4}
                            placeholder="Share your answer here..."
                            className="w-full rounded-2xl border border-white/[0.08] bg-[#111111] px-4 py-3 text-[14px] text-white outline-none transition placeholder:text-white/25 focus:border-[#E1C068]/35"
                            required
                          />
                          <button
                            type="submit"
                            disabled={submittingEngagement}
                            className="inline-flex items-center gap-2 rounded-full bg-[#E1C068] px-5 py-3 text-[13px] font-bold text-[#0d0d0d] transition hover:bg-[#ecd078] disabled:cursor-not-allowed disabled:opacity-70"
                          >
                            {submittingEngagement ? (
                              <Loader2 size={16} className="animate-spin" />
                            ) : (
                              <Send size={15} />
                            )}
                            {submittingEngagement ? "Saving your answer..." : "Submit answer"}
                          </button>
                        </form>
                      ) : (
                        <div className="mt-4 space-y-3 rounded-2xl border border-white/[0.06] bg-[#111111] p-4">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/35">
                              Your Answer
                            </p>
                            <p className="mt-2 text-[14px] leading-7 text-white/88">
                              {engagementExchange?.q}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
                              Advisor Reply
                            </p>
                            <div className="mt-2">
                              <MarkdownLikeText text={engagementExchange?.a || ""} />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
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
      <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-[#E1C068]/75">
        {title}
      </p>
      <MarkdownLikeText text={body} />
=======
  return (
    <div className="flex min-h-[min(72vh,720px)] flex-col items-center justify-center px-4 py-12">
      <div className="relative max-w-lg rounded-3xl border border-[#E1C068]/20 bg-[#171717] px-10 py-14 text-center shadow-[0_0_80px_-20px_rgba(225,192,104,0.35)]">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#E1C068]/14 text-[#E1C068]">
          <Lightbulb size={28} aria-hidden />
        </div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[#E1C068]/70">
          Idea Lab
        </p>
        <h1 className="mt-3 text-3xl font-black tracking-tight text-white">
          Coming soon
        </h1>
        <p className="mt-4 text-[14px] leading-relaxed text-white/48">
          We&apos;re polishing this workspace. You can continue from here later.
        </p>
        <div className="mt-8 inline-flex items-center gap-2 rounded-full border border-[#E1C068]/20 bg-[#E1C068]/8 px-4 py-2 text-[12px] font-medium text-[#E1C068]/90">
          <Sparkles size={14} className="shrink-0" aria-hidden />
          Stay tuned
        </div>
      </div>
>>>>>>> 29a9781f514391037f7e29fa43b4ccf8a602ec18
    </div>
  );
}
