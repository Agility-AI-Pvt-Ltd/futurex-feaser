import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchClassCatchup } from "@/app/lib/classcatchup";
import { cache, CacheKeys } from "@/app/lib/redis";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

interface ChatRequestBody {
  session_id: string;
  message: string;
  transcript_id?: number | null;
}

interface ChatResponse {
  session_id: string;
  answer: string;
  sources?: string[];
}

export async function POST(request: NextRequest) {
  try {
    const user = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: user.userId,
      role: user.role,
    });
    const body = (await request.json()) as ChatRequestBody;

    const data = await fetchClassCatchup<ChatResponse>("/chat", {
      method: "POST",
      headers: { Authorization: authorization },
      body: JSON.stringify({
        session_id: body.session_id,
        message: body.message,
        transcript_id: body.transcript_id ?? null,
        author_id: user.userId,
      }),
    });

    await Promise.all([
      cache.del(CacheKeys.classCatchupSessions(user.userId)),
      cache.del(CacheKeys.classCatchupMessages(user.userId, body.session_id)),
    ]);

    return NextResponse.json(data);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized")
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    return NextResponse.json(
      { error: message || "Failed to send message" },
      { status: 502 },
    );
  }
}
