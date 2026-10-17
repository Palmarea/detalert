/* Semaforización y espectros: un solo lugar para los umbrales que colorean casos e indicadores.
   - signal(): rojo / ámbar / verde de cada caso (rojo = urgente, ver urgencyReason)
   - spectra(): posición de cada valor del caso en su escala (riesgo, monto, confianza, antigüedad, plazo) */
import { THRESHOLDS as T, urgencyReason } from "./catalog";
import { money } from "./format";
import type { PaymentEvent } from "./types";

export type Signal = "red" | "amber" | "green";
export type Tone = "ok" | "warn" | "bad";

export const SIGNALS: Record<Signal, { label: string; tone: Tone; hint: string }> = {
  red: { label: "Rojo", tone: "bad", hint: "Actuar ya" },
  amber: { label: "Ámbar", tone: "warn", hint: "Revisar" },
  green: { label: "Verde", tone: "ok", hint: "Sin alertas" },
};
export const SIGNAL_ORDER: Signal[] = ["red", "amber", "green"];

/* Umbral de monto alto (el mismo de urgencyReason y la regla R-21), en céntimos */
export const HIGH_AMOUNT = { PEN: 300000, USD: 80000 } as const;
/* Antigüedad de un caso abierto: ámbar desde 10 min, rojo desde 30 min */
export const AGE_MIN = { warn: 10, bad: 30 };

export function signal(e: PaymentEvent): { signal: Signal; reason: string } {
  const urgent = urgencyReason(e);
  if (urgent) return { signal: "red", reason: urgent };
  const d = e.data;
  if (d.risk_score >= T.REVIEW) return { signal: "amber", reason: `Zona de revisión (${d.risk_score})` };
  if (d.amount > HIGH_AMOUNT[d.currency] && e.type !== "refund.created") return { signal: "amber", reason: "Monto sobre el umbral" };
  if (e.type === "payment.failed") return { signal: "amber", reason: "Pago fallido" };
  return { signal: "green", reason: "Sin alertas" };
}

export const toneOf = (v: number, warn: number, bad: number): Tone => (v >= bad ? "bad" : v >= warn ? "warn" : "ok");

/* Un valor ubicado en su escala. pos, zones y marks van de 0 a 1.
   zones: dónde empieza el ámbar y dónde el rojo (con invert, dónde empieza el ámbar y dónde el verde). */
export interface Spectrum {
  key: string;
  label: string;
  value: string;
  pos: number;
  tone: Tone;
  zones: [number, number];
  marks: { at: number; label: string }[];
  invert?: boolean;
  hint: string;
}

const clamp = (n: number) => Math.max(0, Math.min(1, n));
const mins = (ms: number) => Math.max(0, Math.round(ms / 60000));
const dur = (m: number) => (m < 60 ? `${m} min` : m < 1440 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.floor(m / 1440)} d`);

export function riskSpectrum(score: number): Spectrum {
  return {
    key: "risk", label: "Riesgo", value: `${score} / 100`, pos: score / 100, tone: toneOf(score, T.REVIEW, T.BLOCK), zones: [T.REVIEW / 100, T.BLOCK / 100],
    marks: [{ at: T.REVIEW / 100, label: String(T.REVIEW) }, { at: T.BLOCK / 100, label: String(T.BLOCK) }],
    hint: score >= T.BLOCK ? "Sobre el umbral de bloqueo" : score >= T.REVIEW ? "Zona de revisión" : "Bajo",
  };
}

/* Monto relativo al umbral de monto alto. La escala llega a 2× el umbral; más allá queda al tope. */
export function amountSpectrum(e: PaymentEvent): Spectrum {
  const d = e.data;
  const ratio = d.amount / HIGH_AMOUNT[d.currency];
  return {
    key: "amount", label: "Monto vs umbral", value: `${Math.round(ratio * 100)} %`, pos: clamp(ratio / 2), tone: toneOf(ratio, 0.75, 1), zones: [0.375, 0.5],
    marks: [{ at: 0.5, label: money(HIGH_AMOUNT[d.currency], d.currency).replace(/[.,]00$/, "") }],
    hint: ratio > 1 ? `${ratio.toFixed(1)}× el umbral` : "Bajo el umbral",
  };
}

export function spectra(e: PaymentEvent, now = Date.now()): Spectrum[] {
  const d = e.data;
  const out = [riskSpectrum(d.risk_score), amountSpectrum(e)];
  const conf = e.context?.confidence;
  if (conf != null)
    out.push({
      key: "conf", label: "Confianza del motor", value: `${conf} %`, pos: conf / 100, tone: conf < 70 ? "bad" : conf < 85 ? "warn" : "ok", zones: [0.7, 0.85],
      marks: [{ at: 0.7, label: "70" }, { at: 0.85, label: "85" }], invert: true,
      hint: conf < 70 ? "Baja: verificar a mano" : conf < 85 ? "Media" : "Alta",
    });
  if (!e.resolution) {
    const m = mins(now - +new Date(e.created_at));
    out.push({
      key: "age", label: "Tiempo en bandeja", value: dur(m), pos: clamp(m / 60), tone: toneOf(m, AGE_MIN.warn, AGE_MIN.bad), zones: [AGE_MIN.warn / 60, AGE_MIN.bad / 60],
      marks: [{ at: AGE_MIN.warn / 60, label: `${AGE_MIN.warn}m` }, { at: AGE_MIN.bad / 60, label: `${AGE_MIN.bad}m` }],
      hint: m >= AGE_MIN.bad ? "Fuera de plazo interno" : m >= AGE_MIN.warn ? "Acercándose al plazo" : "Dentro del plazo",
    });
  }
  if (d.respond_by) {
    // Plazo del contracargo: la escala es de 10 días; quedan menos días → más a la derecha (rojo)
    const days = Math.max(0, (+new Date(d.respond_by) - now) / 86400000);
    out.push({
      key: "due", label: "Plazo de respuesta", value: `${days.toFixed(1)} días`, pos: clamp(1 - days / 10), tone: days <= 2 ? "bad" : days <= 5 ? "warn" : "ok", zones: [0.5, 0.8],
      marks: [{ at: 0.5, label: "5 d" }, { at: 0.8, label: "2 d" }],
      hint: days <= 2 ? "Vence pronto" : "Con margen",
    });
  }
  return out;
}

export function countSignals(events: PaymentEvent[]) {
  const c: Record<Signal, number> = { red: 0, amber: 0, green: 0 };
  events.forEach((e) => c[signal(e).signal]++);
  return c;
}
