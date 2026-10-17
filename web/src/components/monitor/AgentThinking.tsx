/* "Cómo lo pensó el agente": muestra context.aml, el bloque que manda el agente cognitivo AML con cada evento.
   Defensivo: si el evento no trae ese bloque, no se muestra nada; si falta un dato, se omite esa parte. */

type Rec = Record<string, unknown>;

const rec = (v: unknown): Rec => (v && typeof v === "object" && !Array.isArray(v) ? (v as Rec) : {});
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const str = (v: unknown, max = 600): string => {
  const s = typeof v === "string" ? v : v === null || v === undefined ? "" : typeof v === "number" || typeof v === "boolean" ? String(v) : "";
  return s.length > max ? `${s.slice(0, max)}…` : s;
};
const seg = (ms: unknown): string => (typeof ms === "number" && Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)} s` : "");

const NOMBRE_PASO: Record<string, string> = {
  evaluador: "Agente evaluador",
  cognitivo: "Agente cognitivo",
  contexto: "Contexto ampliado",
  memoria: "Memoria del agente",
  decisor: "Agente decisor",
  compuerta: "Compuerta",
  envio: "Envío",
};
const DOT: Record<string, string> = { fin: "b-ok", error: "b-bad", omitido: "b-info" };

/* Historia de la cuenta (context.aml.historial_cuenta): solo los campos que vinieron. */
const num = (v: unknown): string => (typeof v === "number" && Number.isFinite(v) ? Math.round(v).toLocaleString("es-PE") : "");
const HISTORIAL: [string, string, (v: unknown) => string][] = [
  ["operaciones_30d", "Operaciones (30 días)", num],
  ["operaciones_7d", "Operaciones (7 días)", num],
  ["monto_enviado_7d", "Monto enviado (7 días)", num],
  ["promedio_30d", "Promedio por operación (30 días)", num],
  ["efectivo_30d", "En efectivo (30 días)", num],
  ["recibidas_7d", "Recibidas (7 días)", num],
  ["horas_desde_ultima", "Desde la última", (v) => (num(v) ? `${num(v)} h` : "")],
  ["contraparte_nueva", "Contraparte", (v) => (v === true || v === 1 ? "nueva" : v === false || v === 0 ? "conocida" : "")],
];

function HistoriaCuenta({ data }: { data: Rec }) {
  const frase = str(data.frase, 220);
  const filas = HISTORIAL.map(([k, label, fmt]) => [label, fmt(data[k])] as const).filter(([, v]) => v);
  const cuenta = str(data.cuenta, 60);
  if (!frase && !filas.length) return null;
  return (
    <>
      <h3>Historia de la cuenta{cuenta ? <> · <span className="mono">{cuenta}</span></> : null}</h3>
      {frase && <p className="acct-story">{frase}</p>}
      {filas.length > 0 && (
        <dl className="kv" style={{ marginBottom: 16 }}>
          {filas.map(([label, v]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className="num">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  );
}

export function AgentThinking({ context }: { context: unknown }) {
  const aml = rec(rec(context).aml);
  if (!Object.keys(aml).length) return null;

  const pasos = arr(aml.pasos).map(rec);
  const evidencia = arr(aml.evidencia).map(rec);
  const objeciones = arr(aml.objeciones).map(rec);
  const aprendizaje = rec(aml.aprendizaje);
  const memoria = arr(aprendizaje.memoria_cuenta).map(rec);
  const cambios = arr(aprendizaje.cambios_aplicados).map(rec);
  const bandaModelo = str(aml.banda_modelo, 40);
  const bandaAgente = str(aml.agent_band, 40);
  const famApi = str(aml.familia_api, 40);
  const famInf = str(aml.familia_inferida, 40);
  const confianza = typeof aml.confianza === "number" ? `${aml.confianza} %` : "";

  return (
    <section className="section">
      <div className="sec-head">
        <h3>Cómo lo pensó el agente</h3>
        <span className="sample">Agente cognitivo AML</span>
      </div>

      <HistoriaCuenta data={rec(aml.historial_cuenta)} />

      <dl className="kv">
        {bandaModelo && (
          <div>
            <dt>Banda: modelo → agente</dt>
            <dd>{bandaModelo} → <b>{bandaAgente || bandaModelo}</b>{bandaAgente && bandaAgente !== bandaModelo ? " (subió)" : " (no baja)"}</dd>
          </div>
        )}
        {famApi && (
          <div>
            <dt>Familia: modelo → agente</dt>
            <dd>{famApi} → <b>{famInf || famApi}</b>{famInf && famInf !== famApi ? " (reclasificó)" : ""}</dd>
          </div>
        )}
        {str(aml.decision_contrato, 40) && (
          <div>
            <dt>Decisión</dt>
            <dd><b>{str(aml.decision_contrato, 40)}</b>{confianza ? ` · confianza ${confianza}` : ""}</dd>
          </div>
        )}
      </dl>

      {str(aprendizaje.aprendio, 300) && (
        <p className="muted-note" style={{ marginTop: 12 }}>
          <b>Lo que aprendió:</b> {str(aprendizaje.aprendio, 300)}
          {memoria.length > 0 ? ` · ${memoria.length} caso(s) previo(s) de estas cuentas` : ""}
          {cambios.length > 0 ? ` · ${cambios.length} parámetro(s) ajustado(s) por aprendizaje` : ""}
        </p>
      )}

      {pasos.length > 0 && (
        <>
          <h3 style={{ marginTop: 16 }}>Paso a paso</h3>
          <ol className="timeline">
            {pasos.map((p, i) => {
              const nombre = str(p.paso, 30);
              const estado = str(p.estado, 20);
              return (
                <li key={`${nombre}-${i}`}>
                  <span className={`tdot ${DOT[estado] ?? "b-info"}`} />
                  <div>
                    <b>{NOMBRE_PASO[nombre] ?? nombre}</b>{estado && estado !== "fin" ? ` · ${estado}` : ""}
                    <br />
                    <small>{str(p.resumen, 200)}</small>
                  </div>
                  <small className="num">{seg(p.ms)}</small>
                </li>
              );
            })}
          </ol>
        </>
      )}

      {evidencia.length > 0 && (
        <>
          <h3 style={{ marginTop: 16 }}>Evidencia que citó</h3>
          <ul className="rules">
            {evidencia.slice(0, 6).map((ev, i) => (
              <li key={i} style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <b className="mono">{str(ev.feature, 60)} = {str(ev.valor, 40)}</b>
                  <br />
                  <small>{str(ev.interpretacion, 200)}</small>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {(objeciones.length > 0 || str(aml.explicacion_legitima, 400)) && (
        <>
          <h3 style={{ marginTop: 16 }}>Abogado del diablo</h3>
          {str(aml.explicacion_legitima, 400) && <p className="muted-note"><b>Explicación legítima que consideró:</b> {str(aml.explicacion_legitima, 400)}</p>}
          {objeciones.length > 0 && (
            <ul className="rules">
              {objeciones.slice(0, 3).map((o, i) => (
                <li key={i} style={{ gridTemplateColumns: "1fr" }}>
                  <div><small>{str(o.texto, 240)}{str(o.feature, 60) ? ` (${str(o.feature, 60)})` : ""}</small></div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {str(aml.narrativa, 900) && (
        <>
          <h3 style={{ marginTop: 16 }}>Narrativa para el analista</h3>
          <p className="muted-note">{str(aml.narrativa, 900)}</p>
        </>
      )}
    </section>
  );
}
