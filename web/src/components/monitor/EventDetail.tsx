"use client";
import { useEffect, useMemo, useState } from "react";
import { STEP_CLS, THRESHOLDS, needsReview, typeInfo, urgencyReason } from "@/lib/payments/catalog";
import { auditHash, type Decision } from "@/lib/payments/decision";
import { jsonHTML, money } from "@/lib/payments/format";
import { signal, spectra } from "@/lib/payments/signal";
import { useNow } from "@/hooks/usePaymentStream";
import { EVIDENCE_CATEGORIES, EVIDENCE_INDICATORS, categoryLabel, indicatorLabel } from "@/lib/payments/evidence";
import type { EvidenceCategory, EvidenceIndicator, EvidenceInput, PaymentEvent, ResolutionAction } from "@/lib/payments/types";
import { AgentPanel, useAgentAudit } from "@agent/index";
import { AlertIcon, ChevronIcon } from "@/components/icons";
import { ScoreHero, SpectrumBar } from "./Signals";
import { AgentThinking } from "./AgentThinking";

interface Props {
  event: PaymentEvent;
  user: { name: string; role: string };
  onBack: () => void;
  /* Bandeja: el analista puede marcar el caso y consultar al agente. Sin onResolve (historial) es solo lectura. */
  onResolve?: Resolver;
}

/* Devuelve el error a mostrar, o null. evidence solo viaja en rechazos. */
type Resolver = (action: ResolutionAction, note: string, evidence?: EvidenceInput) => Promise<string | null>;

const DECIDER: Record<Decision["decidedBy"]["kind"], string> = { auto: "Automática", human: "Persona", external: "Tercero" };
const stamp = (iso: string) => new Date(iso).toLocaleString("es-PE", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const ACTION_LABEL: Record<ResolutionAction, string> = { approved: "Aprobado", rejected: "Rechazado" };

export function EventDetail({ event: e, user, onBack, onResolve }: Props) {
  const t = typeInfo(e.type);
  const d = e.data;
  const x = e.context ?? null;
  const res = e.resolution;
  const consults = useAgentAudit(e.id, user.name); // vacío si el agente no está instalado
  const audit = useMemo(
    () => [
      ...(x?.audit ?? []),
      // Las consultas al agente y la resolución también son actos auditables
      ...consults,
      ...(res
        ? [
            { at: res.at, actor: res.by.name, action: `${res.action === "approved" ? "Aprobó" : "Rechazó"} y archivó el caso${res.note ? `: «${res.note}»` : ""}`, hash: auditHash(e.id + res.at) },
            ...(res.evidence ? [{ at: res.evidence.at, actor: res.by.name, action: `Guardó el caso como evidencia: ${categoryLabel(res.evidence.category)}`, hash: auditHash(e.id + "x") }] : []),
            ...(res.notification ? [{ at: res.at, actor: "Sistema", action: `Notificación en cola (canal ${res.notification.channel === "por_definir" ? "por definir" : res.notification.channel})`, hash: auditHash(e.id + "n") }] : []),
          ]
        : []),
    ],
    [x, consults, res, e.id],
  );
  const urgent = urgencyReason(e);
  const risk = d.risk_score >= THRESHOLDS.BLOCK ? "bad" : d.risk_score >= THRESHOLDS.REVIEW ? "warn" : "ok";
  const now = useNow(15000);
  const sig = signal(e);
  const specs = useMemo(() => spectra(e, now).filter((s) => s.key !== "risk"), [e, now]); // el riesgo va en grande arriba

  let alert: React.ReactNode = null;
  if (d.failure_code)
    alert = <div className="alert s-bad"><b>{d.failure_message}</b> · código <span className="mono">{d.failure_code}</span></div>;
  if (d.dispute_reason && d.respond_by)
    alert = (
      <div className="alert s-bad">
        <b>{d.dispute_reason}</b> · responder antes del{" "}
        {new Date(d.respond_by).toLocaleDateString("es-PE", { day: "numeric", month: "long" })}
      </div>
    );
  if (needsReview(e) && !res)
    alert = (
      <div className="alert s-warn">
        <b>Pendiente de revisión:</b> el puntaje {d.risk_score} está entre el umbral de revisión ({THRESHOLDS.REVIEW}) y el de bloqueo ({THRESHOLDS.BLOCK}), así que el agente no lo califica solo. Queda retenido hasta que lo apruebes o rechaces.
      </div>
    );

  return (
    <article className="detail">
      <button className="back" onClick={onBack}>← {onResolve ? "Pendientes" : "Historial"}</button>
      <div className="d-head">
        <div>
          <div className="type">{e.type} · {e.id}</div>
          <h2 className="num">
            {e.type === "refund.created" ? "−" : ""}
            {money(d.amount, d.currency)}
            <small>{d.currency}</small>
          </h2>
        </div>
        <div className="d-status">
          {urgent && <span className="urgent-tag"><AlertIcon size={14} />Urgente · {urgent}</span>}
          <span className={`pill s-${t.cls}`} style={{ fontSize: 13, padding: "4px 12px" }}>{t.label}</span>
        </div>
      </div>
      {alert}

      <section className="section signal-card" aria-label="Semáforo e indicadores del caso">
        <ScoreHero score={d.risk_score} signal={sig.signal} reason={sig.reason} />
        <div className="spec-grid">
          {specs.map((s) => <SpectrumBar key={s.key} s={s} />)}
        </div>
      </section>

      {res ? (
        <div className={`resolved s-${res.action === "approved" ? "ok" : "bad"}`}>
          <b>{ACTION_LABEL[res.action]} por {res.by.name}</b>
          <span>{res.by.role} · {stamp(res.at)}{res.notification ? " · notificación en cola" : ""}</span>
          {res.note && <p>«{res.note}»</p>}
          {res.evidence && (
            <p className="ev-saved">
              <span className="ev-badge">Evidencia</span>
              {categoryLabel(res.evidence.category)}
              {res.evidence.indicators.length > 0 && <small> · señales: {res.evidence.indicators.map(indicatorLabel).join(", ")}</small>}
            </p>
          )}
        </div>
      ) : (
        onResolve && <ResolveBar key={e.id} event={e} onResolve={onResolve} />
      )}

      <section className="section">
        <h3>Pago</h3>
        <dl className="kv">
          <KV k="ID de pago" v={d.payment_id} mono />
          <KV k="Orden" v={d.order_id} mono />
          <KV k="Comercio" v={d.merchant} />
          <KV k="Método" v={`${d.brand}${d.last4 ? ` terminada en ${d.last4}` : ""}`} />
          <KV k="Recibido" v={new Date(e.created_at).toLocaleString("es-PE")} />
          <div>
            <dt>Riesgo</dt>
            <dd><span className={`pill s-${risk} num`}>{d.risk_score} / 100</span></dd>
          </div>
          {d.refund_id && <KV k="ID de reembolso" v={d.refund_id} mono />}
        </dl>
      </section>

      {x ? (
        <DecisionSection x={x} risk={d.risk_score} />
      ) : (
        <section className="section">
          <h3>Decisión y responsabilidad</h3>
          <p className="muted-note">Este evento llegó sin contexto: no hay decisión, factores ni reglas que mostrar.</p>
        </section>
      )}

      <AgentThinking context={x} />

      <section className="section">
        <h3>Cliente</h3>
        <dl className="kv">
          <KV k="Nombre" v={d.customer.name} />
          <KV k="Correo" v={d.customer.email} />
          <KV k="Documento" v={d.customer.doc} />
          <KV k="IP · País" v={`${d.ip} · ${d.country}`} mono />
        </dl>
      </section>

      <section className="section">
        <h3>Línea de tiempo</h3>
        <ol className="timeline">
          {d.history.map((h, i) => (
            <li key={i}>
              <span className={`tdot ${STEP_CLS[h.status] ?? "b-info"}`} />
              <div><b>{h.status}</b><br /><small>{h.note}</small></div>
              <small className="num">{stamp(h.at)}</small>
            </li>
          ))}
        </ol>
      </section>

      <section className="section">
        <div className="sec-head">
          <h3>Registro de auditoría</h3>
          {x && <span className="sample">Recibido con el evento</span>}
        </div>
        {audit.length ? (
          <ol className="audit">
            {audit.map((a, i) => (
              <li key={i}>
                <small className="num">{stamp(a.at)}</small>
                <div><b>{a.actor}</b><span>{a.action}</span></div>
                <span className="tag" title="Huella del registro">#{a.hash}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted-note">Sin registros todavía.</p>
        )}
      </section>

      <details className="section collapse">
        <summary>
          <ChevronIcon />
          <h3>Payload recibido</h3>
          <span className="tag">{(JSON.stringify(e).length / 1024).toFixed(1)} KB · JSON</span>
        </summary>
        <JsonBlock value={e} />
      </details>

      {onResolve && <AgentPanel event={e} userName={user.name} />}
    </article>
  );
}

/* Aprobar / Rechazar.
   - Aprobar pide un segundo clic para confirmar (una decisión archivada no se deshace).
   - Rechazar abre un paso de confirmación donde, opcionalmente, el caso se guarda como evidencia
     (categoría + señales del pago) para futuros análisis de riesgo. */
function ResolveBar({ event: e, onResolve }: { event: PaymentEvent; onResolve: Resolver }) {
  const [note, setNote] = useState("");
  const [armed, setArmed] = useState<ResolutionAction | null>(null);
  const [busy, setBusy] = useState<ResolutionAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keep, setKeep] = useState(false); // archivar como evidencia
  const [category, setCategory] = useState<EvidenceCategory | null>(null);
  const [indicators, setIndicators] = useState<EvidenceIndicator[]>(EVIDENCE_INDICATORS.map((i) => i.key));

  // Solo la aprobación se desarma sola; el paso de rechazo espera a que el analista termine
  useEffect(() => {
    if (armed !== "approved") return;
    const id = setTimeout(() => setArmed(null), 4000);
    return () => clearTimeout(id);
  }, [armed]);

  const submit = async (a: ResolutionAction) => {
    if (keep && a === "rejected" && !category) return setError("Elige una categoría o desmarca «Guardar como evidencia».");
    setBusy(a);
    const err = await onResolve(a, note, keep && a === "rejected" && category ? { category, indicators } : undefined);
    if (err) {
      setError(err);
      setBusy(null);
      if (a === "approved") setArmed(null);
    }
  };

  const click = (a: ResolutionAction) => {
    if (busy) return;
    if (armed !== a) {
      setArmed(a);
      setError(null);
      return;
    }
    submit(a);
  };

  const toggle = (k: EvidenceIndicator) => setIndicators((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const rejecting = armed === "rejected";
  const fired = e.context?.rules.filter((r) => r.fired).length ?? 0;

  return (
    <section className="resolve" data-step={rejecting ? "reject" : undefined} aria-label="Decidir el caso">
      <div className="resolve-head">
        <h3>{rejecting ? "Confirmar rechazo" : "Decide este caso"}</h3>
        <small>Se archiva, se registra a tu nombre y la notificación queda en cola.</small>
      </div>
      <div className="resolve-row">
        <input value={note} onChange={(ev) => setNote(ev.target.value)} maxLength={1000} placeholder={rejecting ? "Nota: por qué lo rechazas (recomendado)" : "Nota (opcional): por qué lo decides"} aria-label="Nota de la decisión" />
        {rejecting ? (
          <button type="button" className="btn btn-ghost" disabled={!!busy} onClick={() => { setArmed(null); setError(null); }}>Cancelar</button>
        ) : (
          <button type="button" className="btn btn-reject" disabled={!!busy} onClick={() => click("rejected")}>Rechazar</button>
        )}
        {rejecting ? (
          <button type="button" className="btn btn-reject" data-armed="true" disabled={!!busy} onClick={() => submit("rejected")}>
            {busy === "rejected" ? "Guardando…" : keep ? "Rechazar y guardar evidencia" : "Confirmar rechazo"}
          </button>
        ) : (
          <button type="button" className="btn btn-approve" data-armed={armed === "approved"} disabled={!!busy} onClick={() => click("approved")}>
            {busy === "approved" ? "Guardando…" : armed === "approved" ? "Confirmar aprobación" : "Aprobar"}
          </button>
        )}
      </div>

      {rejecting && (
        <div className="evidence" data-on={keep}>
          <label className="ev-toggle">
            <input type="checkbox" checked={keep} onChange={(ev) => { setKeep(ev.target.checked); setError(null); }} />
            <span>
              <b>Guardar como evidencia para futuros análisis de riesgo</b>
              <small>Opcional. Queda en el archivo de evidencias con el puntaje {e.data.risk_score}, {e.context?.factors.length ?? 0} factores y {fired} regla{fired === 1 ? "" : "s"} disparada{fired === 1 ? "" : "s"}.</small>
            </span>
          </label>
          {keep && (
            <>
              <fieldset className="ev-group">
                <legend>¿Qué tipo de caso es?</legend>
                <div className="ev-chips">
                  {EVIDENCE_CATEGORIES.map(([k, l]) => (
                    <button key={k} type="button" className="chip" aria-pressed={category === k} onClick={() => { setCategory(k); setError(null); }}>{l}</button>
                  ))}
                </div>
              </fieldset>
              <fieldset className="ev-group">
                <legend>Señales a guardar</legend>
                <div className="ev-inds">
                  {EVIDENCE_INDICATORS.map((i) => (
                    <label key={i.key} className="ev-ind">
                      <input type="checkbox" checked={indicators.includes(i.key)} onChange={() => toggle(i.key)} />
                      <span>{i.label}</span>
                      <small className="mono">{i.value(e.data)}</small>
                    </label>
                  ))}
                </div>
              </fieldset>
            </>
          )}
        </div>
      )}
      {error && <p className="resolve-error" role="alert">{error}</p>}
    </section>
  );
}

function DecisionSection({ x, risk }: { x: Decision; risk: number }) {
  const max = Math.max(...x.factors.map((f) => Math.abs(f.points)), x.base, 1);
  return (
    <section className="section">
      <div className="sec-head">
        <h3>Decisión y responsabilidad</h3>
        <span className="sample">Recibido con el evento</span>
      </div>
      <div className="verdict">
        <span className={`pill s-${x.outcome}`}>{DECIDER[x.decidedBy.kind]}</span>
        <div>
          <b>{x.verdict}</b>
          <small>{x.policy}</small>
        </div>
      </div>
      <dl className="kv">
        <KV k="Decidió" v={`${x.decidedBy.name} · ${x.decidedBy.detail}`} />
        <KV k="Responsable" v={`${x.accountable.name} · ${x.accountable.role}`} />
        {x.confidence !== null && <KV k="Confianza del motor" v={`${x.confidence} %`} />}
        <KV k="Apelación" v={x.appeal} />
      </dl>

      <h4>Por qué: factores del puntaje {risk} / 100</h4>
      <ul className="factors">
        <li>
          <span>Base del comercio</span>
          <span className="bar"><i className="b-info" style={{ width: `${(x.base / max) * 100}%` }} /></span>
          <b className="num">{x.base}</b>
        </li>
        {x.factors.map((f) => (
          <li key={f.label}>
            <span>{f.label}</span>
            <span className="bar"><i className={f.points > 0 ? "b-bad" : "b-ok"} style={{ width: `${(Math.abs(f.points) / max) * 100}%` }} /></span>
            <b className="num">{f.points > 0 ? `+${f.points}` : `−${-f.points}`}</b>
          </li>
        ))}
        <li className="total"><span>Puntaje final</span><span /><b className="num">{risk}</b></li>
      </ul>

      <h4>Reglas evaluadas</h4>
      <ul className="rules">
        {x.rules.map((r) => (
          <li key={r.id}>
            <span className="tag">{r.id}</span>
            <div><span>{r.name}</span><small>{r.detail}</small></div>
            <span className={`pill s-${r.fired ? "bad" : "ok"}`}>{r.fired ? "Disparó" : "No disparó"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div>
      <dt>{k}</dt>
      <dd className={mono ? "mono" : undefined}>{v}</dd>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  const [label, setLabel] = useState("Copiar JSON");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
      setLabel("Copiado");
    } catch {
      setLabel("No se pudo copiar");
    }
    setTimeout(() => setLabel("Copiar JSON"), 1500);
  };
  return (
    <div className="json-wrap">
      <button className="copy" onClick={copy}>{label}</button>
      <pre dangerouslySetInnerHTML={{ __html: jsonHTML(value) }} />
    </div>
  );
}
