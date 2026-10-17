/* POST /api/ingest — punto de entrada de la fuente de eventos (hoy: scripts/feed.ts).
   Es máquina a máquina: no usa la sesión del analista, sino el token INGEST_TOKEN. */
import { NextRequest, NextResponse } from "next/server";
import { adaptIncoming } from "@/lib/payments/ingest";
import { saveEvents } from "@/lib/payments/repo";

export const dynamic = "force-dynamic";

function token() {
  const t = process.env.INGEST_TOKEN;
  if (t) return t;
  if (process.env.NODE_ENV === "production") throw new Error("Falta INGEST_TOKEN.");
  return "dev-ingest-token";
}

function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) | 0) ^ (b.charCodeAt(i) | 0);
  return diff === 0;
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  if (!safeEqual(auth, `Bearer ${token()}`)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let items;
  try {
    items = adaptIncoming(await req.json());
  } catch (err) {
    return NextResponse.json({ error: "payload inválido", detail: String(err instanceof Error ? err.message : err) }, { status: 400 });
  }
  try {
    const inserted = await saveEvents(items);
    return NextResponse.json({ received: items.length, inserted });
  } catch (err) {
    console.error("[ingest] no se pudo guardar", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
