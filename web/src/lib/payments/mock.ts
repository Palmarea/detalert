/* Simulador de eventos (datos de ejemplo). Lo usa scripts/feed.ts para alimentar /api/ingest.
   Portado del prototipo HTML. */
import type { Currency, HistoryStep, PaymentData, PaymentEvent, PaymentEventType } from "./types";

const rnd = <T,>(a: T[]) => a[Math.floor(Math.random() * a.length)];
const NAMES = ["María Quispe", "José Huamán", "Lucía Torres", "Carlos Ramos", "Ana Flores", "Diego Vargas", "Rosa Mendoza", "Luis Castillo"];
const MERCH = ["Tienda Miraflores", "Farmacia Central", "Delivery Express", "Librería Surco", "Café Barranco", "Electro Lima"];
const METHODS: [PaymentData["method"], string][] = [["card", "Visa"], ["card", "Mastercard"], ["card", "Amex"], ["wallet", "Yape"], ["wallet", "Plin"], ["transfer", "BCP"]];
const FAILS = [["insufficient_funds", "Fondos insuficientes"], ["card_declined", "Tarjeta rechazada por el emisor"], ["expired_card", "Tarjeta vencida"], ["fraud_suspected", "Bloqueado por regla antifraude"]];
let seq = 48210;

function hex(n: number) {
  let s = "";
  while (s.length < n) s += Math.random().toString(16).slice(2);
  return s.slice(0, n);
}
const iso = (ms: number) => new Date(ms).toISOString();
const ipPart = () => Math.floor(Math.random() * 255);

/* force: genera un caso concreto (lo usa el historial inicial para que la demo no arranque vacía).
   "review" = pendiente en la parte alta de la zona de revisión y con monto alto: urgente. */
export function fakeEvent(at = Date.now(), force?: "fraud" | "chargeback" | "review"): PaymentEvent {
  const r = Math.random();
  const type: PaymentEventType =
    force === "chargeback" ? "chargeback.opened" : force === "fraud" ? "payment.failed" : force === "review" ? "payment.pending" : r < 0.45 ? "payment.succeeded" : r < 0.75 ? "payment.pending" : r < 0.9 ? "payment.failed" : r < 0.97 ? "refund.created" : "chargeback.opened";
  const [kind, brand] = rnd(METHODS);
  const name = rnd(NAMES);
  const currency: Currency = Math.random() < 0.8 ? "PEN" : "USD";
  const amount = Math.round((force === "review" ? 3200 + Math.random() * 1800 : Math.random() < 0.85 ? 15 + Math.random() * 450 : 800 + Math.random() * 4200) * 100);
  const history: HistoryStep[] = [{ status: "created", at: iso(at - 4000), note: "Intento de pago iniciado" }];
  const data: PaymentData = {
    payment_id: "pay_" + hex(14),
    amount,
    currency,
    status: "created",
    method: kind,
    brand,
    last4: kind === "card" ? String(1000 + Math.floor(Math.random() * 9000)) : null,
    customer: {
      name,
      email: name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(" ", ".") + "@correo.pe",
      doc: "DNI " + (40000000 + Math.floor(Math.random() * 39999999)),
    },
    merchant: rnd(MERCH),
    order_id: "ORD-" + seq++,
    // El puntaje decide el destino (ver THRESHOLDS): < 40 aprueba el agente, 40–69 bandeja, ≥ 70 bloquea el agente.
    // pending y chargeback caen en la zona de revisión; el fraude, en bloqueo; el resto, en riesgo bajo.
    risk_score:
      force === "review" ? 58 + Math.floor(Math.random() * 12)
      : type === "payment.pending" || type === "chargeback.opened" ? 40 + Math.floor(Math.random() * 30)
      : type === "payment.failed" && (force === "fraud" || Math.random() < 0.4) ? 72 + Math.floor(Math.random() * 20)
      : Math.floor(Math.random() * 40),
    ip: `190.${ipPart()}.${ipPart()}.${ipPart()}`,
    country: "PE",
    history,
  };

  switch (type) {
    case "payment.succeeded":
      data.status = "captured";
      history.push(
        { status: "authorized", at: iso(at - 1500), note: "Autorizado por el emisor" },
        { status: "captured", at: iso(at), note: "Fondos capturados" },
      );
      break;
    case "payment.pending":
      data.status = "pending";
      history.push({ status: "pending", at: iso(at), note: "Retenido: puntaje en zona de revisión, pasa a un analista" });
      break;
    case "payment.failed": {
      const [c, m] = data.risk_score >= 70 ? FAILS[3] : rnd(FAILS.slice(0, 3));
      data.status = "failed";
      data.failure_code = c;
      data.failure_message = m;
      history.push({ status: "failed", at: iso(at), note: m });
      break;
    }
    case "refund.created":
      data.status = "refunded";
      data.refund_id = "re_" + hex(12);
      history.push(
        { status: "captured", at: iso(at - 86400000), note: "Pago original capturado" },
        { status: "refunded", at: iso(at), note: "Reembolso total solicitado por el comercio" },
      );
      break;
    case "chargeback.opened":
      data.status = "disputed";
      data.dispute_reason = "Cliente no reconoce el cargo";
      data.respond_by = iso(at + 7 * 86400000);
      history.push(
        { status: "captured", at: iso(at - 12 * 86400000), note: "Pago original capturado" },
        { status: "disputed", at: iso(at), note: "El emisor abrió una disputa" },
      );
      break;
  }
  return { id: "evt_" + hex(16), type, created_at: iso(at), data };
}

/* Genera los eventos "ocurridos" entre since y now, igual ritmo que el prototipo
   (uno cada 2.5–6.5 s). Sin since devuelve un historial inicial de 15 eventos, 3 de ellos urgentes. */
const URGENT_AT: Record<number, "fraud" | "chargeback" | "review"> = { 11: "review", 8: "fraud", 6: "chargeback", 2: "review" };
export function mockEventsSince(since: number | null, now = Date.now(), limit = 50): PaymentEvent[] {
  const out: PaymentEvent[] = [];
  if (since === null) {
    for (let i = 14; i >= 0; i--) out.push(fakeEvent(now - i * 47000 - Math.random() * 20000, URGENT_AT[i]));
    return out;
  }
  for (let t = since + 2500 + Math.random() * 4000; t <= now && out.length < limit; t += 2500 + Math.random() * 4000) {
    out.push(fakeEvent(Math.round(t)));
  }
  return out;
}
