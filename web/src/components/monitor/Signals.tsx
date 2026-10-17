/* Piezas visuales de semaforización: semáforo, barra de conteos y espectros.
   El color nunca va solo: cada semáforo lleva su etiqueta y cada espectro su valor. */
import { THRESHOLDS as T } from "@/lib/payments/catalog";
import { SIGNALS, SIGNAL_ORDER, riskSpectrum, type Signal, type Spectrum } from "@/lib/payments/signal";

const C = { ok: "var(--ok)", warn: "var(--warn)", bad: "var(--bad)" };

/* Gradiente de la escala: verde → ámbar → rojo (o al revés con invert), con los cambios en zones */
export function gradient({ zones: [a, b], invert }: Pick<Spectrum, "zones" | "invert">) {
  const [lo, hi] = invert ? [C.bad, C.ok] : [C.ok, C.bad];
  const p = (n: number) => `${(n * 100).toFixed(1)}%`;
  return `linear-gradient(90deg, ${lo} 0%, ${lo} ${p(Math.max(0, a - 0.08))}, ${C.warn} ${p(a)}, ${C.warn} ${p(Math.max(a, b - 0.04))}, ${hi} ${p(b)}, ${hi} 100%)`;
}

/* Semáforo de tres luces; solo se enciende la del caso */
export function SignalLight({ value, size = "md" }: { value: Signal; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`light light-${size}`} role="img" aria-label={`Semáforo ${SIGNALS[value].label}`}>
      {SIGNAL_ORDER.map((s) => <i key={s} className={`s-${SIGNALS[s].tone}`} data-on={s === value} />)}
    </span>
  );
}

export function SpectrumBar({ s, compact }: { s: Spectrum; compact?: boolean }) {
  const pct = `${(s.pos * 100).toFixed(1)}%`;
  if (compact)
    return (
      <span className="spec spec-mini" title={`${s.label}: ${s.value} · ${s.hint}`}>
        <span className="spec-track" style={{ background: gradient(s) }} />
        <span className="spec-dot" style={{ left: pct }} />
      </span>
    );
  return (
    <div className="spec-row">
      <div className="spec-head">
        <span>{s.label}</span>
        <b className={`num t-${s.tone}`}>{s.value}</b>
      </div>
      <div className="spec" role="meter" aria-label={s.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.pos * 100)} aria-valuetext={`${s.value}, ${s.hint}`}>
        <span className="spec-track" style={{ background: gradient(s) }} />
        {s.marks.map((m) => <span key={m.label} className="spec-tick" style={{ left: `${m.at * 100}%` }}><small>{m.label}</small></span>)}
        <span className="spec-dot" style={{ left: pct }} />
      </div>
      <small className="spec-hint">{s.hint}</small>
    </div>
  );
}

/* Puntaje de riesgo en grande + su espectro con los umbrales nombrados y el valor marcado sobre la escala */
export function ScoreHero({ score, signal: sg, reason }: { score: number; signal: Signal; reason: string }) {
  const s = riskSpectrum(score);
  const zones = [
    { from: 0, to: T.REVIEW, label: "Aprueba el agente", tone: "ok" },
    { from: T.REVIEW, to: T.BLOCK, label: "Revisión (pendiente)", tone: "warn" },
    { from: T.BLOCK, to: 100, label: "Bloquea el agente", tone: "bad" },
  ];
  return (
    <div className="hero">
      <div className="hero-top">
        <div className="hero-score">
          <small>Puntaje de riesgo</small>
          <b className={`num t-${s.tone}`}>{score}<span>/100</span></b>
        </div>
        <div className="hero-sig">
          <SignalLight value={sg} size="lg" />
          <div>
            <b>Semáforo {SIGNALS[sg].label.toLowerCase()} · {SIGNALS[sg].hint}</b>
            <small>{reason}</small>
          </div>
        </div>
      </div>
      <div className="hero-spec" role="meter" aria-label="Puntaje de riesgo" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-valuetext={`${score} de 100, ${s.hint}`}>
        <span className="hero-bubble num" style={{ left: `${score}%` }}>{score}</span>
        <span className="spec-track" style={{ background: gradient(s) }} />
        {[T.REVIEW, T.BLOCK].map((t) => (
          <span key={t} className="hero-th" style={{ left: `${t}%` }}>
            <small><span className="th-word">Umbral de </span>{t === T.REVIEW ? "revisión" : "bloqueo"} · {t}</small>
          </span>
        ))}
        <span className="spec-dot" style={{ left: `${score}%` }} />
      </div>
      <div className="hero-zones">
        {zones.map((z) => (
          <span key={z.label} style={{ width: `${z.to - z.from}%` }} data-on={score >= z.from && (score < z.to || z.to === 100)} className={`t-${z.tone}`}>
            {z.label} {z.from}–{z.to === 100 ? 100 : z.to - 1}
          </span>
        ))}
      </div>
    </div>
  );
}

/* Conteo por color + barra apilada. Con onPick cada color filtra la lista. */
export function SignalStrip({ counts, active, onPick }: { counts: Record<Signal, number>; active?: Signal | null; onPick?: (s: Signal | null) => void }) {
  const total = counts.red + counts.amber + counts.green;
  return (
    <div className="strip">
      <div className="strip-bar" aria-hidden="true">
        {total ? SIGNAL_ORDER.map((s) => counts[s] > 0 && <i key={s} className={`b-${SIGNALS[s].tone}`} style={{ flexGrow: counts[s] }} />) : <i className="strip-empty" />}
      </div>
      <div className="strip-counts" role="group" aria-label="Semáforo de casos">
        {SIGNAL_ORDER.map((s) => (
          <button
            key={s}
            type="button"
            className="strip-item"
            aria-pressed={active === s}
            disabled={!onPick}
            onClick={() => onPick?.(active === s ? null : s)}
            title={onPick ? (active === s ? "Quitar filtro" : `Mostrar solo ${SIGNALS[s].label.toLowerCase()}`) : undefined}
          >
            <span className={`ldot b-${SIGNALS[s].tone}`} />
            <span>{SIGNALS[s].label}</span>
            <b className="num">{counts[s]}</b>
          </button>
        ))}
      </div>
    </div>
  );
}
