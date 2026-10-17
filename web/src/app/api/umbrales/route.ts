/* GET /api/umbrales  →  { base, props, actualizado, fuente }
   Lo último que publicó el agente por POST /api/agent-learning. Si nunca llegó nada,
   responde fuente "ejemplo" y /umbrales.html se queda con sus datos de ejemplo. */
import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

type Row = { body: { base?: unknown; props?: unknown }; updated_at: Date };

export async function GET() {
  if (!(await getSession())) return NextResponse.json({ error: "unauthorized" }, { status: 401 }); // además del middleware
  try {
    const [row] = await sql<Row>("select body, updated_at from agent_learning where id = 1");
    if (!row) return NextResponse.json({ base: null, props: null, fuente: "ejemplo" });
    return NextResponse.json({
      base: row.body.base ?? null,
      props: Array.isArray(row.body.props) ? row.body.props : null,
      actualizado: row.updated_at.toISOString(),
      fuente: "agente",
    });
  } catch (err) {
    console.error("[umbrales] no se pudo leer la base de datos", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
