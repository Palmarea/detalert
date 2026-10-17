"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { FILTERS, URGENCY, matches, urgencyReason } from "@/lib/payments/catalog";
import { useNow, usePaymentStream } from "@/hooks/usePaymentStream";
import { EventCard } from "./EventCard";
import { EventDetail } from "./EventDetail";
import { UserFoot } from "./UserFoot";
import type { ResolutionAction } from "@/lib/payments/types";

interface Toast { action: ResolutionAction; id: string; name: string }

export function Monitor({ user }: { user: { name: string; role: string } }) {
  const { state, connection, select, close, setFilter, setUrgency, setQuery, setLive } = usePaymentStream();
  const [toast, setToast] = useState<Toast | null>(null);
  const now = useNow();
  const [open, setOpen] = useState(false); // panel de detalle en móvil
  const mainRef = useRef<HTMLElement>(null);

  const items = useMemo(
    () => state.events.filter((e) => matches(e, state.filter, state.q, state.urgency)),
    [state.events, state.filter, state.q, state.urgency],
  );
  const urgentCount = useMemo(() => state.events.filter((e) => urgencyReason(e)).length, [state.events]);
  const urgencyCount = { urgent: urgentCount, normal: state.events.length - urgentCount, all: state.events.length };
  const selected = state.events.find((e) => e.id === state.selected);

  const stats = useMemo(() => {
    const ev = state.events;
    const ok = ev.filter((e) => e.type === "payment.succeeded" && e.data.currency === "PEN").reduce((a, e) => a + e.data.amount, 0);
    return {
      total: ev.length,
      ok: "S/ " + Math.round(ok / 100).toLocaleString("es-PE"),
      bad: ev.filter((e) => e.type === "payment.failed" || e.type === "chargeback.opened").length,
    };
  }, [state.events]);

  const pick = useCallback((id: string) => {
    select(id);
    mainRef.current?.scrollTo({ top: 0 });
    setOpen(true);
  }, [select]);

  /* Aprobar / rechazar: guarda en la DB, saca el caso de la bandeja y avisa. Devuelve el error a mostrar, o null. */
  const resolve = useCallback(async (id: string, action: ResolutionAction, note: string) => {
    const ev = state.events.find((e) => e.id === id);
    try {
      const res = await fetch(`/api/events/${encodeURIComponent(id)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, note }),
      });
      if (res.status === 401) {
        location.assign("/login?expired=1");
        return null;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 409 || res.status === 404) close([id]); // ya no está abierto
        return body.error ?? "No se pudo guardar. Intenta de nuevo.";
      }
      // Pasar al siguiente caso de la lista visible (respeta filtros), o al anterior si era el último
      const i = items.findIndex((e) => e.id === id);
      const next = items[i + 1] ?? items[i - 1];
      close([id]);
      if (next) select(next.id);
      setToast({ action, id, name: ev?.data.customer.name ?? id });
      return null;
    } catch {
      return "Sin conexión con el servidor. La decisión no se guardó.";
    }
  }, [state.events, items, close, select]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  // Navegación con ↑/↓ o j/k
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.target as HTMLElement).matches("input") || !["ArrowDown", "ArrowUp", "j", "k"].includes(ev.key) || !items.length) return;
      let i = items.findIndex((e) => e.id === state.selected);
      i = ev.key === "ArrowDown" || ev.key === "j" ? Math.min(items.length - 1, i + 1) : Math.max(0, i - 1);
      select(items[i].id);
      document.querySelector(`[data-id="${items[i].id}"]`)?.scrollIntoView({ block: "nearest" });
      ev.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [items, state.selected, select]);

  const n = state.pending.length;
  const liveLabel = connection === "error" ? "Sin conexión" : state.live ? "En vivo" : "En pausa";

  return (
    <div className={`app${open ? " open" : ""}`}>
      <aside>
        <div className="side-head">
          <div className="brand">
            <h1>Monitor de pagos</h1>
            <Link className="nav-link" href="/historial">Historial</Link>
            <button className="live" data-on={state.live} data-conn={connection} title="Pausar o reanudar el stream" onClick={() => setLive(!state.live)}>
              <span className="dot" />
              <span>{liveLabel}</span>
            </button>
          </div>
          <div className="urgency" role="group" aria-label="Filtrar por urgencia">
            {URGENCY.map(([k, l]) => (
              <button key={k} className="seg" data-k={k} data-hot={k === "urgent" && urgentCount > 0} aria-pressed={state.urgency === k} onClick={() => setUrgency(k)}>
                <span>{l}</span>
                <b className="num">{urgencyCount[k]}</b>
              </button>
            ))}
          </div>
          <div className="stats">
            <div className="stat"><span>Eventos</span><b className="num">{stats.total}</b></div>
            <div className="stat"><span>Aprobado</span><b className="num">{stats.ok}</b></div>
            <div className="stat"><span>Fallidos</span><b className="num">{stats.bad}</b></div>
          </div>
          <div className="tools">
            <input type="search" placeholder="Buscar por ID, cliente o comercio" aria-label="Buscar eventos" onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="chips" role="group" aria-label="Filtrar por estado">
            {FILTERS.map(([k, l]) => (
              <button key={k} className="chip" aria-pressed={state.filter === k} onClick={() => setFilter(k)}>{l}</button>
            ))}
          </div>
        </div>
        {n > 0 && (
          <button className="newbar" onClick={() => setLive(true)}>
            {n} evento{n > 1 ? "s" : ""} nuevo{n > 1 ? "s" : ""} en pausa · mostrar
          </button>
        )}
        <div className="list" role="list">
          {items.length ? (
            items.map((e) => (
              <EventCard
                key={e.id}
                event={e}
                now={now}
                selected={state.selected === e.id}
                unread={state.unread.has(e.id)}
                urgent={urgencyReason(e)}
                fresh={state.freshId === e.id}
                onSelect={pick}
              />
            ))
          ) : (
            <div className="empty">
              {!state.events.length
                ? "Esperando eventos de pago…"
                : state.urgency === "urgent" && !urgentCount
                  ? "Sin eventos urgentes por ahora. Los nuevos aparecerán aquí en cuanto lleguen."
                  : "Ningún evento coincide con el filtro."}
            </div>
          )}
        </div>
        <UserFoot user={user} />
      </aside>
      <main ref={mainRef}>
        {selected ? (
          <EventDetail
            event={selected}
            user={user}
            onResolve={(action, note) => resolve(selected.id, action, note)}
            onBack={() => setOpen(false)}
          />
        ) : (
          <div className="placeholder">
            <p>
              {state.events.length
                ? "Selecciona un caso de la izquierda para ver su detalle y decidirlo."
                : "No hay casos abiertos. Cuando la fuente envíe eventos (npm run feed), aparecerán aquí."}
            </p>
          </div>
        )}
      </main>
      {toast && (
        <div className={`toast s-${toast.action === "approved" ? "ok" : "bad"}`} role="status">
          <span>
            <b>{toast.action === "approved" ? "Aprobado" : "Rechazado"}</b> · {toast.name}. Archivado y notificación en cola.
          </span>
          <Link href={`/historial?q=${encodeURIComponent(toast.id)}`}>Ver en historial</Link>
        </div>
      )}
    </div>
  );
}
