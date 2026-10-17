/* Entrada de eventos. El mecanismo real aún no está definido (webhook, cola, pull a un API…);
   cualquiera que sea, debe terminar llamando a POST /api/ingest o a saveEvents().
   adaptIncoming() es el único lugar a ajustar cuando se conozca el formato real. */
import type { Decision } from "./decision";
import type { PaymentEvent } from "./types";

export interface Incoming {
  event: PaymentEvent;
  context?: Decision;
}

/* Acepta { events: [...] }, un arreglo, o un solo elemento.
   Cada elemento: { event, context } o el evento plano. */
export function adaptIncoming(body: unknown): Incoming[] {
  const list: unknown[] = Array.isArray(body) ? body : ((body as { events?: unknown[] })?.events ?? [body]);
  return list.map((item, i) => {
    const o = (item ?? {}) as { event?: PaymentEvent; context?: Decision } & Partial<PaymentEvent>;
    const e = (o.event ?? o) as PaymentEvent;
    if (!e.id || !e.type || !e.created_at || !e.data?.payment_id) throw new Error(`Elemento ${i}: falta id, type, created_at o data.payment_id`);
    return {
      event: { id: e.id, type: e.type, created_at: e.created_at, data: e.data },
      context: o.context,
    };
  });
}
