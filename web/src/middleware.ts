/* Todo el sitio exige sesión salvo /login.
   - Páginas sin sesión → redirige a /login (recordando a dónde iba).
   - API sin sesión → 401, así /api/events no se puede consultar desde fuera.
   - /api/ingest y POST /api/agent-learning son máquina a máquina: no usan sesión, la ruta exige INGEST_TOKEN. */
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/auth/session";

export async function middleware(req: NextRequest) {
  if (req.nextUrl.pathname === "/api/ingest" || (req.nextUrl.pathname === "/api/agent-learning" && req.method === "POST")) return NextResponse.next();
  const session = await verifySession(req.cookies.get(SESSION_COOKIE)?.value);
  const { pathname, search } = req.nextUrl;

  if (pathname === "/login") return session ? NextResponse.redirect(new URL("/", req.url)) : NextResponse.next();
  if (session) return NextResponse.next();
  if (pathname.startsWith("/api/")) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL("/login", req.url);
  if (pathname !== "/") url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/((?!_next/|favicon.ico).*)"] };
