/* Transparencia y responsabilidad de cada evento: quién decidió, por qué, con qué reglas
   y qué quedó registrado.
   El contexto real llega junto con cada evento (POST /api/ingest) y se guarda en events.context.
   explainDecision() lo SIMULA para scripts/feed.ts: se deriva del propio evento con una semilla fija. */
import { DEMO_USERS } from "@/lib/auth/users";
import type { PaymentEvent } from "./types";

export type DeciderKind = "auto" | "human" | "external";
export type Outcome = "ok" | "warn" | "bad" | "info";

export interface Factor { label: string; points: number }
export interface RuleCheck { id: string; name: string; fired: boolean; detail: string }
export interface AuditEntry { at: string; actor: string; action: string; hash: string }

export interface Decision {
  outcome: Outcome;
  verdict: string; // «Aprobado automáticamente», «Bloqueado por regla antifraude»…
  decidedBy: { kind: DeciderKind; name: string; detail: string };
  accountable: { name: string; role: string };
  confidence: number | null; // % del motor; null cuando decidió una persona o un tercero
  policy: string;
  base: number; // puntaje base del comercio
  factors: Factor[]; // base + Σ points = risk_score
  rules: RuleCheck[];
  appeal: string;
  audit: AuditEntry[];
}

const ENGINE = "Motor antifraude v3.2.1";
const [ANALYST, SUPERVISOR] = DEMO_USERS;

/* Huella corta para entradas de auditoría creadas en el navegador (consultas al agente). */
export const auditHash = (s: string) => Array.from({ length: 8 }, (_, i) => Math.floor(seeded(s + i)() * 16).toString(16)).join("");

function seeded(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return () => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const UP = [
  "Monto por encima del promedio del cliente",
  "IP no vista antes para este cliente",
  "Varios intentos en los últimos 10 minutos",
  "Comercio con tasa de contracargos alta",
  "Horario poco habitual para este cliente",
  "Tarjeta emitida fuera de Perú",
];
const DOWN = ["Dispositivo reconocido", "Cliente con historial sin disputas", "Correo verificado hace más de 1 año", "IP y emisor en el mismo país"];

export function explainDecision(e: PaymentEvent): Decision {
  const r = seeded(e.id);
  const pick = <T,>(a: T[], n: number) => [...a].sort(() => r() - 0.5).slice(0, n);
  const hash = () => Array.from({ length: 8 }, () => Math.floor(r() * 16).toString(16)).join("");
  const d = e.data;
  const t0 = +new Date(e.created_at);
  const at = (ms: number) => new Date(t0 + ms).toISOString();

  // Factores: base + positivos + negativos = risk_score exacto
  let base = 4 + Math.floor(r() * 6);
  let downs = pick(DOWN, 1 + Math.floor(r() * 2)).map((label) => ({ label, points: -(2 + Math.floor(r() * 6)) }));
  let pos = d.risk_score - base - downs.reduce((a, f) => a + f.points, 0);
  while (pos < 0 && downs.length) { downs = downs.slice(1); pos = d.risk_score - base - downs.reduce((a, f) => a + f.points, 0); }
  if (pos < 0) { base = d.risk_score; pos = 0; }
  const ups: Factor[] = [];
  if (pos > 0) {
    const labels = pick(UP, Math.min(pos, d.risk_score >= 60 ? 3 : 1 + Math.floor(r() * 2)));
    const w = labels.map(() => 0.4 + r());
    const sw = w.reduce((a, b) => a + b, 0);
    let left = pos;
    labels.forEach((label, i) => {
      const p = i === labels.length - 1 ? left : Math.max(1, Math.round((pos * w[i]) / sw));
      left -= p;
      ups.push({ label, points: p });
    });
  }
  const factors = [...ups.sort((a, b) => b.points - a.points), ...downs];

  const velocity = d.failure_code === "fraud_suspected";
  const rules: RuleCheck[] = [
    { id: "R-03", name: "Lista de bloqueo", fired: false, detail: "Documento, correo e IP no figuran" },
    { id: "R-09", name: "Umbral de riesgo (≥ 70 bloquea)", fired: d.risk_score >= 70, detail: `Puntaje ${d.risk_score} / 100` },
    { id: "R-14", name: "Velocidad de intentos", fired: velocity, detail: velocity ? "4 intentos en 10 min (límite 3)" : "1 intento en 10 min" },
    { id: "R-21", name: "Monto alto requiere revisión (> S/ 3,000)", fired: d.amount > 300000, detail: d.amount > 300000 ? "Supera el umbral" : "Bajo el umbral" },
  ];

  const audit: AuditEntry[] = [{ at: at(-3800), actor: "Sistema", action: "Evento recibido por webhook y validado", hash: hash() }];
  const engineNote = (txt: string) => audit.push({ at: at(-2600), actor: ENGINE, action: txt, hash: hash() });

  let dec: Omit<Decision, "factors" | "rules" | "audit" | "base">;
  switch (e.type) {
    case "payment.succeeded":
      if (d.risk_score >= 40 || d.amount > 300000) {
        engineNote(d.amount > 300000 ? "Regla R-21 disparada: enviado a revisión manual" : `Puntaje ${d.risk_score}: enviado a revisión manual`);
        audit.push({ at: at(-900), actor: ANALYST.name, action: "Revisó factores y aprobó manualmente", hash: hash() });
        dec = {
          outcome: "ok", verdict: "Aprobado tras revisión manual",
          decidedBy: { kind: "human", name: ANALYST.name, detail: ANALYST.role },
          accountable: { name: ANALYST.name, role: ANALYST.role },
          confidence: null, policy: "POL-RIESGO-04 · Revisión de riesgo medio",
          appeal: "Un supervisor puede revertirla dentro de las 24 h.",
        };
      } else {
        engineNote(`Puntaje ${d.risk_score}: aprobado sin revisión`);
        dec = {
          outcome: "ok", verdict: "Aprobado automáticamente",
          decidedBy: { kind: "auto", name: ENGINE, detail: "Sin reglas disparadas" },
          accountable: { name: SUPERVISOR.name, role: SUPERVISOR.role },
          confidence: 90 + Math.floor(r() * 9), policy: "POL-RIESGO-01 · Aprobación automática de riesgo bajo",
          appeal: "No requiere acción. Se puede marcar para revisión posterior.",
        };
      }
      break;
    case "payment.pending":
      engineNote("Retenido hasta que el emisor confirme");
      dec = {
        outcome: "warn", verdict: "Retenido: esperando confirmación",
        decidedBy: { kind: "external", name: d.method === "transfer" ? d.brand : "Emisor de la tarjeta", detail: d.method === "transfer" ? "Confirmación bancaria" : "3-D Secure" },
        accountable: { name: ANALYST.name, role: ANALYST.role },
        confidence: null, policy: "POL-PAGOS-02 · Retención por autenticación pendiente",
        appeal: "Se resuelve solo al llegar el siguiente evento; si pasan 30 min, escala a analista.",
      };
      break;
    case "payment.failed":
      if (velocity || d.risk_score >= 70) {
        engineNote(velocity ? "Regla R-14 disparada: pago bloqueado" : `Puntaje ${d.risk_score}: pago bloqueado`);
        audit.push({ at: at(-600), actor: "Sistema", action: `Caso asignado a ${ANALYST.name}`, hash: hash() });
        dec = {
          outcome: "bad", verdict: "Bloqueado por regla antifraude",
          decidedBy: { kind: "auto", name: ENGINE, detail: velocity ? "Regla R-14 · velocidad" : "Regla R-09 · umbral" },
          accountable: { name: SUPERVISOR.name, role: SUPERVISOR.role },
          confidence: 80 + Math.floor(r() * 15), policy: "POL-RIESGO-07 · Bloqueo preventivo",
          appeal: "El cliente puede apelar; la revierte un supervisor tras revisar el caso.",
        };
      } else {
        engineNote(`Puntaje ${d.risk_score}: enviado al emisor`);
        dec = {
          outcome: "bad", verdict: "Rechazado por el emisor",
          decidedBy: { kind: "external", name: d.brand, detail: d.failure_message ?? "Rechazo del emisor" },
          accountable: { name: d.brand, role: "Emisor (fuera de nuestra plataforma)" },
          confidence: null, policy: "POL-PAGOS-05 · Rechazos de terceros",
          appeal: "No es apelable aquí: el cliente debe contactar a su banco.",
        };
      }
      break;
    case "refund.created":
      audit.push({ at: at(-2600), actor: d.merchant, action: "Solicitó reembolso total", hash: hash() });
      dec = {
        outcome: "info", verdict: "Reembolso solicitado por el comercio",
        decidedBy: { kind: "external", name: d.merchant, detail: "Comercio" },
        accountable: { name: d.merchant, role: "Comercio" },
        confidence: null, policy: "POL-PAGOS-09 · Reembolsos",
        appeal: "Irreversible una vez liquidado por el banco.",
      };
      break;
    case "chargeback.opened":
      audit.push({ at: at(-2600), actor: "Emisor", action: `Notificó disputa: ${d.dispute_reason ?? "sin motivo"}`, hash: hash() });
      audit.push({ at: at(-600), actor: "Sistema", action: `Caso asignado a ${SUPERVISOR.name}`, hash: hash() });
      dec = {
        outcome: "bad", verdict: "Contracargo abierto por el cliente",
        decidedBy: { kind: "external", name: "Emisor del cliente", detail: d.dispute_reason ?? "Disputa" },
        accountable: { name: SUPERVISOR.name, role: SUPERVISOR.role },
        confidence: null, policy: "POL-DISPUTAS-01 · Respuesta a contracargos",
        appeal: "Se responde con evidencia antes de la fecha límite del emisor.",
      };
      break;
  }
  audit.push({ at: e.created_at, actor: "Sistema", action: "Decisión registrada y notificada", hash: hash() });
  return { ...dec, base, factors, rules, audit };
}
