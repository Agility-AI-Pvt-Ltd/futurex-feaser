import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchIdeaLab } from "@/app/lib/idea-lab";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

interface IdeaLabEngagementReplyRequest {
  conversation_id: string;
  answer: string;
  engagement_question?: string | null;
}

interface IdeaLabEngagementReplyResponse {
  answer: string;
}

export async function POST(request: NextRequest) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const body = (await request.json()) as IdeaLabEngagementReplyRequest;

    const response = await fetchIdeaLab<IdeaLabEngagementReplyResponse>("/engagement-reply", {
      method: "POST",
      headers: { Authorization: authorization },
      body: JSON.stringify({
        conversation_id: body.conversation_id,
        answer: body.answer,
        engagement_question: body.engagement_question ?? null,
      }),
    });

    return NextResponse.json(response);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to save engagement answer" },
      { status: 502 },
    );
  }
}
