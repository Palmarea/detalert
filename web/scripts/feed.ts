/* Simula la fuente de eventos: genera eventos de pago con su contexto
   (decisión, factores, reglas, auditoría) y los envía a POST /api/ingest.

   Uso:
     npm run feed                      # historial inicial de 15 + un evento cada 2.5–6.5 s
     npm run feed -- --no-history      # solo eventos nuevos
     npm run feed -- --once            # envía el historial y termina
     npm run feed -- --url https://<app>.vercel.app --token <INGEST_TOKEN>

   Token: --token, o INGEST_TOKEN (del entorno o de .env.local), o "dev-ingest-token" en desarrollo.
   Despliegues protegidos de Vercel (vistas previas): definir VERCEL_AUTOMATION_BYPASS_SECRET
   con el secreto de "Protection Bypass for Automation" del proyecto. */
import { fakeEvent, mockEventsSince } from "@/lib/payments/mock";
import { explainDecision } from "@/lib/payments/decision";
import { needsReview, urgencyReason, typeInfo } from "@/lib/payments/catalog";
import { money } from "@/lib/payments/format";
import type { PaymentEvent } from "@/lib/payments/types";

try {
  process.loadEnvFile(".env.local");
} catch {}

const args = process.argv.slice(2);
const flag = (f: string) => args.includes(f);
const opt = (f: string) => (args.includes(f) ? args[args.indexOf(f) + 1] : undefined);

const BASE = opt("--url") ?? process.env.FEED_URL ?? "http://localhost:3000";
const TOKEN = opt("--token") ?? (process.env.INGEST_TOKEN || "dev-ingest-token");
const BYPASS = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;

const hhmmss = () => new Date().toLocaleTimeString("es-PE", { hour12: false });

function line(e: PaymentEvent) {
  const u = urgencyReason(e);
  const t = typeInfo(e.type).label.padEnd(11);
  const dest = needsReview(e) ? `→ Pendientes${u ? ` ⚠ ${u}` : ""}` : "· calificado por el agente";
  return `  ${t} ${money(e.data.amount, e.data.currency).padStart(13)}  ${e.data.customer.name.padEnd(14)} ${e.id}  ${dest}`;
}

async function send(events: PaymentEvent[]) {
  const res = await fetch(`${BASE}/api/ingest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN}`,
      ...(BYPASS ? { "x-vercel-protection-bypass": BYPASS } : {}),
    },
    body: JSON.stringify({ events: events.map((event) => ({ event, context: explainDecision(event) })) }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`HTTP ${res.status} ${body.error ?? ""}`.trim());
  return body as { received: number; inserted: number };
}

async function main() {
  console.log(`Alimentando ${BASE}/api/ingest  (Ctrl+C para detener)\n`);

  if (!flag("--no-history")) {
    const hist = mockEventsSince(null);
    const r = await send(hist);
    console.log(`[${hhmmss()}] historial: ${r.inserted} de ${r.received} guardados`);
    hist.forEach((e) => console.log(line(e)));
    console.log();
  }
  if (flag("--once")) return;

  for (;;) {
    await new Promise((r) => setTimeout(r, 2500 + Math.random() * 4000));
    const e = fakeEvent();
    try {
      await send([e]);
      console.log(`[${hhmmss()}]${line(e)}`);
    } catch (err) {
      console.error(`[${hhmmss()}] no se pudo enviar: ${(err as Error).message}. Reintento con el siguiente.`);
    }
  }
}

main().catch((err) => {
  console.error(`No se pudo conectar con ${BASE}: ${(err as Error).message}`);
  console.error("¿Está corriendo la app (npm run dev) y la base de datos (npm run db:up)?");
  process.exit(1);
});
