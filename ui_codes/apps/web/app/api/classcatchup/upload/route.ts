import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { getIdeaLabApiBase } from "@/app/lib/idea-lab";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";
import { cache, CacheKeys } from "@/app/lib/redis";

export async function POST(request: NextRequest) {
  try {
    const user = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: user.userId,
      role: user.role,
    });
    const formData = await request.formData();

    const base = getIdeaLabApiBase();
    const response = await fetch(`${base}/upload`, {
      method: "POST",
      headers: { Authorization: authorization },
      body: formData, // fetch will automatically set the correct Content-Type for FormData
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.error || "Upload failed");
    }

    await cache.del(CacheKeys.classCatchupTranscripts(user.userId));

    return NextResponse.json(data);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to upload transcript" },
      { status: 502 },
    );
  }
}
