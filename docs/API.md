# AML Scoring API — guía para el equipo

> **URL:** https://aml-scoring-api.vercel.app · **Docs interactivas:** https://aml-scoring-api.vercel.app/docs
> **Backend actual: `postgres` (Supabase, proyecto `aml-hackathon`) con data real:** 25.601 casos del período OOT jun–ago 2023 de SAML-D, puntuados por el modelo `binary_v1` con umbrales `thresholds_v1`. `POST /feedback` **persiste** en `aml.feedback`.
> **Requiere API key** (header `X-API-Key`) en todo salvo `/health` y `/docs`: ver [Autenticación](#autenticación-api-key). Pídesela al dueño de la API por privado.
> Las respuestas **no incluyen la etiqueta real** (si era lavado o no): el agente decide con el score, la banda, la familia y los reason codes, como en producción.

La API entrega, para cada transacción y cada caso, el **score calibrado**, la **banda**, la **familia de tipología** (para enrutar al agente especializado) y los **reason codes** (por qué el modelo lo marcó). La especificación completa está en [`openapi.json`](openapi.json), y con la API corriendo se puede ver de forma interactiva en `/docs`. Hay ejemplos de request y response por endpoint en [`PAYLOADS.md`](PAYLOADS.md).

## Reglas del contrato

1. **El agente puede subir la banda, nunca bajarla.** `POST /feedback` responde `422` si el agente intenta bajar la banda del modelo, por ejemplo de `high_priority` a `auto_close_eligible`.
2. **`p_laundering` es una probabilidad calibrada**: 0,02 significa ~2% de probabilidad real de lavado.
3. **La banda depende del modo de operación**, es decir, de la capacidad de analistas:

| `mode` | Capacidad | Qué cambia |
|---|---|---|
| `normal` | 100% | Auto-cierre conservador |
| `reduced_capacity` | 50% | Umbrales más estrictos: solo lo más riesgoso va a la cola |
| `no_analyst` | 0% | Más casos pasan a `high_priority` con `preventive_hold` (se retiene la transacción hasta que haya un humano) |

4. **Toda respuesta trae `model_version` y `threshold_version`**, para la trazabilidad.

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/health` | Estado, backend y versiones |
| GET | `/cases?mode=normal&band=&family=&limit=50&offset=0` | Bandeja ordenada por prioridad |
| GET | `/cases/{case_id}?mode=normal` | Detalle del caso: transacciones y reason codes |
| POST | `/score/transactions` `{"txn_ids": [...]}` | Score de transacciones puntuales |
| POST | `/score/live` | **Score en vivo de una transacción nueva** (calcula features con el historial de las cuentas) |
| GET | `/score/account/{account}?from=...&to=...` | Score agregado de una cuenta en una ventana |
| GET | `/thresholds` | Puntos de operación y su costo (auto-cierre y leakage) |
| GET | `/model/metrics` | Gini, KS, comparación con el baseline, recall por tipología y funnel |
| GET | `/audit/{txn_id}` | Snapshot de features y scores (trazabilidad) |
| POST | `/feedback` | Decisión del agente o del analista |

### Ejemplo: flujo del agente

```bash
# 1. Tomar los casos a investigar
curl "$API/cases?mode=normal&band=review&limit=10"

# 2. Ver el detalle (reason codes -> qué consultar con SQL)
curl "$API/cases/C-1234567890-2023-06-05"

# 3. Registrar la decisión (puede subir la banda, no bajarla)
curl -X POST "$API/feedback" -H 'Content-Type: application/json' \
  -d '{"case_id":"C-1234567890-2023-06-05","actor":"agent","decision":"escalated","agent_band":"review","notes":"Narrativa..."}'
```

## Scoring en vivo (`POST /score/live`)

Recibe una transacción **nueva** y devuelve su score en ~1 s. Calcula las 18 features del modelo con el historial de ambas cuentas estrictamente anterior a `ts` y corre el mismo modelo que el batch (resultado idéntico, validado en 400 transacciones).

```bash
curl -X POST "$API/score/live" -H "X-API-Key: $AML_API_KEY" -H 'Content-Type: application/json' -d '{
  "ts": "2023-08-10T05:15:22Z",
  "sender_account": "6812204903", "receiver_account": "5440521221",
  "amount": 6248.44, "payment_type": "Cross-border",
  "payment_currency": "UK pounds", "received_currency": "Euro"
}'
```

- `payment_type` debe ser uno de: `ACH`, `Cash Deposit`, `Cash Withdrawal`, `Cheque`, `Credit card`, `Cross-border`, `Debit card`.
- **`ts` es opcional.** Si se omite, se usa "ahora" = justo después del final del historial (2023-08-23).
- **Ventana válida:** el historial cubre del 1 de julio al 23 de agosto de 2023. Para `ts` anteriores al 31 de julio, las ventanas de 30 días quedan incompletas, y para `ts` muy posteriores al 23 de agosto no hay actividad reciente. En ambos casos la respuesta trae `warnings`.
- **Cuentas que no existen en el dataset** se tratan como nuevas: sin historial y con contraparte nueva.
- La respuesta incluye `features`, es decir, lo que vio el modelo, para trazabilidad.
- **`family` solo es relevante si el score es alto**, porque el clasificador se entrenó con casos de lavado.
- **La transacción no se guarda en el historial:** el endpoint es de solo lectura.

## Autenticación (API key)

Todas las rutas salvo `/health`, `/docs` y `/openapi.json` exigen el header `X-API-Key`. Sin él, o con una key incorrecta, la respuesta es `401`.

```bash
export AML_API_KEY='...'   # la key que te compartió el dueño de la API
curl -H "X-API-Key: $AML_API_KEY" "$API/cases?limit=5"
```

- **Swagger (`/docs`):** botón **Authorize** → pegar la key → todas las llamadas de prueba la incluyen.
- **En código:** léela de una variable de entorno (`AML_API_KEY`). Nunca la pongas en el repo, en un PR ni en el frontend público: en un navegador cualquiera podría verla.
- **Cómo se comparte:** por un canal privado (DM de Slack o WhatsApp, o una bóveda compartida de 1Password o Bitwarden). Nunca en un canal público, issue o commit.
- **Rotarla** (si se filtra o al terminar la hackathon): generar una nueva, reemplazar `AML_API_KEY` en Vercel (Settings → Environment Variables), redesplegar y volver a compartirla. La anterior deja de funcionar al instante.

## Backends

| `AML_BACKEND` | Datos | Requiere |
|---|---|---|
| `mock` (default) | 120 casos falsos, deterministas y realistas | Nada |
| `postgres` | Data real exportada por el batch de ML | `DATABASE_URL` |

## Correr en local

```bash
.venv/bin/uvicorn aml.api.main:app --reload
```

Queda en http://localhost:8000/docs.

## Desplegar en Vercel

El proyecto ya existe: `aml-scoring-api`, en el team `josephchomboms-projects`, con `AML_BACKEND=mock` definida. El primer despliegue se hizo subiendo los archivos directamente (sin Git). Para redesplegar desde el repo:

1. Instalar el CLI e iniciar sesión (lo hace cada uno con su cuenta): `npm i -g vercel` y luego `vercel login`.
2. Desde la raíz del repo, correr `vercel link --project aml-scoring-api` (una vez) y después `vercel --prod`. Vercel instala solo `requirements.txt` (fastapi, pydantic y psycopg, ~46 MB). El stack de ML está en `requirements-ml.txt` y no se sube.
3. En Project Settings → Environment Variables, definir:
   - `AML_BACKEND` = `mock` para empezar, o `postgres`;
   - `DATABASE_URL` = la URL del **pooler** de Postgres (Neon o Supabase). Nunca va en el repo;
   - opcionalmente, `AML_API_KEY` y `AML_CORS_ORIGINS`.

## Cargar Postgres

```bash
# Esquema + datos mock (para tener la API en modo postgres desde ya)
DATABASE_URL='postgresql://...' .venv/bin/python -m aml.api.seed_mock
```

El export con la data real (`python -m aml.export`) llega con la fase 3: casos, umbrales y puntos de operación.

## Tests

```bash
.venv/bin/pytest tests/                                                            # mock + no-fuga
AML_TEST_BACKEND=postgres DATABASE_URL=postgresql:///aml_dev .venv/bin/pytest tests/test_api.py
```
