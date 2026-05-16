import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { fetchIdeaLab } from "@/app/lib/idea-lab";
import { createInternalServiceAuthHeader } from "@/app/lib/internal-service-auth";

interface IdeaLabQaRequest {
  conversation_id: string;
  question: string;
}

interface IdeaLabQaResponse {
  answer: string;
  top_chunks?: Array<{ source?: string; text?: string; score?: number }>;
  trace?: Array<{ step?: string; message?: string }>;
}

export async function POST(request: NextRequest) {
  try {
    const auth = requireAuth(request);
    const authorization = createInternalServiceAuthHeader({
      sub: auth.userId,
      role: auth.role,
    });
    const body = (await request.json()) as IdeaLabQaRequest;

    const response = await fetchIdeaLab<IdeaLabQaResponse>("/qa", {
      method: "POST",
      headers: { Authorization: authorization },
      body: JSON.stringify({
        conversation_id: body.conversation_id,
        question: body.question,
      }),
    });

    return NextResponse.json(response);
  } catch (error) {
    const message = (error as Error).message;
    if (message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: message || "Failed to answer question" },
      { status: 502 },
    );
  }
}
