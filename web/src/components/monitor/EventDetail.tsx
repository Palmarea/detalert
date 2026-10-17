"use client";
import { useEffect, useMemo, useState } from "react";
import { STEP_CLS, typeInfo, urgencyReason } from "@/lib/payments/catalog";
import { auditHash, type Decision } from "@/lib/payments/decision";
import { jsonHTML, money } from "@/lib/payments/format";
import type { PaymentEvent, ResolutionAction } from "@/lib/payments/types";
import { AgentPanel, useAgentAudit } from "@agent/index";
import { AlertIcon, ChevronIcon } from "@/components/icons";

interface Props {
  event: PaymentEvent;
  user: { name: string; role: string };
  onBack: () => void;
  /* Bandeja: el analista puede marcar el caso y consultar al agente. Sin onResolve (historial) es solo lectura. */
  onResolve?: (action: ResolutionAction, note: string) => Promise<string | null>; // devuelve el error, o null
}

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
            ...(res.notification ? [{ at: res.at, actor: "Sistema", action: `Notificación en cola (canal ${res.notification.channel === "por_definir" ? "por definir" : res.notification.channel})`, hash: auditHash(e.id + "n") }] : []),
          ]
        : []),
    ],
    [x, consults, res, e.id],
  );
  const urgent = urgencyReason(e);
  const risk = d.risk_score >= 70 ? "bad" : d.risk_score >= 40 ? "warn" : "ok";

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
  if (d.status === "pending")
    alert = <div className="alert s-warn">El pago aún no se confirma. Se recibirá un nuevo evento cuando cambie de estado.</div>;

  return (
    <article className="detail">
      <button className="back" onClick={onBack}>← {onResolve ? "Casos" : "Historial"}</button>
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

      {res ? (
        <div className={`resolved s-${res.action === "approved" ? "ok" : "bad"}`}>
          <b>{ACTION_LABEL[res.action]} por {res.by.name}</b>
          <span>{res.by.role} · {stamp(res.at)}{res.notification ? " · notificación en cola" : ""}</span>
          {res.note && <p>«{res.note}»</p>}
        </div>
      ) : (
        onResolve && <ResolveBar key={e.id} onResolve={onResolve} />
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

/* Aprobar / Rechazar. Cada botón pide un segundo clic para confirmar (una decisión archivada no se deshace). */
function ResolveBar({ onResolve }: { onResolve: (action: ResolutionAction, note: string) => Promise<string | null> }) {
  const [note, setNote] = useState("");
  const [armed, setArmed] = useState<ResolutionAction | null>(null);
  const [busy, setBusy] = useState<ResolutionAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!armed) return;
    const id = setTimeout(() => setArmed(null), 4000);
    return () => clearTimeout(id);
  }, [armed]);

  const click = async (a: ResolutionAction) => {
    if (busy) return;
    if (armed !== a) {
      setArmed(a);
      setError(null);
      return;
    }
    setBusy(a);
    const err = await onResolve(a, note);
    if (err) {
      setError(err);
      setBusy(null);
      setArmed(null);
    }
  };

  return (
    <section className="resolve" aria-label="Decidir el caso">
      <div className="resolve-head">
        <h3>Decide este caso</h3>
        <small>Se archiva, se registra a tu nombre y la notificación queda en cola.</small>
      </div>
      <div className="resolve-row">
        <input value={note} onChange={(ev) => setNote(ev.target.value)} maxLength={1000} placeholder="Nota (opcional): por qué lo decides" aria-label="Nota de la decisión" />
        <button type="button" className="btn btn-reject" data-armed={armed === "rejected"} disabled={!!busy} onClick={() => click("rejected")}>
          {busy === "rejected" ? "Guardando…" : armed === "rejected" ? "Confirmar rechazo" : "Rechazar"}
        </button>
        <button type="button" className="btn btn-approve" data-armed={armed === "approved"} disabled={!!busy} onClick={() => click("approved")}>
          {busy === "approved" ? "Guardando…" : armed === "approved" ? "Confirmar aprobación" : "Aprobar"}
        </button>
      </div>
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
