import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  // protect admin routes
  if (request.nextUrl.pathname.startsWith("/api/admin")) {
    /**
     * NOTE: Next.js middleware runs on the Edge runtime.
     * JWT verification with `jsonwebtoken` is not Edge-compatible and can cause
     * valid tokens to appear invalid. We only enforce "auth header present" here
     * and do full verification/role checks in the route handlers via `requireAdmin()`.
     */
    const authHeader = request.headers.get("authorization") ?? "";
    if (!authHeader.trim()) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  // Protect frontend pages (pathname is URL path; route groups like (main) are not in URL)
  const PROTECTED_PREFIXES = ["/communities", "/admin", "/quiz", "/idea-lab"];

  if (PROTECTED_PREFIXES.some((p) => pathname.startsWith(p))) {
    const token = request.cookies.get("token")?.value;

    if (!token) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("from", pathname);
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/api/:path*",
    "/communities/:path*",
    "/admin",
    "/admin/:path*",
    "/idea-lab",
    "/idea-lab/:path*",
    "/quiz",
    "/quiz/:path*",
  ],
};
