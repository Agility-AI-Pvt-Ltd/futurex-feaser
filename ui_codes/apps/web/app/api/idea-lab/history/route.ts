import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchIdeaLab } from "@/app/lib/idea-lab";
import { cache, CacheKeys } from "@/app/lib/redis";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

const PAGE_CACHE_TTL = 30; // seconds
const DEFAULT_LIMIT = 10;

interface HistoryItem {
  conversation_id: string;
  idea: string;
  timestamp: string;
  user_name: string;
}

interface PaginatedHistory {
  items: HistoryItem[];
  total: number;
  offset: number;
  limit: number;
}

interface HistoryPageResponse {
  items: HistoryItem[];
  total: number;
  totalPages: number;
  page: number;
  limit: number;
}

export async function GET(request: NextRequest) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const { searchParams } = request.nextUrl;

    const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10));
    const limit = Math.max(1, parseInt(searchParams.get("limit") ?? String(DEFAULT_LIMIT), 10));
    const offset = (page - 1) * limit;

    const cacheKey = CacheKeys.ideaLabHistoryPage(auth.userId, page, limit);
    const cached = await cache.get<HistoryPageResponse>(cacheKey);

    if (cached) {
      return NextResponse.json(cached, { headers: { "X-Cache": "HIT" } });
    }

    const raw = await fetchIdeaLab<PaginatedHistory | HistoryItem[]>(
      `/history?author_id=${encodeURIComponent(auth.userId)}&limit=${limit}&offset=${offset}`,
      { method: "GET", headers: { Authorization: authorization } },
    );

    // Handle both old (plain array) and new ({items,total}) backend response shapes
    const items = Array.isArray(raw) ? raw : ((raw as PaginatedHistory).items ?? []);
    const total = Array.isArray(raw) ? raw.length : ((raw as PaginatedHistory).total ?? 0);
    const totalPages = Math.max(1, Math.ceil(total / limit));

    const result: HistoryPageResponse = {
      items,
      total,
      totalPages,
      page,
      limit,
    };

    await cache.set(cacheKey, result, PAGE_CACHE_TTL);

    return NextResponse.json(result);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to load history" },
      { status: 502 },
    );
  }
}
