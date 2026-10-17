import type { Decision } from "./decision";

/* Modelo de evento de pago. Es el contrato que debe cumplir el endpoint real
   (o, si llega en otro formato, el adaptador de src/lib/payments/ingest.ts). */

export type PaymentEventType =
  | "payment.succeeded"
  | "payment.pending"
  | "payment.failed"
  | "refund.created"
  | "chargeback.opened";

export type PaymentStatus =
  | "created"
  | "authorized"
  | "captured"
  | "pending"
  | "failed"
  | "refunded"
  | "disputed";

export type Currency = "PEN" | "USD";

export interface HistoryStep {
  status: PaymentStatus;
  at: string; // ISO
  note: string;
}

export interface PaymentData {
  payment_id: string;
  amount: number; // céntimos
  currency: Currency;
  status: PaymentStatus;
  method: "card" | "wallet" | "transfer";
  brand: string;
  last4: string | null;
  customer: { name: string; email: string; doc: string };
  merchant: string;
  order_id: string;
  risk_score: number; // 0–100
  ip: string;
  country: string;
  history: HistoryStep[];
  failure_code?: string;
  failure_message?: string;
  refund_id?: string;
  dispute_reason?: string;
  respond_by?: string; // ISO
}

export interface PaymentEvent {
  id: string;
  type: PaymentEventType;
  created_at: string; // ISO
  data: PaymentData;
  context?: Decision; // contexto que llega con el evento (decisión, factores, reglas, auditoría)
  resolution?: Resolution; // presente cuando el caso ya fue marcado y archivado
}

export type ResolutionAction = "approved" | "rejected";

export interface Resolution {
  action: ResolutionAction;
  note: string | null;
  at: string; // ISO
  by: { email: string; name: string; role: string };
  notification: { channel: string; status: "queued" | "sent" | "failed" } | null;
}

/* Respuesta de GET /api/events?since=<cursor>
   - events: casos abiertos nuevos, del más antiguo al más nuevo
   - closed: ids archivados desde el cursor anterior (por este u otro analista)
   - cursor: valor opaco que el cliente devuelve en la siguiente llamada */
export interface EventsPage {
  events: PaymentEvent[];
  closed: string[];
  cursor: string;
}

export type StatusClass = "ok" | "warn" | "bad" | "info";
export type Filter = "all" | StatusClass;
export type Urgency = "urgent" | "normal" | "all";
