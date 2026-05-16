import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchClassCatchup } from "@/app/lib/classcatchup";
import { cache, CacheKeys } from "@/app/lib/redis";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  try {
    const user = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: user.userId,
      role: user.role,
    });
    const { sessionId } = await params;
    const cacheKey = CacheKeys.classCatchupMessages(user.userId, sessionId);
    const cached = await cache.get<unknown[]>(cacheKey);

    if (cached) {
      return NextResponse.json(cached, {
        headers: { "X-Cache": "HIT" },
      });
    }

    const data = await fetchClassCatchup(
      `/history/${encodeURIComponent(sessionId)}`,
      { method: "GET", headers: { Authorization: authorization } },
    );
    await cache.set(cacheKey, data, 300);

    return NextResponse.json(data);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized")
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    return NextResponse.json(
      { error: message || "Failed to load messages" },
      { status: 502 },
    );
  }
}
