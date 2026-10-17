import type { Filter, PaymentEvent, PaymentEventType, PaymentStatus, StatusClass, Urgency } from "./types";

export const TYPES: Record<PaymentEventType, { label: string; cls: StatusClass }> = {
  "payment.succeeded": { label: "Aprobado", cls: "ok" },
  "payment.pending": { label: "Pendiente", cls: "warn" },
  "payment.failed": { label: "Rechazado", cls: "bad" },
  "refund.created": { label: "Reembolso", cls: "info" },
  "chargeback.opened": { label: "Contracargo", cls: "bad" },
};

export const FILTERS: [Filter, string][] = [
  ["all", "Todos"],
  ["ok", "Aprobados"],
  ["warn", "Pendientes"],
  ["bad", "Fallidos"],
  ["info", "Reembolsos"],
];

export const URGENCY: [Urgency, string][] = [
  ["urgent", "Urgentes"],
  ["normal", "No urgentes"],
  ["all", "Todos"],
];

/* Criterios de urgencia (un solo lugar para ajustarlos). Devuelve el motivo, o null si no es urgente. */
export function urgencyReason(e: PaymentEvent): string | null {
  const d = e.data;
  if (e.type === "chargeback.opened") return "Contracargo con plazo";
  if (d.failure_code === "fraud_suspected") return "Bloqueo antifraude";
  if (d.risk_score >= 70) return `Riesgo ${d.risk_score}`;
  const high = d.currency === "PEN" ? d.amount > 300000 : d.amount > 80000;
  if (high && d.risk_score >= 40 && e.type !== "refund.created") return "Monto alto con riesgo";
  return null;
}

export const STEP_CLS: Record<PaymentStatus, string> = {
  created: "b-info",
  authorized: "b-ok",
  captured: "b-ok",
  pending: "b-warn",
  failed: "b-bad",
  refunded: "b-info",
  disputed: "b-bad",
};

export const typeInfo = (t: string) => TYPES[t as PaymentEventType] ?? { label: t, cls: "info" as const };

export function matches(e: PaymentEvent, filter: Filter, q: string, urgency: Urgency = "all") {
  if (urgency !== "all" && (urgencyReason(e) !== null) !== (urgency === "urgent")) return false;
  if (filter !== "all" && typeInfo(e.type).cls !== filter) return false;
  if (!q) return true;
  const d = e.data;
  return `${e.id} ${d.payment_id} ${d.customer.name} ${d.merchant} ${d.order_id}`.toLowerCase().includes(q);
}
