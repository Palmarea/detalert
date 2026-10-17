# Agente AML → API de ML: qué recibe su `/feedback` y cómo usarlo para aprender

**Resumen:** sí, ya les estamos dando feedback. Cada caso que analiza el agente termina en `POST /feedback` con `actor: "agent"`: la API aceptó las 11 decisiones de hoy (201) y el agente nunca intentó bajar una banda (cero 422). Además, el agente ahora pide más contexto a su API cuando lo necesita, y un agente de aprendizaje propone umbrales y etiquetas de familia para ustedes (`propuestas_para_ml.json`).

## Qué usamos de su API

| Endpoint | Para qué |
|---|---|
| `GET /cases?band=…` y `GET /cases/{id}` | La bandeja de trabajo: casos con sus transacciones y reason codes |
| `GET /audit/{txn_id}` | Las 18 variables (`features_snapshot`) de hasta 3 transacciones por caso: es la evidencia que cita el agente |
| `GET /score/account/{cuenta}?from&to` | **Contexto ampliado:** cuando el agente pide más historial, el código trae el riesgo de 30 días de la cuenta emisora y de la receptora (máximo 2 llamadas) y se lo pasa al decisor |
| `POST /score/live` | El caso del jurado en vivo: una transacción nueva puntuada en el momento |
| `POST /feedback` | La decisión del agente por cada caso |
| `GET /thresholds` | Los parámetros iniciales del agente de aprendizaje |

## Qué mandamos

```json
{
  "case_id": "C-5471569552-2023-07-09",
  "actor": "agent",
  "decision": "escalated",
  "agent_band": "review",
  "notes": "<narrativa del agente> · <nota de la decisión> · familia inferida: behavioural · versiones: binary_v1/thresholds_v1"
}
```

| Campo | Cómo lo decide el agente |
|---|---|
| `decision` | Se traduce del veredicto del skill en código: `APPROVE` → `auto_closed` (solo si la banda del modelo es `auto_close_eligible`); `INVESTIGATE_FURTHER` → `escalated`; `REJECT` → `high_priority` con retención preventiva. Rechazar y reportar (SAR) queda para el analista |
| `agent_band` | Nunca menor que la banda del modelo. Puede subir si una firma del negocio o una señal extrema lo pide (por ejemplo `s_amt_z_30d ≥ 4` en un caso de cierre lo sube a `review`) |
| `notes` | Narrativa con las variables citadas (cada una verificada contra `features_snapshot` antes de enviar), la familia inferida y las versiones del modelo y los umbrales |

## Cómo decide el agente

1. **Evaluador (código):** toma la banda y calcula sobre las 18 variables de `/audit` las firmas del skill de negocio: pitufeo, abanico, embudo, emisor puente, receptor mula, fricción internacional, depósito y giro, efectivo intensivo, cambio de comportamiento. Si la banda es de cierre y no hay ninguna firma ni señal extrema, cierra sin IA (~1 s).
2. **Agente cognitivo (IA):** infiere la familia real (el skill trata `family` como preliminar), cita las variables que lo prueban y propone una acción.
3. **Agente decisor (IA):** busca primero la explicación legítima (la tipología normal más cercana), objeta y decide.
4. **Compuerta (código):** traduce la decisión al contrato, aplica "la banda no baja", descarta la evidencia que no coincide con los datos y filtra la salida.

## Lo que encontró el agente en los casos reales

- **Reclasifica la familia seguido:** `layering` → `behavioural` y `structuring` → `behavioural` o `generic` cuando ninguna firma del negocio se dispara. Es señal útil para entrenar `train_family.py` (etiquetas débiles: `familia_inferida`).
- **Una transacción cross-border con `p = 0,0027` llegó marcada `review` dentro de un caso de revisión**: parece que hereda la banda del caso (máximo del caso). Vale la pena confirmar si es lo esperado.
- **Los casos de cierre sin señales se cierran en ~1 s sin IA**; los que tienen alguna señal pasan por los agentes (~30–50 s, unos US$ 0,33 por caso).

## Casos enviados hoy

11 casos, todos con respuesta 201:

| case_id | Banda del modelo | Decisión del agente | agent_band | Familia API → inferida | Ruta | Confianza | feedback_id |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-2231090262-2023-08-11 | high_priority | high_priority | high_priority | structuring → generic | agentes | 62 | `63251a63-ab98-4962-92e0-c4e13c9315f0` |
| C-6875184773-2023-07-08 | high_priority | high_priority | high_priority | structuring → behavioural | agentes | 62 | `03204b7d-d3ce-4a00-a8e6-dc243a22e51e` |
| C-9166883856-2023-06-17 | high_priority | high_priority | high_priority | structuring → behavioural | agentes | 60 | `7ab728c3-a4e5-4151-8a5c-b555f784012d` |
| C-1285873873-2023-06-15 | review | escalated | review | structuring → behavioural | agentes | 64 | `a82a2285-8bf9-4319-bd65-5f040b9b13aa` |
| C-4112229788-2023-07-13 | review | escalated | review | layering → structuring | agentes | 60 | `8da0abcd-0117-44d6-9de1-89a2c37ac917` |
| C-5471569552-2023-07-09 | review | escalated | review | layering → behavioural | agentes | 70 | `cdc06763-1277-438c-bc32-9bb786f2633a` |
| C-7218608806-2023-07-14 | review | escalated | review | layering → generic | agentes | 62 | `5b103662-6241-491e-9a94-b3c2f04035dc` |
| C-990166612-2023-08-22 | review | escalated | review | layering → behavioural | agentes | 70 | `c2b3c5ea-32ea-460a-adfb-6090a6762243` |
| C-3049253016-2023-06-09 | auto_close_eligible | auto_closed | auto_close_eligible | cash → normal | sin IA | — | `a71829b0-23cb-4c76-9906-7c7b8c3f0217` |
| C-6324740324-2023-07-28 | auto_close_eligible | auto_closed | auto_close_eligible | cash → normal | sin IA | — | `70636baa-8d2a-487d-8e0a-9964aedb5529` |
| C-8060333204-2023-06-13 | auto_close_eligible | auto_closed | auto_close_eligible | cash → normal | agentes | 82 | `d984efd5-6a64-4a0a-b8e3-b6983e8da004` |


## Lo que podemos mandarles además

Hoy el detalle estructurado viaja como texto en `notes`. Si agregan un campo opcional `agent_payload` (JSON) a `/feedback`, lo mandamos estructurado:

```json
"agent_payload": {
  "familia_api": "layering", "familia_inferida": "behavioural", "tipologias": ["Single_large"],
  "tipologia_normal_mas_cercana": "Normal_single_large",
  "firmas_disparadas": [ { "id": "F-behavioural-1", "valores": { "s_amt_ratio_mean_30d": 7.71, "s_amt_z_30d": 4.9 } } ],
  "evidencia": [ { "feature": "s_amt_z_30d", "valor": 4.9 } ],
  "mitigantes": ["…"], "objeciones": ["…"], "confianza": 70,
  "consultas_sugeridas": ["contrapartes_90d"], "tiempo_agente_ms": 34000
}
```

## Lo que les deja el agente de aprendizaje

Después de cada tanda, el agente de aprendizaje lee todos los dictámenes y escribe `propuestas_para_ml.json`:

| Bloque | Qué trae | Cómo usarlo |
|---|---|---|
| `propuestas_umbral` | Modo, umbral (cierre o alta prioridad), valor actual, propuesto, motivo y los `case_id` que lo sostienen | Candidatos para `thresholds_v2`; los umbrales los cambian ustedes, el agente solo propone |
| `etiquetas_familia` | `case_id`, familia de la API y familia inferida por el agente | Etiquetas débiles para entrenar `train_family.py` |
| `riesgos` | Lo que podría salir mal si se aplican | Para decidir con cuidado |

Reglas en código: ninguna propuesta mueve un parámetro más de 25 %, con menos de 5 casos no propone nada, y cada `case_id` citado existe. Las propuestas sobre firmas del negocio solo se aplican si alguien las aprueba.

## El ciclo de aprendizaje (lo que pidió el jurado)

1. **Parámetros iniciales sin inventar:** bandas y umbrales de `thresholds_v1` (ML) y firmas del skill de negocio.
2. **Etiquetas:** la decisión del agente (`actor: agent`) y después la del analista desde la bandeja (`actor: analyst`: `approved`, `rejected`, `sar_filed`).
3. **El agente propone parámetros nuevos:** con el acuerdo y desacuerdo agente ↔ analista por banda y por familia, propone mover los umbrales de cada modo (cierre y alta prioridad) y ajustar las firmas. Eso mueve el "espectro" del tablero de `/thresholds`.
4. **ML se alimenta del agente:** familia inferida como etiqueta débil para `train_family.py` y las propuestas de umbral para `thresholds_v2`.

## Lo que necesitamos de ustedes

1. **Leer el feedback:** un `GET /feedback?case_id=…` o un listado por fecha, para que el agente aprenda de lo que corrige el analista.
2. **El campo opcional `agent_payload`** en `/feedback`.
3. **Un lugar para las propuestas de umbral:** por ejemplo `POST /thresholds/proposals`, o las mandamos en `notes`.
4. **10 `case_id` con su etiqueta real**, solo para evaluar al agente (la API no la entrega, y está bien).
5. **La moneda de cada transacción en `GET /cases/{id}`**: hoy `payment_currency` y `received_currency` no vienen en el detalle del caso.
6. **Cambiar la API key**: la de la guía es pública.
7. **Feedback para el caso del jurado:** `/score/live` no devuelve `case_id`, así que hoy esas decisiones no les llegan. Si devolvieran un id (o aceptaran feedback por `txn`), también las guardaríamos.
