import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchClassCatchup } from "@/app/lib/classcatchup";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

type SessionListResponse = {
  sessions: unknown[];
  hasMore: boolean;
  limit: number;
  offset: number;
};

function parsePositiveInt(value: string | null, fallback: number) {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return parsed;
}

export async function GET(request: NextRequest) {
  try {
    const user = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: user.userId,
      role: user.role,
    });
    const requestedLimit = parsePositiveInt(
      request.nextUrl.searchParams.get("limit"),
      DEFAULT_LIMIT,
    );
    const limit = Math.min(Math.max(requestedLimit, 1), MAX_LIMIT);
    const offset = parsePositiveInt(
      request.nextUrl.searchParams.get("offset"),
      0,
    );

    const data = await fetchClassCatchup<unknown[]>(
      `/sessions?author_id=${encodeURIComponent(user.userId)}&limit=${limit + 1}&offset=${offset}`,
      { method: "GET", headers: { Authorization: authorization } },
    );

    const hasMore = data.length > limit;
    const sessions = hasMore ? data.slice(0, limit) : data;

    return NextResponse.json({
      sessions,
      hasMore,
      limit,
      offset,
    } satisfies SessionListResponse);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized")
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    return NextResponse.json(
      { error: message || "Failed to load sessions" },
      { status: 502 },
    );
  }
}
