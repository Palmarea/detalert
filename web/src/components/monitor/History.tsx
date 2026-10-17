"use client";
/* Historial: casos ya aprobados o rechazados, consultados en Postgres vía /api/history. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { URGENCY } from "@/lib/payments/catalog";
import { useNow } from "@/hooks/usePaymentStream";
import type { PaymentEvent, ResolutionAction, Urgency } from "@/lib/payments/types";
import { urgencyReason } from "@/lib/payments/catalog";
import { EventCard } from "./EventCard";
import { EventDetail } from "./EventDetail";
import { UserFoot } from "./UserFoot";

type Outcome = ResolutionAction | "all";
const OUTCOMES: [Outcome, string][] = [["all", "Todos"], ["approved", "Aprobados"], ["rejected", "Rechazados"]];

interface Filters {
  q: string;
  outcome: Outcome;
  urgency: Urgency;
  analyst: string;
  from: string;
  to: string;
}

interface Page {
  events: PaymentEvent[];
  total: number;
  analysts: { email: string; name: string }[];
}

export function History({ user, initialQuery }: { user: { name: string; role: string }; initialQuery: string }) {
  const now = useNow();
  const [f, setF] = useState<Filters>({ q: initialQuery, outcome: "all", urgency: "all", analyst: "", from: "", to: "" });
  const [q, setQ] = useState(initialQuery); // texto del buscador, se aplica con una pequeña espera
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    const t = setTimeout(() => setF((p) => (p.q === q ? p : { ...p, q })), 300);
    return () => clearTimeout(t);
  }, [q]);

  const load = async (offset: number) => {
    const sp = new URLSearchParams({ offset: String(offset) });
    (Object.entries(f) as [keyof Filters, string][]).forEach(([k, v]) => v && v !== "all" && sp.set(k, v));
    setLoading(true);
    try {
      const res = await fetch(`/api/history?${sp}`, { cache: "no-store" });
      if (res.status === 401) return location.assign("/login?expired=1");
      if (!res.ok) throw new Error();
      const next: Page = await res.json();
      setPage((prev) => (offset && prev ? { ...next, events: [...prev.events, ...next.events] } : next));
      setError(null);
      if (!offset) setSelected((s) => (s && next.events.some((e) => e.id === s) ? s : (next.events[0]?.id ?? null)));
    } catch {
      setError("No se pudo consultar el historial. ¿Está levantada la base de datos?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f]);

  const events = page?.events ?? [];
  const current = events.find((e) => e.id === selected);
  const filtered = f.q || f.outcome !== "all" || f.urgency !== "all" || f.analyst || f.from || f.to;

  return (
    <div className={`app${open ? " open" : ""}`}>
      <aside>
        <div className="side-head">
          <div className="brand">
            <h1>Historial</h1>
            <Link className="nav-link" href="/">Casos abiertos</Link>
          </div>
          <div className="urgency" role="group" aria-label="Filtrar por resultado">
            {OUTCOMES.map(([k, l]) => (
              <button key={k} className="seg" aria-pressed={f.outcome === k} onClick={() => set("outcome", k)}>
                <span>{l}</span>
              </button>
            ))}
          </div>
          <div className="tools">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por ID, cliente, comercio o nota" aria-label="Buscar en el historial" />
          </div>
          <div className="h-filters">
            <label>
              <span>Desde</span>
              <input type="date" value={f.from} max={f.to || undefined} onChange={(e) => set("from", e.target.value)} />
            </label>
            <label>
              <span>Hasta</span>
              <input type="date" value={f.to} min={f.from || undefined} onChange={(e) => set("to", e.target.value)} />
            </label>
            <label className="wide">
              <span>Analista</span>
              <select value={f.analyst} onChange={(e) => set("analyst", e.target.value)}>
                <option value="">Todos</option>
                {page?.analysts.map((a) => <option key={a.email} value={a.email}>{a.name}</option>)}
              </select>
            </label>
          </div>
          <div className="chips" role="group" aria-label="Filtrar por urgencia">
            {URGENCY.map(([k, l]) => (
              <button key={k} className="chip" aria-pressed={f.urgency === k} onClick={() => set("urgency", k)}>{l}</button>
            ))}
          </div>
          <div className="h-count">
            <span className="num">{page ? `${page.total} caso${page.total === 1 ? "" : "s"}` : "Cargando…"}</span>
            {filtered && (
              <button className="link" onClick={() => { setQ(""); setF({ q: "", outcome: "all", urgency: "all", analyst: "", from: "", to: "" }); }}>
                Limpiar filtros
              </button>
            )}
          </div>
        </div>
        <div className="list" role="list" aria-busy={loading}>
          {error ? (
            <div className="empty">{error}</div>
          ) : events.length ? (
            <>
              {events.map((e) => (
                <EventCard
                  key={e.id}
                  event={e}
                  now={now}
                  selected={selected === e.id}
                  unread={false}
                  urgent={urgencyReason(e)}
                  fresh={false}
                  onSelect={(id) => { setSelected(id); setOpen(true); }}
                />
              ))}
              {page && events.length < page.total && (
                <button className="more" disabled={loading} onClick={() => load(events.length)}>
                  {loading ? "Cargando…" : `Cargar más (${page.total - events.length})`}
                </button>
              )}
            </>
          ) : (
            !loading && (
              <div className="empty">
                {filtered ? "Ningún caso archivado coincide con los filtros." : "Aún no hay casos archivados. Aprueba o rechaza uno desde Casos abiertos."}
              </div>
            )
          )}
        </div>
        <UserFoot user={user} />
      </aside>
      <main>
        {current ? (
          <EventDetail event={current} user={user} onBack={() => setOpen(false)} />
        ) : (
          <div className="placeholder">
            <p>Selecciona un caso archivado para ver quién lo decidió, cuándo, con qué nota y todo su contexto.</p>
          </div>
        )}
      </main>
    </div>
  );
}
