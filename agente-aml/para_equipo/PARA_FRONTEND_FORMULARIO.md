# Formulario "Probar un caso" con los pasos del agente en vivo

**Objetivo:** el jurado escribe una transacción en la bandeja, pulsa **Ejecutar** y ve cómo la piensan los agentes paso a paso. En unos 40–60 s aparece el caso terminado en la bandeja.

**Cómo funciona:** el agente no recibe conexiones; va a buscar el trabajo. La bandeja guarda la solicitud, el agente la recoge cada 3 s, ML la puntúa en vivo (`/score/live`), los agentes la analizan, cada paso llega a la bandeja apenas termina y el caso final entra por `/api/ingest` como siempre.

Hay dos fases. La **Fase 1** alcanza para la demo (≈ 20 min); la **Fase 2** agrega los pasos en vivo (≈ 15 min más).

## Fase 1 · Formulario y solicitud (obligatoria)

### 1. Tabla

```sql
create table if not exists agent_requests (
  id          text primary key,
  payload     jsonb not null,
  status      text not null default 'pending',   -- pending | taken
  created_by  text,
  created_at  timestamptz not null default now()
);
```

### 2. `POST /api/agent-requests` (con sesión del analista)

- Body: `{ sender_account, receiver_account, amount, payment_type, payment_currency, received_currency }`.
- Validación:
  - cuentas: solo dígitos, de 4 a 12;
  - `amount` mayor que 0;
  - `payment_type` es uno de: `ACH`, `Cash Deposit`, `Cash Withdrawal`, `Cheque`, `Credit card`, `Cross-border`, `Debit card`;
  - monedas: texto, por defecto `UK pounds`.
- `id = "req" + Date.now().toString(36)`. **Solo letras y números**, porque el agente lo usa dentro del id del evento.
- Inserta con `status = 'pending'` y responde `{ id }`.

### 3. `GET /api/agent-requests?estado=pendiente` (máquina a máquina)

- Lo llama el agente cada 3 s con `Authorization: Bearer <INGEST_TOKEN>`, igual que `/api/ingest`.
- **Exentarlo del middleware de sesión**, como `/api/ingest`.
- Devuelve las pendientes, de la más antigua a la más nueva, como máximo 5:

```json
{ "solicitudes": [ { "id": "reqm2x7k1", "sender_account": "1111111111", "receiver_account": "2222222222", "amount": 9500, "payment_type": "Cash Deposit", "payment_currency": "UK pounds", "received_currency": "UK pounds" } ] }
```

- Al devolverlas, márcalas `status = 'taken'`. El agente además recuerda las que ya procesó.

### 4. El formulario

1. Un botón **"Probar un caso"** en la bandeja abre un modal con los 6 campos: `payment_type` como lista y las monedas ya llenas con `UK pounds`.
2. **Ejecutar** hace el `POST`, guarda el `id` y muestra "El agente está analizando…".
3. Polling cada 2 s a `GET /api/events` (ya existe), buscando un evento cuyo `id` **termine en `_<id>`**. El id final es `evt_aml_jurado_<AAAAMMDDhhmmss>_<id>`.
4. Cuando llega, abre su detalle y muestra `context.aml.pasos` como línea de tiempo. Detalle en `PARA_FRONTEND.md`.

## Fase 2 · Pasos en vivo (recomendada si da el tiempo)

### 5. Tabla

```sql
create table if not exists agent_events (
  id           bigserial primary key,
  event_id     text not null,
  case_id      text,
  paso         text not null,        -- evaluador | cognitivo | contexto | decisor | compuerta | envio
  estado       text not null,        -- fin | error | omitido
  at           timestamptz,
  ms           integer,
  resumen      text,
  datos        jsonb,
  received_at  timestamptz not null default now()
);
create index if not exists agent_events_event_id on agent_events (event_id);
```

### 6. `POST /api/agent-events` (máquina a máquina)

- `Authorization: Bearer <INGEST_TOKEN>` y exento de sesión, como `/api/ingest`.
- Body (uno por paso, apenas termina):

```json
{ "case_id": "jurado_20261017213000_reqm2x7k1", "event_id": "evt_aml_jurado_20261017213000_reqm2x7k1", "paso": "cognitivo", "estado": "fin", "at": "2026-10-17T21:30:12Z", "ms": 11659, "resumen": "Familia inferida structuring (el modelo decía structuring) con 3 evidencias", "datos": { } }
```

- Inserta y responde 200. Si falla, el agente sigue igual.

### 7. `GET /api/agent-events?request=<id>` (con sesión)

Devuelve los pasos cuyo `event_id` termina en `_<id>`, ordenados por `at`.

### 8. En el modal, mientras espera

Polling cada 1 s a ese `GET`. Pinta cada paso con un punto, su `resumen` y su tiempo en segundos; en `error` usa rojo y en `omitido` gris. Son unos 6 pasos en unos 40 s:

1. **Evaluador:** banda del modelo y firmas del negocio disparadas.
2. **Cognitivo:** familia inferida y evidencia.
3. **Contexto:** historial de 30 días de las dos cuentas, si el agente lo pidió.
4. **Decisor:** explicación legítima, objeciones, decisión y confianza.
5. **Compuerta:** controles superados y la banda final, que nunca baja.
6. **Envío:** entregado a la bandeja.

## Cómo replicar en pantalla la "ventana del agente"

Esto es lo que el agente muestra en su terminal para un caso real del jurado, y de dónde lo saca la bandeja:

```
Modelo: banda review · p_laundering 0.0121
Firmas disparadas: ninguna
Familia: API structuring → inferida generic
Evidencia:
  - is_new_counterparty = 1: Primera transacción hacia este receptor…
  - amount = 9500: Monto justo bajo el umbral de reporte de 10,000…
Objeciones:
  - Sin historial del emisor siempre vale 1: refleja el arranque en frío más que un riesgo propio…
Decisión: escalated · agent_band review · confianza 66
Pasos:
  1. evaluador [fin]: Banda review; firmas disparadas: ninguna · 1 ms
  2. cognitivo [fin]: Propuso familia generic y INVESTIGATE_FURTHER; confianza 62 · 22298 ms
  3. contexto [omitido]: El cognitivo no pidió más transacciones · 0 ms
  4. decisor [fin]: Recomendó INVESTIGATE_FURTHER; familia final generic; 3 objeciones; confianza 66 · 20787 ms
  5. compuerta [fin]: A1-A7 superados; decisión escalated (review) · 11 ms
  6. envio [omitido]: No aplica: transacción en vivo sin case_id · 0 ms
```

| Línea de la ventana | Mientras piensa (Fase 2) | Cuando termina (en el evento) |
|---|---|---|
| Pasos 1 a 6 | Cada fila de `agent_events`, en orden, con `resumen` y `ms` | `context.aml.pasos` |
| Modelo: banda y probabilidad | `datos` del paso `evaluador` | `context.aml.banda_modelo` y `data.risk_score` |
| Firmas disparadas | `datos` del paso `evaluador` | `context.aml.firmas` (las de `disparada: true`) |
| Familia API → inferida | `resumen` del paso `cognitivo` | `context.aml.familia_api` → `context.aml.familia_inferida` |
| Evidencia | — | `context.aml.evidencia` (`feature`, `valor`, `interpretacion`) |
| Objeciones | Cuántas, en el paso `decisor` | `context.aml.objeciones` y `context.aml.explicacion_legitima` |
| Decisión, banda y confianza | Paso `compuerta` | `context.aml.decision_contrato`, `agent_band`, `confianza` |
| Narrativa | — | `context.aml.narrativa` (y la última entrada de `data.history`) |

**Sugerencia de pantalla:** a la izquierda, la línea de tiempo que se llena paso a paso; a la derecha, al terminar, tres tarjetas: **Evidencia**, **Abogado del diablo** (objeciones y explicación legítima) y **Decisión** (con la flecha banda del modelo → banda del agente).

## Seguridad

- No pongan ninguna key de ML en el frontend: el agente es el único que habla con ML.
- Los dos endpoints de máquina usan el mismo `INGEST_TOKEN`; los de pantalla, la sesión del analista.

## Cuando esté listo

Avísennos la URL. Del lado del agente basta con prender la vigilancia; prueben juntos con el caso de ejemplo `1111111111 → 2222222222 · 9500 · Cash Deposit`.
