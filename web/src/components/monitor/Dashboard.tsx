"use client";
/* Panel: semáforo de la bandeja, indicadores con su propio color y espectros de los casos abiertos.
   Se refresca solo cada 5 s desde /api/dashboard. */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { THRESHOLDS, typeInfo } from "@/lib/payments/catalog";
import { money } from "@/lib/payments/format";
import { AGE_MIN, HIGH_AMOUNT, SIGNALS, SIGNAL_ORDER, countSignals, riskSpectrum, signal, toneOf, type Signal, type Tone } from "@/lib/payments/signal";
import type { DashboardStats } from "@/lib/payments/repo";
import type { Currency, PaymentEvent } from "@/lib/payments/types";
import { useNow } from "@/hooks/usePaymentStream";
import { SignalLight, SignalStrip, SpectrumBar } from "./Signals";
import { UserFoot } from "./UserFoot";

interface Data { open: PaymentEvent[]; stats: DashboardStats }

const POLL_MS = 5000;
const TONE_LABEL: Record<Tone, string> = { ok: "En rango", warn: "Atención", bad: "Crítico" };
const ageMin = (e: PaymentEvent, now: number) => Math.max(0, (now - +new Date(e.created_at)) / 60000);
const fmtMin = (m: number) => (m < 60 ? `${Math.round(m)} min` : `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`);
const short = (cents: number, cur: Currency) => (cur === "USD" ? "US$ " : "S/ ") + Math.round(cents / 100).toLocaleString("es-PE");

export function Dashboard({ user }: { user: { name: string; role: string } }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<number | null>(null);
  const now = useNow(5000);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const res = await fetch("/api/dashboard", { cache: "no-store" });
        if (res.status === 401) return location.assign("/login?expired=1");
        if (!res.ok) throw new Error();
        const next: Data = await res.json();
        if (stop) return;
        setData(next);
        setError(null);
        setUpdated(Date.now());
      } catch {
        if (!stop) setError("No se pudo actualizar el panel. ¿Está levantada la base de datos?");
      }
      if (!stop) timer = setTimeout(load, POLL_MS);
    };
    load();
    return () => { stop = true; clearTimeout(timer); };
  }, []);

  const open = useMemo(() => data?.open ?? [], [data]);
  const k = useMemo(() => kpis(open, now), [open, now]);
  const s = data?.stats;
  const resolved = s ? s.today.approved + s.today.rejected : 0;
  const received = s ? s.intake.approved + s.intake.rejected + s.intake.review : 0;
  const autoShare = received ? (s!.intake.approved + s!.intake.rejected) / received : 0;

  return (
    <div className="dash">
      <header className="dash-top">
        <h1>Panel</h1>
        <nav>
          <Link className="nav-link" href="/">Pendientes</Link>
          <Link className="nav-link" href="/historial">Historial</Link>
        </nav>
        <span className="dash-upd num">{error ? <span className="t-bad">{error}</span> : updated ? `Actualizado ${new Date(updated).toLocaleTimeString("es-PE")}` : "Cargando…"}</span>
        <UserFoot user={user} />
      </header>

      <div className="dash-body">
        <section className="kpis" aria-label="Indicadores">
          <Kpi label="Pendientes en bandeja" value={String(open.length)} tone={toneOf(open.length, 15, 30)} note="Ámbar desde 15 · rojo desde 30" />
          <Kpi
            label="Calificados por el agente"
            value={received ? `${Math.round(autoShare * 100)} %` : "—"}
            tone={received ? (autoShare >= 0.7 ? "ok" : autoShare >= 0.5 ? "warn" : "bad") : "ok"}
            note={received ? `${received - s!.intake.review} de ${received} recibidos hoy` : "Sin eventos hoy"}
          />
          <Kpi label="Urgentes (rojo)" value={String(k.counts.red)} tone={k.counts.red ? "bad" : "ok"} note={k.counts.red ? "Requieren acción inmediata" : "Ninguno pendiente"} />
          <Kpi label="Monto expuesto" value={short(k.exposed.PEN, "PEN")} sub={k.exposed.USD ? `+ ${short(k.exposed.USD, "USD")}` : undefined} tone={toneOf(k.exposedShare, 0.3, 0.6)} note={`${Math.round(k.exposedShare * 100)} % del monto abierto está en rojo o ámbar`} />
          <Kpi label="Riesgo promedio" value={open.length ? String(Math.round(k.avgRisk)) : "—"} tone={toneOf(k.avgRisk, 40, 70)} note="Sobre 100">
            {open.length > 0 && <SpectrumBar s={riskSpectrum(Math.round(k.avgRisk))} compact />}
          </Kpi>
          <Kpi label="Caso más antiguo" value={open.length ? fmtMin(k.maxAge) : "—"} tone={toneOf(k.maxAge, AGE_MIN.warn, AGE_MIN.bad)} note={k.late ? `${k.late} fuera de plazo (≥ ${AGE_MIN.bad} min)` : `Plazo interno: ${AGE_MIN.bad} min`} />
          <Kpi
            label="Resolución media hoy"
            value={s?.today.avgMinutes != null ? fmtMin(s.today.avgMinutes) : "—"}
            tone={s?.today.avgMinutes != null ? toneOf(s.today.avgMinutes, AGE_MIN.warn, AGE_MIN.bad) : "ok"}
            note={`${resolved} resuelto${resolved === 1 ? "" : "s"} hoy por analistas`}
          />
        </section>

        <div className="dash-grid">
          <section className="section">
            <div className="sec-head"><h3>Semáforo de la bandeja</h3><span className="sample num">{open.length} pendientes</span></div>
            <SignalStrip counts={k.counts} />
            <ul className="reasons">
              {SIGNAL_ORDER.filter((x) => x !== "green").map((x) => (
                <li key={x}>
                  <span className={`ldot b-${SIGNALS[x].tone}`} />
                  <b>{SIGNALS[x].label}</b>
                  <span>{k.reasons[x].length ? k.reasons[x].map(([r, n]) => `${r} (${n})`).join(" · ") : "Sin casos"}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="section">
            <div className="sec-head"><h3>Distribución de riesgo</h3><span className="sample">Pendientes por puntaje</span></div>
            <RiskHistogram events={open} />
          </section>

          <section className="section span-2">
            <div className="sec-head"><h3>Espectro de casos: riesgo × monto</h3><span className="sample">Clic en un punto para abrir el caso</span></div>
            <Scatter events={open} />
          </section>

          <section className="section">
            <div className="sec-head"><h3>Casos críticos</h3><Link className="nav-link" href="/">Ir a la bandeja</Link></div>
            <Critical events={open} now={now} />
          </section>

          <section className="section">
            <div className="sec-head"><h3>Calificación del agente hoy</h3><span className="sample num">{received} recibidos</span></div>
            {s && received ? <Intake s={s} /> : <p className="muted-note">Aún no llegan eventos hoy.</p>}
          </section>

          <section className="section span-2">
            <div className="sec-head"><h3>Resueltos hoy por analistas</h3><span className="sample num">{s ? `${s.today.urgent} urgentes` : "—"}</span></div>
            {s && resolved ? <Resolved s={s} /> : <p className="muted-note">Aún no hay casos pendientes resueltos hoy.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}

function kpis(open: PaymentEvent[], now: number) {
  const counts = countSignals(open);
  const exposed = { PEN: 0, USD: 0 };
  const total = { PEN: 0, USD: 0 };
  const reasons: Record<Signal, Map<string, number>> = { red: new Map(), amber: new Map(), green: new Map() };
  let risk = 0, maxAge = 0, late = 0;
  for (const e of open) {
    const sg = signal(e);
    const d = e.data;
    total[d.currency] += d.amount;
    if (sg.signal !== "green") exposed[d.currency] += d.amount;
    // Agrupa motivos sin el número variable: «Riesgo 82» → «Riesgo alto»
    const key = sg.reason.replace(/^Riesgo \d+$/, "Riesgo alto").replace(/ \(\d+\)$/, "");
    reasons[sg.signal].set(key, (reasons[sg.signal].get(key) ?? 0) + 1);
    risk += d.risk_score;
    const a = ageMin(e, now);
    maxAge = Math.max(maxAge, a);
    if (a >= AGE_MIN.bad) late++;
  }
  // Participación expuesta: USD llevado a la escala de PEN con la proporción de los umbrales (sin tipo de cambio real)
  const fx = HIGH_AMOUNT.PEN / HIGH_AMOUNT.USD;
  const sum = (o: typeof total) => o.PEN + o.USD * fx;
  const top = (m: Map<string, number>) => [...m].sort((a, b) => b[1] - a[1]).slice(0, 4);
  return {
    counts, exposed, late, maxAge,
    exposedShare: sum(total) ? sum(exposed) / sum(total) : 0,
    avgRisk: open.length ? risk / open.length : 0,
    reasons: { red: top(reasons.red), amber: top(reasons.amber), green: [] as [string, number][] },
  };
}

function Kpi({ label, value, sub, tone, note, children }: { label: string; value: string; sub?: string; tone: Tone; note: string; children?: React.ReactNode }) {
  return (
    <div className="kpi">
      <div className="kpi-head">
        <span>{label}</span>
        <span className={`pill s-${tone}`}><span className={`ldot b-${tone}`} />{TONE_LABEL[tone]}</span>
      </div>
      <b className="kpi-val num">{value}{sub && <small>{sub}</small>}</b>
      {children}
      <small className="kpi-note">{note}</small>
    </div>
  );
}

/* Histograma de 10 tramos; cada barra toma el color de la zona de riesgo en la que cae */
function RiskHistogram({ events }: { events: PaymentEvent[] }) {
  const bins = Array.from({ length: 10 }, (_, i) => ({ from: i * 10, n: 0 }));
  events.forEach((e) => bins[Math.min(9, Math.floor(e.data.risk_score / 10))].n++);
  const max = Math.max(1, ...bins.map((b) => b.n));
  return (
    <div className="hist" role="img" aria-label={`Distribución de riesgo: ${bins.map((b) => `${b.from}–${b.from + 9}: ${b.n}`).join(", ")}`}>
      <div className="hist-bars">
        {bins.map((b) => (
          <div key={b.from} className="hist-col" data-tip={`Riesgo ${b.from}–${b.from + 9}: ${b.n} caso${b.n === 1 ? "" : "s"}`}>
            <span className="hist-n num">{b.n || ""}</span>
            <i className={`b-${toneOf(b.from, 40, 70)}`} style={{ height: `${(b.n / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="hist-axis num">{bins.map((b) => <span key={b.from}>{b.from}</span>)}</div>
      <div className="hist-zones"><span className="z-ok">Bajo &lt; 40</span><span className="z-warn">Revisión 40–69</span><span className="z-bad">Bloqueo ≥ 70</span></div>
    </div>
  );
}

/* Dispersión: x = riesgo, y = monto relativo al umbral. Fondo con las zonas; puntos con el color de su semáforo. */
function Scatter({ events }: { events: PaymentEvent[] }) {
  const [tip, setTip] = useState<{ x: number; y: number; e: PaymentEvent } | null>(null);
  // El SVG se dibuja al ancho real del contenedor para que el texto no escale con él
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([en]) => setW(Math.max(280, Math.round(en.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = 280, P = { l: 40, r: 12, t: 14, b: 26 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const YMAX = 2; // 2× el umbral; lo que pasa queda en el borde
  const X = (r: number) => P.l + (r / 100) * iw;
  const Y = (ratio: number) => P.t + ih - (Math.min(ratio, YMAX) / YMAX) * ih;
  return (
    <div className="scatter" ref={box} onMouseLeave={() => setTip(null)}>
      {!events.length && <p className="muted-note">Sin casos abiertos.</p>}
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Casos abiertos por riesgo y monto">
        {/* zonas de riesgo y franja sobre el umbral de monto */}
        <rect x={X(0)} y={P.t} width={X(40) - X(0)} height={ih} className="zone z-ok" />
        <rect x={X(40)} y={P.t} width={X(70) - X(40)} height={ih} className="zone z-warn" />
        <rect x={X(70)} y={P.t} width={X(100) - X(70)} height={ih} className="zone z-bad" />
        <rect x={P.l} y={P.t} width={iw} height={Y(1) - P.t} className="zone z-band" />
        <line x1={P.l} x2={W - P.r} y1={Y(1)} y2={Y(1)} className="axis-ref" />
        <text x={W - P.r - 4} y={Y(1) - 5} textAnchor="end" className="axis-lbl">umbral de monto</text>
        {(W < 480 ? [0, 20, 40, 60, 80, 100] : [0, 20, 40, 60, 70, 80, 100]).map((v) => (
          <text key={v} x={X(v)} y={H - 8} textAnchor="middle" className="axis-lbl">{v}</text>
        ))}
        {[0, 0.5, 1, 1.5, 2].map((v) => (
          <text key={v} x={P.l - 6} y={Y(v) + 4} textAnchor="end" className="axis-lbl">{v === 2 ? "≥2×" : `${v}×`}</text>
        ))}
        {events.map((e) => {
          const d = e.data;
          const sg = signal(e).signal;
          const cx = X(d.risk_score), cy = Y(d.amount / HIGH_AMOUNT[d.currency]);
          return (
            <a key={e.id} href={`/?id=${encodeURIComponent(e.id)}`} aria-label={`${d.customer.name}, riesgo ${d.risk_score}, ${money(d.amount, d.currency)}`}>
              <circle cx={cx} cy={cy} r={12} className="hit" onMouseEnter={() => setTip({ x: cx / W, y: cy / H, e })} onFocus={() => setTip({ x: cx / W, y: cy / H, e })} />
              <circle cx={cx} cy={cy} r={5} className={`pt f-${SIGNALS[sg].tone}`} data-active={tip?.e.id === e.id} />
            </a>
          );
        })}
      </svg>
      <div className="scatter-axis"><span>Riesgo →</span><span>Monto vs umbral ↑</span></div>
      {tip && (
        <div className="viz-tip" style={{ left: `${tip.x * 100}%`, top: `${tip.y * 100}%` }}>
          <b>{tip.e.data.customer.name}</b>
          <span className="num">{money(tip.e.data.amount, tip.e.data.currency)} · riesgo {tip.e.data.risk_score}</span>
          <span><span className={`ldot b-${SIGNALS[signal(tip.e).signal].tone}`} /> {signal(tip.e).reason}</span>
        </div>
      )}
    </div>
  );
}

function Critical({ events, now }: { events: PaymentEvent[]; now: number }) {
  const rank = { red: 0, amber: 1, green: 2 };
  const list = [...events]
    .filter((e) => signal(e).signal !== "green")
    .sort((a, b) => rank[signal(a).signal] - rank[signal(b).signal] || b.data.risk_score - a.data.risk_score)
    .slice(0, 6);
  if (!list.length) return <p className="muted-note">Todo en verde. Nada que atender.</p>;
  return (
    <ul className="crit">
      {list.map((e) => {
        const sg = signal(e);
        const age = ageMin(e, now);
        return (
          <li key={e.id}>
            <Link href={`/?id=${encodeURIComponent(e.id)}`}>
              <SignalLight value={sg.signal} size="sm" />
              <span className="crit-main">
                <b>{e.data.customer.name}</b>
                <small>{sg.reason} · {typeInfo(e.type).label}</small>
              </span>
              <span className="crit-spec">
                <SpectrumBar s={riskSpectrum(e.data.risk_score)} compact />
                <small className="num">{e.data.risk_score}</small>
              </span>
              <span className="crit-amt num">
                {money(e.data.amount, e.data.currency)}
                <small className={`t-${toneOf(age, AGE_MIN.warn, AGE_MIN.bad)}`}>{fmtMin(age)}</small>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/* De lo recibido hoy: qué aprobó o bloqueó el agente solo y qué cayó en la zona de revisión (bandeja) */
function Intake({ s }: { s: DashboardStats }) {
  const rows = [
    { k: "approved", label: `Aprobados · riesgo < ${THRESHOLDS.REVIEW}`, n: s.intake.approved, cls: "ok" },
    { k: "review", label: `Revisión ${THRESHOLDS.REVIEW}–${THRESHOLDS.BLOCK - 1} → bandeja`, n: s.intake.review, cls: "warn" },
    { k: "rejected", label: `Bloqueados · riesgo ≥ ${THRESHOLDS.BLOCK}`, n: s.intake.rejected, cls: "bad" },
  ];
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.k} data-tip={`${r.label}: ${r.n}`}>
          <span>{r.label}</span>
          <span className="bar"><i className={`b-${r.cls}`} style={{ width: `${(r.n / max) * 100}%` }} /></span>
          <b className="num">{r.n}</b>
        </li>
      ))}
    </ul>
  );
}

function Resolved({ s }: { s: DashboardStats }) {
  const { approved, rejected } = s.today;
  const total = approved + rejected;
  const maxH = Math.max(1, ...s.hourly.map((h) => h.approved + h.rejected));
  return (
    <div className="resolved-grid">
      <div>
        <div className="split">
          <i className="b-ok" style={{ flexGrow: approved }} />
          <i className="b-bad" style={{ flexGrow: rejected }} />
        </div>
        <div className="legend">
          <span><span className="ldot b-ok" />Aprobados <b className="num">{approved}</b> ({Math.round((approved / total) * 100)} %)</span>
          <span><span className="ldot b-bad" />Rechazados <b className="num">{rejected}</b></span>
        </div>
        <ul className="hbars">
          {s.analysts.map((a) => (
            <li key={a.name} data-tip={`${a.name}: ${a.approved} aprobados, ${a.rejected} rechazados`}>
              <span>{a.name}</span>
              <span className="bar stack">
                <i className="b-ok" style={{ width: `${(a.approved / total) * 100}%` }} />
                <i className="b-bad" style={{ width: `${(a.rejected / total) * 100}%` }} />
              </span>
              <b className="num">{a.approved + a.rejected}</b>
            </li>
          ))}
        </ul>
      </div>
      <div className="hours" role="img" aria-label={`Resueltos por hora: ${s.hourly.map((h) => `${h.hour}h ${h.approved + h.rejected}`).join(", ")}`}>
        {s.hourly.map((h) => (
          <div key={h.hour} className="hour" data-tip={`${h.hour}:00 · ${h.approved} aprobados, ${h.rejected} rechazados`}>
            <span className="hour-col" style={{ height: `${((h.approved + h.rejected) / maxH) * 100}%` }}>
              <i className="b-bad" style={{ flexGrow: h.rejected }} />
              <i className="b-ok" style={{ flexGrow: h.approved }} />
            </span>
            <small className="num">{h.hour}h</small>
          </div>
        ))}
      </div>
    </div>
  );
}
