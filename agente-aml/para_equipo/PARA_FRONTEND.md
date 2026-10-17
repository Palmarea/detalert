# Agente AML → Bandeja: qué les llega y cómo aprovecharlo

**Resumen:** cada caso que analiza el agente AML llega a la bandeja por `POST /api/ingest` como un evento de pago más su `context` (la `Decision` de siempre). Ya hay casos reales en la base; los encuentran buscando `aml`.

## Cómo reconocer un caso del agente

| Señal | Valor |
|---|---|
| `event.id` | Empieza con `evt_aml_` y sigue el `case_id` de ML (`evt_aml_C-7218608806-2023-07-14`) |
| `data.order_id` | El `case_id` de ML |
| `context.decidedBy.name` | `Agente cognitivo AML` |
| `context.policy` | Empieza con `aml-transaction-reviewer` y trae las versiones del modelo (`binary_v1/thresholds_v1`) |

El evento se envía **una sola vez**, ya con su contexto: no reutilicen ids `evt_aml_`.

## Qué decisión trae cada tipo de evento

| Decisión del agente | `event.type` | Etiqueta en la tarjeta | Qué significa |
|---|---|---|---|
| `high_priority` | `payment.failed` (`failure_code: fraud_suspected`, `failure_message: "Retenido por el agente AML"`) | Rechazado · Urgente | Retención preventiva; el analista ratifica o libera |
| `escalated` | `payment.pending` | Pendiente | El analista decide con la narrativa del agente |
| `auto_closed` | `payment.succeeded` | Aprobado | Falso positivo cerrado con justificación |

## Qué hay en cada campo

| Campo | Contenido en los casos AML |
|---|---|
| `data.payment_id` | `txn_<id>` de la transacción con mayor probabilidad de lavado |
| `data.amount` | Monto alertado del caso × 100. **La moneda real es la del dataset (libras, euros…), no dólares**: se manda `USD` solo para que la pantalla lo formatee |
| `data.brand` | Tipo de pago original (`Cross-border`, `Cheque`, `Cash Deposit`…); `method` es `card` o `transfer` |
| `data.customer.name` / `doc` | `Cuenta <cuenta emisora>` |
| `data.merchant` | `Receptora <cuenta receptora>` |
| `data.risk_score` | `case_score` del modelo × 100 |
| `data.history` | Una entrada por transacción del caso (fecha original, tipo, monto, receptora y probabilidad) y **al final la narrativa del agente** |
| `context.verdict` | `Agente AML: <cerrar como falso positivo · escalar al analista · subir a prioridad alta> · familia <f>` |
| `context.confidence` | Confianza del agente (0 a 100); `null` si cerró sin IA o hubo contingencia |
| `context.base` + `factors` | Las razones del modelo (reason codes) con su peso; `base + Σ points = risk_score`. **Aquí `base` es la base del modelo, no del comercio** |
| `context.rules` | `BANDA` (banda del modelo), `BANDA-NO-BAJA` (el agente nunca baja la banda), `F-<familia>-<n>` (firmas del negocio sobre las 18 variables: `fired: true` = el patrón está en los datos) y `A1`–`A7` (controles de la compuerta: **`fired: false` = control superado**) |
| `context.audit` | 5 pasos: agente evaluador, agente cognitivo, agente decisor, compuerta y registro en ML (con el `feedback_id`) |

## Ejemplo real (recortado)

```json
{
  "event": {
    "id": "evt_aml_C-2231090262-2023-08-11",
    "type": "payment.failed",
    "data": {
      "payment_id": "txn_9158315", "amount": 301316, "currency": "USD",
      "method": "transfer", "brand": "Cross-border",
      "customer": { "name": "Cuenta 2231090262", "email": "aml@demo.local", "doc": "Cuenta 2231090262" },
      "merchant": "Receptora 9108447968", "order_id": "C-2231090262-2023-08-11", "risk_score": 100,
      "failure_code": "fraud_suspected", "failure_message": "Retenido por el agente AML",
      "history": [
        { "status": "created", "at": "2023-08-11T14:35:21Z", "note": "Cross-border 3013.16 → 9108447968 · p=1.0000" },
        { "status": "failed", "at": "2026-10-17T20:56:11Z", "note": "Agente AML: subir a prioridad alta · familia generic. …narrativa…" }
      ]
    }
  },
  "context": {
    "outcome": "bad",
    "verdict": "Agente AML: subir a prioridad alta · familia generic",
    "decidedBy": { "kind": "auto", "name": "Agente cognitivo AML", "detail": "Evaluador → cognitivo → decisor · compuerta en código" },
    "confidence": 62,
    "policy": "aml-transaction-reviewer · binary_v1/thresholds_v1",
    "base": 85,
    "factors": [ { "label": "Primera transacción hacia esta contraparte", "points": 9 } ],
    "rules": [ { "id": "BANDA-NO-BAJA", "name": "La banda no baja", "fired": false, "detail": "agent_band high_priority; banda del modelo high_priority" } ],
    "audit": [ { "actor": "Agente evaluador", "action": "Ruta agente; firmas disparadas: ninguna; banda mínima high_priority", "hash": "348993a1" } ]
  }
}
```

## Ideas para explotarlo, por prioridad

1. **Una insignia "Agente AML"** en la tarjeta cuando `decidedBy.name` sea el del agente, y la **narrativa** (la última entrada de `history`) destacada arriba del detalle.
2. **Separar las reglas en tres grupos**: banda del modelo, firmas del negocio (mostrar primero las disparadas) y controles de la compuerta (A1–A7 con ✓ cuando `fired` es `false`).
3. **Banda del modelo contra banda del agente**, con una flecha que muestre si subió o quedó igual: es la regla del contrato ("la banda nunca baja") y luce en el pitch.
4. **Familia del modelo → familia del agente** cuando el agente la reclasifica (viene en `verdict` y en la auditoría).
5. **Cerrar el ciclo de aprendizaje**: cuando el analista aprueba o rechaza, que su backend lo mande a ML (`POST /feedback` con `actor: "analyst"` y `decision: approved | rejected | sar_filed`), desde el servidor y con la key de ML. Es la etiqueta con la que aprende el sistema.
6. **Un mini tablero**: casos por decisión, porcentaje cerrado por el agente y tiempo del agente por caso.

## El pensamiento del agente: `context.aml` (casos nuevos desde las 16:45)

Los casos nuevos traen un bloque extra `context.aml` con todo lo que pensó el agente. La bandeja guarda `context` completo, así que no rompe nada: solo hay que mostrarlo. Los 11 casos de la primera tanda no lo tienen, porque la bandeja ignora un id repetido.

**`context.aml.pasos`: la línea de tiempo del razonamiento**, un paso por agente, en orden:

| `paso` | `resumen` de ejemplo | `datos` |
|---|---|---|
| `evaluador` | "Banda review; firmas disparadas: F-behavioural-1 (ratio 7,71; z 4,90)" | banda, firmas disparadas |
| `contexto` | "Se pidió historial de 30 días de emisor y receptor" (o `omitido`) | riesgo de cada cuenta en la ventana |
| `cognitivo` | "Familia inferida behavioural (el modelo decía layering) con 3 evidencias" | familia, evidencia |
| `decisor` | "Decide INVESTIGATE_FURTHER con confianza 70; 2 objeciones" | acción, confianza, objeciones |
| `compuerta` | "Controles A1–A7 superados; la banda queda en review" | decisión del contrato, agent_band |
| `envio` | "Registrado en ML (feedback 201) y entregado a la bandeja" | feedback_id |

Cada paso trae `estado` (`fin`, `error` u `omitido`), `at` y `ms`: alcanza para una barra de progreso con tiempos.

**Cómo mostrarlo, por prioridad:**
1. **Una línea de tiempo vertical "Cómo lo pensó el agente"**, con un punto por paso, su `resumen` y su tiempo.
2. **Familia del modelo → familia del agente** y **banda del modelo → banda del agente**, como dos chips con flecha.
3. **La evidencia** como tabla: variable, valor e interpretación.
4. **Las objeciones y la explicación legítima** del decisor, en un recuadro de "abogado del diablo".
5. **Las firmas del negocio**, con las disparadas primero y sus valores.

El bloque completo:

```json
"aml": {
  "banda_modelo": "review", "agent_band": "review", "decision_contrato": "escalated",
  "familia_api": "layering", "familia_inferida": "behavioural", "tipologias": ["Single_large"],
  "tipologia_normal_mas_cercana": "Normal_single_large",
  "firmas_disparadas": [ { "id": "F-behavioural-1", "valores": { "s_amt_ratio_mean_30d": 7.71, "s_amt_z_30d": 4.9 } } ],
  "evidencia": [ { "feature": "is_new_counterparty", "valor": "1", "interpretacion": "Primera transferencia a este receptor" } ],
  "objeciones": ["…"], "explicacion_legitima": "…", "mitigantes": ["…"],
  "consultas_sugeridas": ["contrapartes_90d"], "plan_b": "…",
  "feedback_id": "…", "versiones": "binary_v1/thresholds_v1", "tiempo_agente_ms": 34000
}
```

## Lo que aprendió el agente: `context.aml.aprendizaje`

Los casos nuevos traen también qué aprendió el agente y qué usó de su experiencia:

```json
"aprendizaje": {
  "version_parametros": "a1b2c3d4",
  "cambios_aplicados": [ { "id": "F-behavioural-1", "variable": "s_amt_ratio_mean_30d", "antes": 4.0, "despues": 3.2, "fecha": "2026-10-17" } ],
  "memoria_cuenta": [ { "case_id": "C-5471569552-2023-07-09", "decision": "escalated", "familia_inferida": "behavioural", "confianza": 70, "resumen": "Cheque grande a receptor nuevo…" } ],
  "casos_previos": 1,
  "propuestas_pendientes": 2,
  "aprendio": "Usó 1 decisión previa sobre la cuenta 5471569552 y la firma F-behavioural-1 con el umbral ajustado (4,0 → 3,2)"
}
```

| Campo | Qué mostrar |
|---|---|
| `aprendio` | Una frase destacada: "Lo que el agente aprendió para este caso" |
| `memoria_cuenta` | "Ya vi estas cuentas": casos previos, con su decisión y familia |
| `cambios_aplicados` | Parámetros que cambiaron por aprendizaje: antes → después, y cuándo |
| `version_parametros` | La versión de las reglas con la que se decidió (trazabilidad) |
| `propuestas_pendientes` | Cuántas mejoras propuso el agente y esperan aprobación |

También hay un paso nuevo, `memoria`, en `context.aml.pasos`, justo antes del decisor: "2 decisiones previas sobre estas cuentas; parámetros v…".

## Caso del jurado en vivo

**Hoy:** el jurado dicta una transacción (cuenta emisora, receptora, monto, tipo de pago y monedas), la corremos desde la terminal del agente, ML la puntúa en vivo (`/score/live`) y en menos de un minuto aparece en la bandeja con id `evt_aml_jurado_<fecha-hora>`. Búsquenla escribiendo `jurado`.

**Para que el jurado la escriba en la bandeja** (próximo paso), el backend necesita dos endpoints. El agente no recibe conexiones: él va a buscar las solicitudes.

| Endpoint | Quién lo llama | Qué hace |
|---|---|---|
| `POST /api/agent-requests` | El formulario de la bandeja ("Probar un caso") | Guarda `{id, sender_account, receiver_account, amount, payment_type, payment_currency, received_currency}` como pendiente |
| `GET /api/agent-requests?estado=pendiente` | El agente, cada 3 s, con Bearer `INGEST_TOKEN` | Devuelve las pendientes; el agente procesa cada una una sola vez |

El resultado llega como siempre por `/api/ingest`, y los pasos por `/api/agent-events` si lo crean (abajo).

## Para el futuro: ver al agente trabajando en vivo

**Idea:** mientras el agente analiza un caso, la bandeja muestra los pasos importantes (no todo su razonamiento), como una barra de progreso con lo esencial de cada paso.

**Cómo llega cada paso:** el agente manda un mensaje corto por paso a un endpoint nuevo del backend (`POST /api/agent-events`, con su propio token) y la bandeja lo muestra con el polling que ya tiene. Un socket directo no conviene en Vercel: sus funciones no mantienen conexiones abiertas. Si quieren tiempo real de verdad, la opción simple es un canal gestionado (Supabase Realtime, Pusher o Ably) al que publica el backend.

```json
{
  "case_id": "C-5471569552-2023-07-09",
  "event_id": "evt_aml_C-5471569552-2023-07-09",
  "paso": "cognitivo",
  "estado": "fin",
  "at": "2026-10-17T20:52:18Z",
  "ms": 11659,
  "resumen": "Familia inferida: behavioural (el modelo decía layering)",
  "datos": { "firmas_disparadas": ["F-behavioural-1"], "evidencia": [ { "feature": "s_amt_z_30d", "valor": 4.9 } ] }
}
```

| Paso | Qué mostrar | Qué no mostrar |
|---|---|---|
| Evaluador | Banda del modelo y firmas del negocio que se dispararon, con sus valores | — |
| Cognitivo | Familia del modelo → familia inferida, y las 2 o 3 variables que la prueban | El razonamiento completo |
| Decisor | Explicación legítima considerada, número de objeciones, decisión y confianza | El texto completo del debate |
| Compuerta | Controles superados (A1–A7) y si la banda subió o quedó igual | — |
| Envío | Registrado en ML (`feedback_id`) y entregado a la bandeja | Tokens, claves o detalles internos |

## Lo que necesitamos de ustedes

1. Confirmar la moneda: ¿mostramos `USD`, o aceptan `GBP`/`EUR`?
2. Cambiar la etiqueta "Base del comercio" por "Base del modelo" en los casos del agente.
3. Mostrar `context.aml.pasos` (la línea de tiempo del pensamiento).
4. Si les da el tiempo: los endpoints `agent-requests` (formulario del jurado) y `agent-events` (pasos en vivo).
5. Que su backend mande a ML la decisión del analista (`POST /feedback`, `actor: "analyst"`): es lo que cierra el ciclo de aprendizaje.
6. Al final del día, cambiar el `INGEST_TOKEN`.
