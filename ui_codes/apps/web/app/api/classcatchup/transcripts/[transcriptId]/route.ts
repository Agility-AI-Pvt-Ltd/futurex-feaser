import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchClassCatchup } from "@/app/lib/classcatchup";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";
import { cache, CacheKeys } from "@/app/lib/redis";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ transcriptId: string }> },
) {
  try {
    const user = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: user.userId,
      role: user.role,
    });
    const { transcriptId } = await params;
    const body = await request.json();

    const data = await fetchClassCatchup(
      `/transcripts/${encodeURIComponent(transcriptId)}`,
      {
        method: "PATCH",
        headers: { Authorization: authorization },
        body: JSON.stringify(body),
      },
    );

    await cache.del(CacheKeys.classCatchupTranscripts(user.userId));

    return NextResponse.json(data);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to update transcript metadata" },
      { status: 502 },
    );
  }
}
