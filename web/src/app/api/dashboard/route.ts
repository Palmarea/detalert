/* GET /api/dashboard  →  casos abiertos (para semaforizar en el cliente) + agregados de lo resuelto hoy */
import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { dashboardStats, openEvents } from "@/lib/payments/repo";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!(await getSession())) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const [open, stats] = await Promise.all([openEvents(null), dashboardStats()]);
    return NextResponse.json({ open: open.events, stats });
  } catch (err) {
    console.error("[dashboard] falló", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
