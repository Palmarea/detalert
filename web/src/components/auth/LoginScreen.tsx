"use client";
/* Misma estructura que el monitor: panel a la izquierda (formulario) y, a la derecha,
   la lista de eventos tal como se ve sin sesión: enmascarada. */
import { useActionState, useState } from "react";
import { login, type LoginState } from "@/app/login/actions";
import { initials, type DemoUser } from "@/lib/auth/users";
import { ArrowIcon, EyeIcon, EyeOffIcon, LockIcon, ShieldIcon } from "@/components/icons";

interface Props {
  next: string;
  expired: boolean;
  demoUsers: DemoUser[];
  demoPassword: string;
}

export function LoginScreen({ next, expired, demoUsers, demoPassword }: Props) {
  const [state, action, pending] = useActionState<LoginState, FormData>(login, { error: null, email: "" });
  const [reveal, setReveal] = useState(false);
  const [via, setVia] = useState<string | null>(null); // qué botón envió el formulario

  const notice = state.error ?? (expired ? "Tu sesión venció. Vuelve a ingresar para seguir viendo los eventos." : null);

  return (
    <div className="auth">
      <section className="auth-panel">
        <div className="brand">
          <span className="brand-name">Monitor de pagos</span>
          <span className="badge"><LockIcon size={12} />Acceso restringido</span>
        </div>

        <form className="auth-form" action={action} onSubmit={(e) => setVia((e.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ?? "form")}>
          <input type="hidden" name="next" value={next} />
          <div className="auth-intro">
            <h1>Inicia sesión</h1>
            <p>Usa tu cuenta de analista para ver los eventos de pago en tiempo real.</p>
          </div>

          {notice && <div className={`alert ${state.error ? "s-bad" : "s-warn"}`} role="alert">{notice}</div>}

          <label className="field">
            <span>Correo</span>
            <input name="email" type="email" autoComplete="username" required defaultValue={state.email} placeholder="nombre@empresa.pe" aria-invalid={!!state.error} />
          </label>
          <label className="field">
            <span>Contraseña</span>
            <span className="pw">
              <input name="password" type={reveal ? "text" : "password"} autoComplete="current-password" required aria-invalid={!!state.error} />
              <button type="button" className="pw-toggle" onClick={() => setReveal(!reveal)} aria-label={reveal ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={reveal}>
                {reveal ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </span>
          </label>
          <button type="submit" className="primary" disabled={pending}>
            {pending && via === "form" ? "Ingresando…" : "Ingresar"}
          </button>

          <div className="demo">
            <h2>Accesos de demo</h2>
            <div className="demo-list">
              {demoUsers.map((u) => (
                <button key={u.id} type="submit" name="demo" value={u.id} formNoValidate className="demo-user" disabled={pending}>
                  <span className="avatar" aria-hidden="true">{initials(u.name)}</span>
                  <span className="who">
                    <b>{pending && via === u.id ? "Ingresando…" : u.name}</b>
                    <small>{u.role}</small>
                    <small className="mono">{u.email}</small>
                  </span>
                  <ArrowIcon />
                </button>
              ))}
            </div>
            <p className="demo-note">Solo demo: también puedes escribir el correo y la contraseña <span className="mono">{demoPassword}</span>.</p>
          </div>
        </form>
      </section>

      <section className="auth-side" aria-labelledby="guard-title">
        <div className="guard">
          <div className="guard-head">
            <span className="guard-icon"><ShieldIcon size={18} /></span>
            <div>
              <h2 id="guard-title">Los eventos se muestran después de iniciar sesión</h2>
              <p>Sin una sesión válida, el monitor redirige aquí y la API de eventos responde 401.</p>
            </div>
          </div>
          <dl className="guard-facts">
            <div><dt>Sesión</dt><dd>Firmada con HMAC-SHA256 en el servidor</dd></div>
            <div><dt>Cookie</dt><dd>httpOnly · SameSite=Lax · no legible desde JavaScript</dd></div>
            <div><dt>Vigencia</dt><dd>8 horas; luego se vuelve a pedir acceso</dd></div>
          </dl>
          <div className="masked" aria-hidden="true">
            {MASKED.map((m, i) => (
              <div key={i} className="card">
                <span className={`stripe b-${m.cls}`} />
                <span className="t"><i className="redact" style={{ width: m.w }} /></span>
                <span className="amt num">{m.cur} •••</span>
                <span className="sub"><i className="redact" style={{ width: m.w2 }} /></span>
                <span className="time">hace •s</span>
                <span className="meta"><span className={`pill s-${m.cls}`}>{m.label}</span><span className="tag">pay_••••••</span></span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

/* Filas fijas: solo muestran la forma de la lista, sin datos. */
const MASKED = [
  { cls: "ok", label: "Aprobado", cur: "S/", w: "52%", w2: "68%" },
  { cls: "bad", label: "Rechazado", cur: "S/", w: "44%", w2: "58%" },
  { cls: "ok", label: "Aprobado", cur: "US$", w: "60%", w2: "50%" },
  { cls: "warn", label: "Pendiente", cur: "S/", w: "40%", w2: "72%" },
  { cls: "bad", label: "Contracargo", cur: "S/", w: "56%", w2: "46%" },
  { cls: "info", label: "Reembolso", cur: "S/", w: "48%", w2: "62%" },
];
