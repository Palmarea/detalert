"use client";
/* "Equipo de agentes en vivo": lee GET /api/agent-events cada 1 s y pinta el análisis más reciente
   como 5 tarjetas (ML → Evaluador → Cognitivo → Decisor → Compuerta).
   - Gris = no empezó, pulsando = en curso, verde = terminó (resumen y segundos), rojo = error.
   - El análisis queda a la vista hasta 60 s después de terminar (paso "envio"); si se queda quieto 2 min, se oculta.
   Todo se pinta como texto. */
import { useEffect, useMemo, useRef, useState } from "react";

interface Paso {
  id: number;
  event_id: string;
  case_id: string | null;
  paso: string;
  estado: string;
  at: string | null;
  ms: number | null;
  resumen: string | null;
  datos: unknown;
  received_at: string;
}

const ORDEN = ["ml", "evaluador", "cognitivo", "contexto", "memoria", "decisor", "compuerta", "envio"];
const TARJETAS: { titulo: string; sub: string; pasos: string[] }[] = [
  { titulo: "ML", sub: "da el olfato", pasos: ["ml"] },
  { titulo: "Evaluador", sub: "reglas del negocio en código", pasos: ["evaluador"] },
  { titulo: "Cognitivo", sub: "investiga con el manual", pasos: ["cognitivo", "contexto", "memoria"] },
  { titulo: "Decisor", sub: "abogado del diablo", pasos: ["decisor"] },
  { titulo: "Compuerta", sub: "límites que nadie salta", pasos: ["compuerta", "envio"] },
];
const POLL_MS = 1000;
const VISIBLE_TRAS_FIN_MS = 60_000;
const QUIETO_MS = 120_000;
const MAX_GUARDADOS = 400;

type Estado = "espera" | "curso" | "fin" | "error" | "omitido";

const rec = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const txt = (v: unknown, max = 160): string => {
  const s = typeof v === "string" ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : "";
  return s.length > max ? `${s.slice(0, max)}…` : s;
};
const ts = (iso: string) => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
};

/* Detalle corto del paso ML desde datos (banda, p_laundering, familia), si vino. */
function detalleMl(p: Paso | undefined): string {
  if (!p) return "";
  const d = rec(p.datos);
  const partes: string[] = [];
  if (txt(d.banda, 20)) partes.push(txt(d.banda, 20));
  if (typeof d.p_laundering === "number" && Number.isFinite(d.p_laundering)) partes.push(`p ${d.p_laundering.toFixed(2)}`);
  if (txt(d.familia, 30)) partes.push(txt(d.familia, 30));
  return partes.join(" · ");
}

export function AgentLive() {
  const [pasos, setPasos] = useState<Paso[]>([]);
  const [ahora, setAhora] = useState(() => Date.now());
  const desfase = useRef(0); // hora del servidor − hora local
  const ultimo = useRef<number | null>(null);

  useEffect(() => {
    let vivo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (!document.hidden) {
        try {
          const q = ultimo.current === null ? "" : `?since=${ultimo.current}`;
          const res = await fetch(`/api/agent-events${q}`, { cache: "no-store" });
          if (res.ok) {
            const body: unknown = await res.json();
            const b = rec(body);
            if (typeof b.now === "string" && ts(b.now)) desfase.current = ts(b.now) - Date.now();
            if (typeof b.last === "number") ultimo.current = b.last;
            const nuevos = Array.isArray(b.events) ? (b.events as Paso[]).filter((e) => e && typeof e.id === "number" && typeof e.event_id === "string") : [];
            if (vivo && nuevos.length) setPasos((prev) => [...prev, ...nuevos].slice(-MAX_GUARDADOS));
          }
        } catch {
          /* sin conexión: se reintenta en el siguiente tick */
        }
      }
      if (!vivo) return;
      setAhora(Date.now());
      timer = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      vivo = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const vista = useMemo(() => {
    if (!pasos.length) return null;
    // Análisis más reciente = el event_id del último paso recibido
    const eventId = pasos[pasos.length - 1].event_id;
    const grupo = pasos.filter((p) => p.event_id === eventId);
    const porPaso = new Map<string, Paso>();
    for (const p of grupo) porPaso.set(p.paso, p); // si un paso se repite, gana el último
    const envio = porPaso.get("envio");
    const ultimaActividad = Math.max(...grupo.map((p) => ts(p.received_at)));
    const horaServidor = ahora + desfase.current;
    if (envio && horaServidor - ts(envio.received_at) > VISIBLE_TRAS_FIN_MS) return null;
    if (!envio && horaServidor - ultimaActividad > QUIETO_MS) return null;

    const maxIdx = Math.max(...grupo.map((p) => ORDEN.indexOf(p.paso)));
    let enCursoAsignado = !!envio;
    const tarjetas = TARJETAS.map((t) => {
      const propios = t.pasos.map((n) => porPaso.get(n)).filter((p): p is Paso => !!p);
      const ultimoIdx = Math.max(...t.pasos.map((n) => ORDEN.indexOf(n)));
      let estado: Estado = "espera";
      if (propios.some((p) => p.estado === "error")) estado = "error";
      else if (porPaso.has(t.pasos[t.pasos.length - 1]) || maxIdx > ultimoIdx || (envio && propios.length)) {
        estado = propios.length && propios.every((p) => p.estado === "omitido") ? "omitido" : propios.length ? "fin" : "omitido";
      } else if (!enCursoAsignado) {
        estado = "curso";
        enCursoAsignado = true;
      }
      const conResumen = [...propios].reverse().find((p) => p.resumen);
      const ms = propios.reduce((s, p) => s + (typeof p.ms === "number" && Number.isFinite(p.ms) ? p.ms : 0), 0);
      return {
        ...t,
        estado,
        resumen: txt(conResumen?.resumen ?? "", 160),
        detalle: t.pasos[0] === "ml" ? detalleMl(porPaso.get("ml")) : "",
        segundos: propios.length && ms > 0 ? `${(ms / 1000).toFixed(1)} s` : "",
      };
    });
    return { eventId, tarjetas, terminado: !!envio };
  }, [pasos, ahora]);

  if (!vista) return null;

  return (
    <section className="agent-live" aria-label="Equipo de agentes en vivo" aria-live="polite">
      <h2 className="agent-live-title">
        Equipo de agentes en vivo · <span className="mono">{txt(vista.eventId, 60)}</span>
        {vista.terminado && <span className="agent-live-done"> · terminó</span>}
      </h2>
      <ol className="agent-live-row">
        {vista.tarjetas.map((t) => (
          <li key={t.titulo} className="agent-card" data-estado={t.estado} title={t.resumen || undefined}>
            <b>{t.titulo}</b>
            <small className="agent-card-sub">{t.sub}</small>
            <span className="agent-card-state">
              {t.estado === "espera" ? "en espera" : t.estado === "curso" ? "trabajando…" : t.estado === "error" ? "error" : t.estado === "omitido" ? "omitido" : t.segundos || "listo"}
            </span>
            {t.detalle && <small className="agent-card-detail">{t.detalle}</small>}
            {t.resumen && (t.estado === "fin" || t.estado === "error") && <small className="agent-card-text">{t.resumen}</small>}
          </li>
        ))}
      </ol>
    </section>
  );
}
