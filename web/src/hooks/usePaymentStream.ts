"use client";
/* Estado del monitor + polling a /api/events (casos abiertos en Postgres).
   La pausa solo afecta a la UI: el polling sigue y los eventos se acumulan en `pending`.
   Los casos que alguien archiva llegan en `closed` y salen de la bandeja. */
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { urgencyReason } from "@/lib/payments/catalog";
import type { EventsPage, Filter, PaymentEvent, Urgency } from "@/lib/payments/types";

const MAX_EVENTS = 500;
const POLL_MS = Number(process.env.NEXT_PUBLIC_EVENTS_POLL_MS) || 3000;
const MAX_BACKOFF_MS = 30000;

export type Connection = "connecting" | "online" | "error";

interface State {
  events: PaymentEvent[]; // más nuevo primero
  pending: PaymentEvent[]; // recibidos en pausa, más nuevo primero
  unread: Set<string>;
  seen: Set<string>; // dedupe: el polling puede repetir eventos
  selected: string | null;
  filter: Filter;
  urgency: Urgency;
  q: string;
  live: boolean;
  freshId: string | null;
}

type Action =
  | { type: "ingest"; events: PaymentEvent[]; initial: boolean } // events: más antiguo primero
  | { type: "close"; ids: string[] } // casos archivados (por mí u otro analista): salen de la bandeja
  | { type: "select"; id: string }
  | { type: "filter"; filter: Filter }
  | { type: "urgency"; urgency: Urgency }
  | { type: "query"; q: string }
  | { type: "setLive"; live: boolean };

const initialState: State = {
  events: [], pending: [], unread: new Set(), seen: new Set(),
  selected: null, filter: "all", urgency: "urgent", q: "", live: true, freshId: null,
};

function flush(s: State): State {
  if (!s.pending.length) return s;
  const unread = new Set(s.unread);
  s.pending.forEach((e) => unread.add(e.id));
  return { ...s, events: [...s.pending, ...s.events].slice(0, MAX_EVENTS), pending: [], unread, freshId: null };
}

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "ingest": {
      const fresh = a.events.filter((e) => !s.seen.has(e.id));
      if (!fresh.length) return s;
      const seen = new Set(s.seen);
      fresh.forEach((e) => seen.add(e.id));
      const newestFirst = [...fresh].reverse();
      if (a.initial) {
        return { ...s, seen, events: newestFirst.slice(0, MAX_EVENTS), selected: s.selected ?? (newestFirst.find((e) => urgencyReason(e)) ?? newestFirst[0]).id };
      }
      if (!s.live) return { ...s, seen, pending: [...newestFirst, ...s.pending] };
      const unread = new Set(s.unread);
      fresh.forEach((e) => unread.add(e.id));
      return { ...s, seen, unread, events: [...newestFirst, ...s.events].slice(0, MAX_EVENTS), freshId: newestFirst[0].id };
    }
    case "close": {
      const gone = new Set(a.ids.filter((id) => s.seen.has(id)));
      if (!gone.size) return s;
      const events = s.events.filter((e) => !gone.has(e.id));
      const unread = new Set([...s.unread].filter((id) => !gone.has(id)));
      // Si se cerró el seleccionado, se deselecciona; quien decide elige el siguiente visible (Monitor)
      const selected = s.selected && gone.has(s.selected) ? null : s.selected;
      return { ...s, events, unread, selected, pending: s.pending.filter((e) => !gone.has(e.id)) };
    }
    case "select": {
      const unread = new Set(s.unread);
      unread.delete(a.id);
      return { ...s, selected: a.id, unread };
    }
    case "filter":
      return { ...s, filter: a.filter };
    case "urgency":
      return { ...s, urgency: a.urgency };
    case "query":
      return { ...s, q: a.q.trim().toLowerCase() };
    case "setLive":
      return a.live ? flush({ ...s, live: true }) : { ...s, live: false };
  }
}

export function usePaymentStream(endpoint = "/api/events") {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [connection, setConnection] = useState<Connection>("connecting");
  const cursor = useRef<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let ctrl: AbortController | null = null;
    let delay = POLL_MS;

    const poll = async () => {
      ctrl = new AbortController();
      try {
        const url = new URL(endpoint, location.origin);
        if (cursor.current) url.searchParams.set("since", cursor.current);
        const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
        if (res.status === 401) {
          // La sesión venció o se revocó: volver al login sin seguir reintentando
          stopped = true;
          location.assign("/login?expired=1");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const page: EventsPage = await res.json();
        dispatch({ type: "ingest", events: page.events, initial: cursor.current === null });
        if (page.closed.length) dispatch({ type: "close", ids: page.closed });
        cursor.current = page.cursor;
        setConnection("online");
        delay = POLL_MS;
      } catch (err) {
        if (stopped) return;
        console.warn("[payments] polling falló", err);
        setConnection("error");
        delay = Math.min(delay * 2, MAX_BACKOFF_MS);
      }
      if (!stopped) timer = setTimeout(poll, delay);
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); ctrl?.abort(); };
  }, [endpoint]);

  return {
    state,
    connection,
    select: useCallback((id: string) => dispatch({ type: "select", id }), []),
    close: useCallback((ids: string[]) => dispatch({ type: "close", ids }), []),
    setFilter: useCallback((filter: Filter) => dispatch({ type: "filter", filter }), []),
    setUrgency: useCallback((urgency: Urgency) => dispatch({ type: "urgency", urgency }), []),
    setQuery: useCallback((q: string) => dispatch({ type: "query", q }), []),
    setLive: useCallback((live: boolean) => dispatch({ type: "setLive", live }), []),
  };
}

/* Reloj compartido para los "hace Ns" (el prototipo refrescaba cada 5 s). */
export function useNow(ms = 5000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
