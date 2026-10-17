"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { URGENCY, matches, urgencyReason } from "@/lib/payments/catalog";
import { countSignals, signal, type Signal } from "@/lib/payments/signal";
import { useNow, usePaymentStream } from "@/hooks/usePaymentStream";
import { EventCard } from "./EventCard";
import { EventDetail } from "./EventDetail";
import { UserFoot } from "./UserFoot";
import { SignalStrip } from "./Signals";
import type { EvidenceInput, ResolutionAction } from "@/lib/payments/types";

interface Toast { action: ResolutionAction; id: string; name: string; evidence: boolean }

export function Monitor({ user, initialId }: { user: { name: string; role: string }; initialId?: string }) {
  const { state, connection, select, close, setUrgency, setQuery, setLive } = usePaymentStream();
  const [sig, setSig] = useState<Signal | null>(null); // filtro por semáforo (local a la bandeja)
  const [toast, setToast] = useState<Toast | null>(null);
  const now = useNow();
  const [open, setOpen] = useState(false); // panel de detalle en móvil
  const mainRef = useRef<HTMLElement>(null);

  // Enlace desde el panel (/?id=…): abre ese caso sin el filtro de urgencia
  useEffect(() => {
    if (!initialId) return;
    select(initialId);
    setUrgency("all");
    setOpen(true);
  }, [initialId, select, setUrgency]);

  const items = useMemo(
    () => state.events.filter((e) => matches(e, state.filter, state.q, state.urgency) && (!sig || signal(e).signal === sig)),
    [state.events, state.filter, state.q, state.urgency, sig],
  );
  const signals = useMemo(() => countSignals(state.events), [state.events]);
  const urgentCount = useMemo(() => state.events.filter((e) => urgencyReason(e)).length, [state.events]);
  const urgencyCount = { urgent: urgentCount, normal: state.events.length - urgentCount, all: state.events.length };
  const selected = state.events.find((e) => e.id === state.selected);

  const pick = useCallback((id: string) => {
    select(id);
    mainRef.current?.scrollTo({ top: 0 });
    setOpen(true);
  }, [select]);

  /* Aprobar / rechazar: guarda en la DB, saca el caso de la bandeja y avisa. Devuelve el error a mostrar, o null. */
  const resolve = useCallback(async (id: string, action: ResolutionAction, note: string, evidence?: EvidenceInput) => {
    const ev = state.events.find((e) => e.id === id);
    try {
      const res = await fetch(`/api/events/${encodeURIComponent(id)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, note, evidence }),
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
      setToast({ action, id, name: ev?.data.customer.name ?? id, evidence: !!evidence });
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
            <h1>Pendientes</h1>
            <Link className="nav-link" href="/panel">Panel</Link>
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
          <SignalStrip counts={signals} active={sig} onPick={setSig} />
          <div className="tools">
            <input type="search" placeholder="Buscar por ID, cliente o comercio" aria-label="Buscar pendientes" onChange={(e) => setQuery(e.target.value)} />
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
                ? "Sin pendientes: nada cayó en la zona de revisión (riesgo 40–69). Los que caigan aparecerán aquí."
                : state.urgency === "urgent" && !urgentCount
                  ? "Sin pendientes urgentes por ahora. Los nuevos aparecerán aquí en cuanto lleguen."
                  : sig
                    ? "Ningún caso de este color con los filtros actuales."
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
            onResolve={(action, note, evidence) => resolve(selected.id, action, note, evidence)}
            onBack={() => setOpen(false)}
          />
        ) : (
          <div className="placeholder">
            <p>
              {state.events.length
                ? "Selecciona un caso de la izquierda para ver su detalle y decidirlo."
                : "No hay casos pendientes. Aquí llegan solo los pagos con riesgo en la zona de revisión (40–69): por debajo los aprueba el agente y desde 70 los bloquea."}
            </p>
          </div>
        )}
      </main>
      {toast && (
        <div className={`toast s-${toast.action === "approved" ? "ok" : "bad"}`} role="status">
          <span>
            <b>{toast.action === "approved" ? "Aprobado" : "Rechazado"}</b> · {toast.name}. {toast.evidence ? "Guardado como evidencia; " : "Archivado y "}notificación en cola.
          </span>
          <Link href={`/historial?q=${encodeURIComponent(toast.id)}`}>Ver en historial</Link>
        </div>
      )}
    </div>
  );
}
