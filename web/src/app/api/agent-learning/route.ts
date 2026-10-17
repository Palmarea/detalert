/* POST /api/agent-learning — el agente publica sus propuestas de umbrales (lo que muestra /umbrales.html).
   Máquina a máquina como /api/ingest: no usa la sesión del analista, sino el token INGEST_TOKEN.
   Guarda solo el último cuerpo recibido (reemplaza al anterior). */
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

const MAX_BYTES = 200 * 1024;
const MAX_PROPS = 20;

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

  const raw = await req.text();
  if (Buffer.byteLength(raw, "utf8") >= MAX_BYTES) return NextResponse.json({ error: "payload demasiado grande", limit: MAX_BYTES }, { status: 413 });

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "payload inválido", detail: "no es JSON" }, { status: 400 });
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) return NextResponse.json({ error: "payload inválido", detail: "se esperaba un objeto" }, { status: 400 });
  const props = (body as { props?: unknown }).props;
  if (!Array.isArray(props) || props.length > MAX_PROPS) {
    return NextResponse.json({ error: "payload inválido", detail: `props debe ser un arreglo de como máximo ${MAX_PROPS} elementos` }, { status: 400 });
  }

  try {
    await sql(
      `insert into agent_learning (id, body, updated_at) values (1, $1::jsonb, now())
       on conflict (id) do update set body = excluded.body, updated_at = excluded.updated_at`,
      [JSON.stringify(body)],
    );
    return NextResponse.json({ ok: true, props: props.length });
  } catch (err) {
    console.error("[agent-learning] no se pudo guardar", err);
    return NextResponse.json({ error: "base de datos no disponible" }, { status: 503 });
  }
}
