/* /api/agent-events — pasos del equipo de agentes, para verlos en vivo en la bandeja.
   POST: máquina a máquina como /api/ingest (token INGEST_TOKEN, sin sesión). El agente manda un paso por llamada:
         { case_id, event_id, paso, estado, at, ms, resumen (≤160), datos (objeto chico) }.
   GET ?since=<id>: con sesión; los pasos con id > since (máx. 100) en orden, más el último id y la hora del servidor.
         Sin since: los de los últimos 10 minutos. */
import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

const MAX_BYTES = 20 * 1024;
const MAX_DATOS = 8 * 1024;
const MAX_ROWS = 100;
const PASOS = ["ml", "evaluador", "cognitivo", "contexto", "memoria", "decisor", "compuerta", "envio"] as const;
const ESTADOS = ["fin", "error", "omitido"] as const;

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

const bad = (detail: string) => NextResponse.json({ error: "payload inválido", detail }, { status: 400 });

function text(v: unknown, max: number): string | null | undefined {
  if (v === undefined || v === null) return null;
  if (typeof v !== "string" || v.length > max) return undefined;
  return v;
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  if (!safeEqual(auth, `Bearer ${token()}`)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const raw = await req.text();
  if (Buffer.byteLength(raw, "utf8") >= MAX_BYTES) return NextResponse.json({ error: "payload demasiado grande", limit: MAX_BYTES }, { status: 413 });

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return bad("se esperaba un objeto");
    body = parsed as Record<string, unknown>;
  } catch {
    return bad("no es JSON");
  }

  const eventId = text(body.event_id, 100);
  if (!eventId) return bad("event_id es obligatorio (texto ≤ 100)");
  const caseId = text(body.case_id, 100);
  if (caseId === undefined) return bad("case_id debe ser texto ≤ 100");
  const paso = body.paso;
  if (typeof paso !== "string" || !(PASOS as readonly string[]).includes(paso)) return bad(`paso debe ser uno de: ${PASOS.join(", ")}`);
  const estado = body.estado;
  if (typeof estado !== "string" || !(ESTADOS as readonly string[]).includes(estado)) return bad(`estado debe ser uno de: ${ESTADOS.join(", ")}`);
  const atText = text(body.at, 40);
  if (atText === undefined) return bad("at debe ser una fecha ISO");
  const at = atText ? new Date(atText) : new Date();
  if (Number.isNaN(at.getTime())) return bad("at debe ser una fecha ISO");
  const ms = body.ms === undefined || body.ms === null ? null : body.ms;
  if (ms !== null && (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0 || ms > 86_400_000)) return bad("ms debe ser un número entre 0 y 86400000");
  if (body.resumen !== undefined && body.resumen !== null && typeof body.resumen !== "string") return bad("resumen debe ser texto");
  const resumen = typeof body.resumen === "string" ? body.resumen.slice(0, 160) : null; // el contrato dice ≤160: se recorta, no se rechaza
  let datos: string | null = null;
  if (body.datos !== undefined && body.datos !== null) {
    if (typeof body.datos !== "object" || Array.isArray(body.datos)) return bad("datos debe ser un objeto");
    datos = JSON.stringify(body.datos);
    if (Buffer.byteLength(datos, "utf8") > MAX_DATOS) return bad(`datos no puede pasar de ${MAX_DATOS} bytes`);
  }

  try {
    const [row] = await sql<{ id: string }>(
      `insert into agent_events (event_id, case_id, paso, estado, at, ms, resumen, datos)
       values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb) returning id`,
      [eventId, caseId, paso, estado, at.toISOString(), ms === null ? null : Math.round(ms), resumen, datos],
    );
    return NextResponse.json({ ok: true, id: Number(row.id) });
  } catch (err) {
    console.error("[agent-events] no se pudo guardar", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}

type Row = {
  id: string;
  event_id: string;
  case_id: string | null;
  paso: string;
  estado: string;
  at: Date | null;
  ms: number | null;
  resumen: string | null;
  datos: unknown;
  received_at: Date;
};

export async function GET(req: NextRequest) {
  if (!(await getSession())) return NextResponse.json({ error: "unauthorized" }, { status: 401 }); // además del middleware
  const sinceRaw = req.nextUrl.searchParams.get("since");
  const since = sinceRaw && /^\d{1,18}$/.test(sinceRaw) ? sinceRaw : null;
  try {
    const rows = since
      ? await sql<Row>(`select * from agent_events where id > $1 order by id asc limit ${MAX_ROWS}`, [since])
      : await sql<Row>(
          `select * from (select * from agent_events where received_at > now() - interval '10 minutes' order by id desc limit ${MAX_ROWS}) t order by id asc`,
        );
    let last = since ? Number(since) : 0;
    if (!since && !rows.length) {
      const [m] = await sql<{ id: string | null }>("select max(id) as id from agent_events");
      last = m?.id ? Number(m.id) : 0;
    }
    const events = rows.map((r) => ({
      id: Number(r.id),
      event_id: r.event_id,
      case_id: r.case_id,
      paso: r.paso,
      estado: r.estado,
      at: r.at ? r.at.toISOString() : null,
      ms: r.ms,
      resumen: r.resumen,
      datos: r.datos ?? null,
      received_at: r.received_at.toISOString(),
    }));
    if (events.length) last = events[events.length - 1].id;
    return NextResponse.json({ events, last, now: new Date().toISOString() }); // now: para que el cliente corrija el desfase de reloj
  } catch (err) {
    console.error("[agent-events] no se pudo leer la base de datos", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
