import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchIdeaLab } from "@/app/lib/idea-lab";
import { cache, CacheKeys } from "@/app/lib/redis";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

interface HistoryItem {
  conversation_id: string;
  idea: string;
  timestamp: string;
  user_name: string;
}

interface PaginatedHistory {
  items?: HistoryItem[];
}

interface ConversationDetail {
  conversation_id: string;
  idea: string;
  user_name: string;
  ideal_customer: string;
  problem_solved: string;
  analysis: string | null;
  engagement_question?: string | null;
  qa_history: Array<{ q?: string; a?: string }>;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ conversationId: string }> },
) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const { conversationId } = await context.params;

    const cacheKey = CacheKeys.ideaLabConversation(conversationId);
    const cached = await cache.get<ConversationDetail>(cacheKey);

    if (cached) {
      return NextResponse.json(cached, {
        headers: { "X-Cache": "HIT" },
      });
    }

    const history = await fetchIdeaLab<HistoryItem[] | PaginatedHistory>(
      `/history?author_id=${encodeURIComponent(auth.userId)}`,
      {
        method: "GET",
        headers: { Authorization: authorization },
      },
    );
    const historyItems = Array.isArray(history) ? history : (history.items ?? []);

    if (!historyItems.some((item) => item.conversation_id === conversationId)) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const response = await fetchIdeaLab<ConversationDetail>(
      `/history/${encodeURIComponent(conversationId)}`,
      {
        method: "GET",
        headers: { Authorization: authorization },
      },
    );

    // Cache the conversation history for 10 seconds
    await cache.set(cacheKey, response, 10);

    return NextResponse.json(response);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to load conversation" },
      { status: 502 },
    );
  }
}
