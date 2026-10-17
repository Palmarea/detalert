import { memo } from "react";
import { typeInfo } from "@/lib/payments/catalog";
import { money, rel } from "@/lib/payments/format";
import type { PaymentEvent } from "@/lib/payments/types";
import { AlertIcon } from "@/components/icons";

interface Props {
  event: PaymentEvent;
  now: number;
  selected: boolean;
  unread: boolean;
  urgent: string | null; // motivo de urgencia
  fresh: boolean;
  onSelect: (id: string) => void;
}

export const EventCard = memo(function EventCard({ event: e, now, selected, unread, urgent, fresh, onSelect }: Props) {
  const t = typeInfo(e.type);
  const d = e.data;
  const r = e.resolution; // en el historial: quién y cuándo lo archivó
  const method = d.last4 ? `${d.brand} ··${d.last4}` : d.brand;
  const cls = ["card", unread && "unread", fresh && "fresh", urgent && "urgent"].filter(Boolean).join(" ");
  return (
    <button className={cls} role="listitem" data-id={e.id} aria-current={selected} onClick={() => onSelect(e.id)}>
      <span className={`stripe b-${t.cls}`} />
      <span className="t">{d.customer.name}</span>
      <span className="amt num">
        {e.type === "refund.created" ? "−" : ""}
        {money(d.amount, d.currency)}
      </span>
      <span className="sub">{d.merchant} · {method}</span>
      <span className="time num">{rel(r?.at ?? e.created_at, now)}</span>
      {r ? (
        <span className="meta">
          <span className={`pill s-${r.action === "approved" ? "ok" : "bad"}`}>{r.action === "approved" ? "Aprobado" : "Rechazado"}</span>
          <span className="by">por {r.by.name}</span>
          {urgent && <span className="urgent-tag" title={urgent}><AlertIcon size={12} /></span>}
        </span>
      ) : (
        <span className="meta">
          <span className={`pill s-${t.cls}`}>{t.label}</span>
          {urgent ? <span className="urgent-tag"><AlertIcon size={12} />{urgent}</span> : <span className="tag">{e.type}</span>}
        </span>
      )}
    </button>
  );
});
