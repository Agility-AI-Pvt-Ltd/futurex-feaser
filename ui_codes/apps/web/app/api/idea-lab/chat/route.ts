import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchIdeaLab } from "@/app/lib/idea-lab";
import { cache } from "@/app/lib/redis";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

interface IdeaLabChatRequest {
  idea: string;
  user_name?: string;
  ideal_customer: string;
  problem_solved: string;
  conversation_id?: string | null;
}

interface IdeaLabChatResponse {
  response: string;
  conversation_id: string;
  analysis: string | null;
  engagement_question?: string | null;
}

export async function POST(request: NextRequest) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const body = (await request.json()) as IdeaLabChatRequest;

    const response = await fetchIdeaLab<IdeaLabChatResponse>("/chat", {
      method: "POST",
      headers: { Authorization: authorization },
      body: JSON.stringify({
        idea: body.idea,
        user_name: body.user_name?.trim() || auth.email || auth.userId,
        ideal_customer: body.ideal_customer,
        problem_solved: body.problem_solved,
        authorId: auth.userId,
        conversation_id: body.conversation_id ?? null,
      }),
    });

    // Invalidate all paginated history cache pages for this user
    await cache.delPattern(`cache:idealab:history:${auth.userId}:p*`);

    return NextResponse.json(response);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("[idea-lab/chat]", message);
    return NextResponse.json(
      { error: message || "Failed to submit idea" },
      { status: 502 },
    );
  }
}
