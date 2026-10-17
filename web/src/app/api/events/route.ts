/* GET /api/events?since=<cursor>  →  EventsPage
   Casos abiertos guardados en Postgres. Los eventos entran por POST /api/ingest. */
import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { openEvents } from "@/lib/payments/repo";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  if (!(await getSession())) return NextResponse.json({ error: "unauthorized" }, { status: 401 }); // además del middleware
  try {
    return NextResponse.json(await openEvents(req.nextUrl.searchParams.get("since")));
  } catch (err) {
    console.error("[events] no se pudo leer la base de datos", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
