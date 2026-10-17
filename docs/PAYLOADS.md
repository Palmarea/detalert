# AML Scoring API — payloads por endpoint

Base URL: `https://aml-scoring-api.vercel.app` · Docs interactivas: `/docs`

Los ejemplos son respuestas reales del backend `mock` (las listas largas están recortadas). Con data real cambian los valores, no los campos.
Si `AML_API_KEY` está definida, todo salvo `/health` exige el header `X-API-Key`.

**Valores posibles**

- `band`: `auto_close_eligible` · `review` · `high_priority`
- `family`: `structuring` · `layering` · `concentration` · `cash` · `behavioural` · `generic` (confianza < 0.5 → agente general)
- `mode`: `normal` (100% analistas) · `reduced_capacity` (50%) · `no_analyst` (0%)

---

## 1. `GET /health` — ¿la API está viva y qué versión corre?

Sin parámetros ni API key.

```json
{
  "status": "ok",
  "backend": "mock",
  "model_version": "binary_v1-mock",
  "threshold_version": "thresholds_v1-mock"
}
```

---

## 2. `GET /cases` — bandeja de casos ordenada por prioridad

Un **caso** agrupa las transacciones de una cuenta en una ventana de tiempo. Es lo que investiga el agente.

| Query | Default | Descripción |
|---|---|---|
| `mode` | `normal` | Cambia los umbrales y, por tanto, la banda de cada caso |
| `band` | — | Filtra por banda |
| `family` | — | Filtra por familia (para enrutar al agente especializado) |
| `limit` | 50 | 1–500 |
| `offset` | 0 | Paginación |

`GET /cases?mode=normal&limit=2`

```json
{
  "mode": "normal",
  "total": 120,
  "cases": [
    {
      "case_id": "C-9733937073-2023-07-03",
      "account": "9733937073",
      "window_start": "2023-07-03T08:00:00Z",
      "window_end": "2023-07-03T08:00:00Z",
      "n_transactions": 5,
      "n_flagged": 1,
      "total_amount_flagged": 15972.2,
      "case_score": 0.9986,
      "band": "high_priority",
      "family": "concentration",
      "priority_rank": 1,
      "model_version": "binary_v1-mock",
      "threshold_version": "thresholds_v1-mock"
    }
  ]
}
```

- `case_score`: probabilidad calibrada de que el caso sea lavado.
- `n_flagged`: transacciones del caso que superan `alert_threshold`.
- `priority_rank`: 1 es el más urgente dentro del `mode` pedido.

---

## 3. `GET /cases/{case_id}` — detalle de un caso

Query opcional: `mode` (default `normal`). Devuelve lo mismo que un ítem de `/cases`, más las transacciones y los reason codes principales del caso. 404 si el caso no existe.

`GET /cases/C-9733937073-2023-07-03`

```json
{
  "case_id": "C-9733937073-2023-07-03",
  "account": "9733937073",
  "case_score": 0.9986,
  "band": "high_priority",
  "family": "concentration",
  "...": "(resto de campos de CaseSummary)",
  "transactions": [
    {
      "txn_id": 9134336,
      "ts": "2023-07-03T08:00:00Z",
      "sender_account": "9733937073",
      "receiver_account": "4467888399",
      "amount": 15972.2,
      "payment_type": "Debit card",
      "p_laundering": 0.8848,
      "band": "review",
      "family": "concentration",
      "family_confidence": 0.626,
      "reason_codes": [
        {
          "code": "CURRENCY_MISMATCH",
          "feature": "currency_mismatch",
          "value": 1.0,
          "contribution": 2.782,
          "text": "La moneda de pago y la de recepción no coinciden"
        }
      ],
      "model_version": "binary_v1-mock",
      "threshold_version": "thresholds_v1-mock"
    }
  ],
  "top_reason_codes": [
    {
      "code": "SENDER_DORMANT",
      "feature": "s_hours_since_prev",
      "value": 194.0,
      "contribution": 3.166,
      "text": "El emisor llevaba 194.0 h sin operar"
    },
    {
      "code": "NEW_COUNTERPARTY",
      "feature": "is_new_counterparty",
      "value": 1.0,
      "contribution": 0.972,
      "text": "Primera transacción hacia esta contraparte"
    }
  ]
}
```

**Reason code:** `feature` es la variable del modelo, `value` es su valor en esa transacción y `contribution` es su aporte SHAP al log-odds (mayor = empuja más hacia "lavado"). `text` ya viene listo para la narrativa del agente.

---

## 4. `POST /score/transactions` — score de transacciones puntuales

Request (entre 1 y 1000 ids):

```json
{ "txn_ids": [9134336, 999999999] }
```

Response: un `TxnScore` por id encontrado (mismo formato que `transactions[]` en el detalle del caso). Los que no existen van a `not_found`.

```json
{
  "results": [
    {
      "txn_id": 9134336,
      "p_laundering": 0.8848,
      "band": "review",
      "family": "concentration",
      "family_confidence": 0.626,
      "reason_codes": ["..."],
      "...": "(resto de campos de TxnScore)"
    }
  ],
  "not_found": [999999999]
}
```

---

## 5. `GET /score/account/{account}?from=...&to=...` — score agregado de una cuenta

`from` y `to` son obligatorios, en ISO 8601. Sin zona horaria se interpretan como UTC. Toma las transacciones **enviadas** por la cuenta en esa ventana. 404 si no hay ninguna.

`GET /score/account/9733937073?from=2023-06-01T00:00:00&to=2023-08-31T23:59:59`

```json
{
  "account": "9733937073",
  "window_start": "2023-06-01T00:00:00Z",
  "window_end": "2023-08-31T23:59:59Z",
  "n_transactions": 1,
  "max_p_laundering": 0.8848,
  "mean_p_laundering": 0.8848,
  "n_flagged": 1,
  "band": "review",
  "model_version": "binary_v1-mock",
  "threshold_version": "thresholds_v1-mock"
}
```

La `band` sale de `max_p_laundering` con los umbrales del modo `normal`.

---

## 6. `GET /thresholds` — puntos de operación según capacidad de analistas

```json
{
  "threshold_version": "thresholds_v1-mock",
  "alert_threshold": 0.01,
  "operating_points": [
    {
      "mode": "normal",
      "analyst_capacity_pct": 100,
      "auto_close_threshold": 0.05,
      "high_priority_threshold": 0.9,
      "auto_close_rate": 0.35,
      "expected_leakage": 0.002,
      "missed_laundering_pct": null,
      "queue_cases_per_day": 40.0,
      "preventive_hold": false
    },
    { "mode": "reduced_capacity", "analyst_capacity_pct": 50, "auto_close_threshold": 0.12, "high_priority_threshold": 0.8, "...": "..." },
    { "mode": "no_analyst", "analyst_capacity_pct": 0, "high_priority_threshold": 0.5, "preventive_hold": true, "...": "..." }
  ]
}
```

- `alert_threshold`: `p_laundering` mínima para que una transacción entre a un caso.
- `case_score < auto_close_threshold` → `auto_close_eligible`; `≥ high_priority_threshold` → `high_priority`; lo de en medio → `review`.
- `auto_close_rate`: % de casos que se cierran solos. `expected_leakage`: % de esos auto-cierres que en realidad eran lavado.
- `preventive_hold: true`: sin analista, los `high_priority` retienen la transacción hasta que la revise un humano.

---

## 7. `GET /model/metrics` — desempeño del modelo (para el dashboard o el pitch)

```json
{
  "sample": "oot",
  "gini": 99.94,
  "ks": 98.21,
  "pr_auc": 0.9756,
  "recall_at_1pct": 0.9898,
  "baseline_gini": 44.7,
  "recall_by_typology": { "Smurfing": 0.947, "Cash_Withdrawal": 0.975, "Structuring": 1.0 },
  "funnel": [
    { "stage": "transacciones", "n_in": 2456064, "n_out": 2456064, "positives_out": 2837, "leakage": 0.0 },
    { "stage": "alertas",       "n_in": 2456064, "n_out": 24561,   "positives_out": 2808, "leakage": 0.0102 },
    { "stage": "casos",         "n_in": 24561,   "n_out": 3900,    "positives_out": 2808, "leakage": 0.0 },
    { "stage": "escalados",     "n_in": 3900,    "n_out": 2500,    "positives_out": 2802, "leakage": 0.002 }
  ],
  "model_version": "binary_v1-mock",
  "threshold_version": "thresholds_v1-mock"
}
```

`funnel` muestra cuánto volumen elimina cada etapa (`n_in` → `n_out`) y cuánto lavado real se pierde en ella (`leakage`).

---

## 8. `GET /audit/{txn_id}` — trazabilidad de una decisión

Qué vio exactamente el modelo al puntuar la transacción. 404 si no hay registro.

```json
{
  "txn_id": 9134336,
  "scored_at": "2023-07-03T08:00:02Z",
  "features_snapshot": {
    "currency_mismatch": 1.0,
    "s_amt_ratio_mean_30d": 10.3,
    "r_out_cnt_7d": 23.0,
    "amount": 15972.2
  },
  "score_raw": 0.999,
  "p_laundering": 0.8848,
  "band": "review",
  "family": "concentration",
  "reason_codes": ["..."],
  "model_version": "binary_v1-mock",
  "threshold_version": "thresholds_v1-mock"
}
```

`score_raw` es la salida del LightGBM antes de calibrar; `p_laundering` es la probabilidad calibrada. Con data real, `features_snapshot` trae las 18 features del modelo.

---

## 9. `POST /feedback` — decisión del agente o del analista

Request:

```json
{
  "case_id": "C-9733937073-2023-07-03",
  "actor": "agent",
  "decision": "escalated",
  "agent_band": "high_priority",
  "notes": "Fan-in de 14 emisores nuevos en 48h"
}
```

| Campo | Valores |
|---|---|
| `actor` | `agent` · `analyst` |
| `decision` | `auto_closed` · `escalated` · `high_priority` · `approved` (analista confirma al agente) · `rejected` (analista lo revierte) · `sar_filed` (reporte emitido) |
| `agent_band` | Opcional. Banda final del agente: solo puede ser **igual o mayor** que la del modelo |
| `notes` | Opcional. Narrativa libre |

Response `201`:

```json
{ "feedback_id": "ec6fd38d-0879-466a-a837-cb2eb282356f", "received_at": "2026-10-17T18:21:28.452688Z" }
```

Response `422` si el agente intenta bajar la banda:

```json
{ "detail": "El agente no puede bajar la banda: modelo=high_priority, agente=auto_close_eligible" }
```

En `mock` el feedback se valida pero no se guarda; en `postgres` sí.

---

## Errores comunes

| Código | Cuándo |
|---|---|
| 401 | Falta `X-API-Key` o es incorrecta (solo si `AML_API_KEY` está definida) |
| 404 | Caso, transacción o cuenta sin datos |
| 422 | Body o query inválidos, o el agente intenta bajar la banda |
