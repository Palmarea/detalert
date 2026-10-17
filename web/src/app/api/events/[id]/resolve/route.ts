/* POST /api/events/:id/resolve  { action: "approved" | "rejected", note?: string, evidence?: { category, indicators } }
   Archiva el caso, registra al analista de la sesión y deja la notificación en cola.
   evidence solo se acepta al rechazar: guarda el caso como evidencia para análisis de riesgo. */
import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { parseEvidence } from "@/lib/payments/evidence";
import { resolveEvent } from "@/lib/payments/repo";

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = (await req.json().catch(() => ({}))) as { action?: string; note?: string; evidence?: unknown };
  if (body.action !== "approved" && body.action !== "rejected") {
    return NextResponse.json({ error: "action debe ser approved o rejected" }, { status: 400 });
  }
  const note = body.note?.trim().slice(0, 1000) || null;
  const evidence = parseEvidence(body.evidence);
  if (typeof evidence === "string") return NextResponse.json({ error: evidence }, { status: 400 });
  if (evidence && body.action !== "rejected") return NextResponse.json({ error: "Solo un rechazo se puede archivar como evidencia." }, { status: 400 });

  try {
    const r = await resolveEvent(id, body.action, note, { email: session.sub, name: session.name, role: session.role }, evidence);
    return r.ok ? NextResponse.json({ ok: true }) : NextResponse.json({ error: r.error }, { status: r.status });
  } catch (err) {
    console.error("[resolve] falló", err);
    return NextResponse.json({ error: "No se pudo guardar. Intenta de nuevo." }, { status: 503 });
  }
}
