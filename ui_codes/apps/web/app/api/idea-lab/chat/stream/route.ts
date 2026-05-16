import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { getIdeaLabApiBase } from "@/app/lib/idea-lab";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const body = await request.json();
    const base = getIdeaLabApiBase();

    const backendRes = await fetch(`${base}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authorization,
      },
      body: JSON.stringify({
        ...body,
        authorId: auth.userId,
      }),
    });

    if (!backendRes.ok) {
      const errorText = await backendRes.text();
      return new Response(errorText, {
        status: backendRes.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(backendRes.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
      },
    });
  } catch (error) {
    console.error("Streaming proxy error:", error);
    return NextResponse.json(
      { error: (error as Error).message || "Failed to proxy stream" },
      { status: 500 },
    );
  }
}
