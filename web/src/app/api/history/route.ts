/* GET /api/history?q=&outcome=&urgency=&analyst=&from=&to=&offset=  →  casos archivados */
import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { history, type HistoryFilter } from "@/lib/payments/repo";

export const dynamic = "force-dynamic";

const DATE = /^\d{4}-\d{2}-\d{2}$/;

export async function GET(req: NextRequest) {
  if (!(await getSession())) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const sp = req.nextUrl.searchParams;
  const pick = <T extends string>(k: string, allowed: readonly T[]) => (allowed.includes(sp.get(k) as T) ? (sp.get(k) as T) : undefined);
  const f: HistoryFilter = {
    q: sp.get("q")?.trim() || undefined,
    outcome: pick("outcome", ["approved", "rejected", "all"] as const),
    urgency: pick("urgency", ["urgent", "normal", "all"] as const),
    analyst: sp.get("analyst") || undefined,
    from: DATE.test(sp.get("from") ?? "") ? sp.get("from")! : undefined,
    to: DATE.test(sp.get("to") ?? "") ? sp.get("to")! : undefined,
    offset: Number(sp.get("offset")) || 0,
  };
  try {
    return NextResponse.json(await history(f));
  } catch (err) {
    console.error("[history] falló", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
