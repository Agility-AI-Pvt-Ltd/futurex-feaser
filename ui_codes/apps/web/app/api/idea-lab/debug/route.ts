import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/app/middleware/auth";
import { getIdeaLabApiBase, getIdeaLabOpenApiProbeUrls } from "@/app/lib/idea-lab";

/**
 * GET — verify Idea Lab base URL from the Next server (same process as /api/idea-lab/*).
 * While logged in, open /api/idea-lab/debug in the browser; if openapi probe is HTML, fix IDEA_LAB_API_URL.
 */
export async function GET(request: NextRequest) {
  try {
    requireAuth(request);
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const base = getIdeaLabApiBase();
  const openapiUrls = getIdeaLabOpenApiProbeUrls(base);

  let openapiUrl = openapiUrls[0]!;
  let openapi: {
    ok: boolean;
    status: number;
    contentType: string;
    startsWithJson: boolean;
    startsWithHtml: boolean;
    snippet: string;
    error?: string;
  };

  try {
    let lastErr = "";
    let r: Response | undefined;
    let text = "";
    for (const url of openapiUrls) {
      openapiUrl = url;
      try {
        r = await fetch(url, {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: AbortSignal.timeout(12_000),
        });
        text = await r.text();
        const t = text.trimStart();
        const startsJson = t.startsWith("{") || t.startsWith("[");
        const looksLikeOpenApi =
          startsJson &&
          (t.includes('"openapi"') ||
            t.includes('"swagger"') ||
            t.includes('"OpenAPI"'));
        if (r.ok && looksLikeOpenApi) break;
        const tryNext =
          openapiUrls.indexOf(url) < openapiUrls.length - 1 &&
          (!looksLikeOpenApi || !r.ok);
        if (tryNext) {
          lastErr = `HTTP ${r.status} at ${url}`;
          continue;
        }
        break;
      } catch (e) {
        lastErr = (e as Error).message;
        if (openapiUrls.indexOf(url) < openapiUrls.length - 1) continue;
        throw e;
      }
    }
    if (!r) throw new Error(lastErr || "OpenAPI probe failed");
    const t = text.trimStart();
    openapi = {
      ok: r.ok,
      status: r.status,
      contentType: r.headers.get("content-type") || "",
      startsWithJson: t.startsWith("{") || t.startsWith("["),
      startsWithHtml: t.startsWith("<!") || t.toLowerCase().startsWith("<html"),
      snippet: t.replace(/\s+/g, " ").slice(0, 160),
    };
  } catch (e) {
    openapi = {
      ok: false,
      status: 0,
      contentType: "",
      startsWithJson: false,
      startsWithHtml: false,
      snippet: "",
      error: (e as Error).message,
    };
  }

  const hf =
    /\.hf\.space/i.test(base) || /huggingface\.co/i.test(base)
      ? "This URL looks like Hugging Face Spaces — those hosts often return HTML (not OpenAPI JSON) to server-side fetch. Use a normal FastAPI deployment URL instead."
      : "FastAPI should expose JSON at {base}/openapi.json and POST {base}/qa. If openapi.startsWithHtml is true, fix IDEA_LAB_API_URL (try adding/removing /api to match root_path).";

  return NextResponse.json({
    ideaLabApiBase: base,
    openapiUrl,
    openapi,
    hint: hf,
  });
}
