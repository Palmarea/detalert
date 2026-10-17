/* Evidencia de rechazos: catálogo de categorías e indicadores, validación de la entrada
   y la foto del caso que se guarda para análisis de riesgo futuros. */
import type { EvidenceCategory, EvidenceIndicator, EvidenceInput, PaymentData, PaymentEvent } from "./types";

export const EVIDENCE_CATEGORIES: [EvidenceCategory, string][] = [
  ["fraude_confirmado", "Fraude confirmado"],
  ["suplantacion", "Suplantación de identidad"],
  ["tarjeta_robada", "Tarjeta o cuenta robada"],
  ["patron_sospechoso", "Patrón sospechoso"],
  ["contracargo_indebido", "Contracargo indebido"],
  ["otro", "Otro"],
];
export const categoryLabel = (c: string) => EVIDENCE_CATEGORIES.find(([k]) => k === c)?.[1] ?? c;

/* Rasgos del pago que se pueden marcar como señal; value() muestra al analista qué se guardará */
export const EVIDENCE_INDICATORS: { key: EvidenceIndicator; label: string; value: (d: PaymentData) => string }[] = [
  { key: "ip", label: "IP y país", value: (d) => `${d.ip} · ${d.country}` },
  { key: "identidad", label: "Documento y correo", value: (d) => `${d.customer.doc} · ${d.customer.email}` },
  { key: "medio", label: "Medio de pago", value: (d) => (d.last4 ? `${d.brand} ··${d.last4}` : d.brand) },
  { key: "comercio", label: "Comercio", value: (d) => d.merchant },
];
export const indicatorLabel = (k: string) => EVIDENCE_INDICATORS.find((i) => i.key === k)?.label ?? k;

/* Valida lo que llega del cliente. undefined = sin evidencia; string = error a devolver. */
export function parseEvidence(raw: unknown): EvidenceInput | undefined | string {
  if (raw == null) return undefined;
  const r = raw as { category?: unknown; indicators?: unknown };
  if (!EVIDENCE_CATEGORIES.some(([k]) => k === r.category)) return "Elige una categoría para la evidencia.";
  const keys = EVIDENCE_INDICATORS.map((i) => i.key) as string[];
  const indicators = Array.isArray(r.indicators) ? [...new Set(r.indicators.filter((k): k is EvidenceIndicator => keys.includes(k as string)))] : [];
  return { category: r.category as EvidenceCategory, indicators };
}

/* Foto del caso al momento del rechazo: puntaje, factores y reglas, más los indicadores elegidos */
export function evidenceSnapshot(e: Pick<PaymentEvent, "id" | "type" | "data" | "context">, indicators: EvidenceIndicator[]) {
  const d = e.data;
  const x = e.context;
  return {
    event_id: e.id,
    type: e.type,
    payment_id: d.payment_id,
    amount: d.amount,
    currency: d.currency,
    risk_score: d.risk_score,
    failure_code: d.failure_code ?? null,
    dispute_reason: d.dispute_reason ?? null,
    factors: x?.factors ?? [],
    rules_fired: x?.rules.filter((r) => r.fired).map((r) => r.id) ?? [],
    indicators: Object.fromEntries(
      indicators.map((k) => [
        k,
        k === "ip" ? { ip: d.ip, country: d.country }
        : k === "identidad" ? { doc: d.customer.doc, email: d.customer.email, name: d.customer.name }
        : k === "medio" ? { method: d.method, brand: d.brand, last4: d.last4 }
        : { merchant: d.merchant },
      ]),
    ),
  };
}
