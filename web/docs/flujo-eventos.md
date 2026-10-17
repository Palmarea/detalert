# Flujo de reporte de transacciones como eventos

## 1. Cómo funciona hoy (prototipo `Monitor de Pagos.html`)

Todo ocurre en el navegador. No hay backend: un simulador inventa eventos y los mete en memoria.

```mermaid
flowchart TD
    A([Carga de la página]) --> B[Genera 15 eventos de historial<br/>fakeEvent con fechas pasadas]
    B --> C[ingest silent:true<br/>sin marcar como no leídos]
    C --> D[Selecciona el más reciente<br/>y muestra su detalle]
    D --> T

    T[[tick cada 2.5 – 6.5 s]] --> F[fakeEvent: sortea el tipo<br/>58% aprobado · 16% pendiente · 16% rechazado<br/>7% reembolso · 3% contracargo]
    F --> G[Arma data + history según el tipo<br/>failure_code / refund_id / dispute_reason]
    G --> H{¿Stream en vivo?}
    EXT[/window.pushPaymentEvent<br/>punto de entrada para fuente real/] -.-> H

    H -- No, en pausa --> P[Se guarda en state.pending]
    P --> NB[Barra: N eventos nuevos en pausa · mostrar]
    NB -- clic o reanudar --> FL[flushPending: pasan a la lista<br/>marcados como no leídos]

    H -- Sí --> U[unshift al inicio de state.events]
    U --> CAP{¿más de 500?}
    CAP -- Sí --> POP[Descarta el más antiguo]
    CAP -- No --> UR
    POP --> UR[Marca como no leído]
    FL --> R
    UR --> R[renderStats<br/>total · S/ aprobado solo PEN · fallidos+contracargos]
    R --> L[renderList: aplica filtro de estado + búsqueda<br/>animación fresh en el nuevo]
    L --> T

    L --> SEL([Usuario hace clic o usa ↑↓ / j k])
    SEL --> DET[renderDetail: alerta según estado,<br/>pago, cliente, línea de tiempo, payload JSON]
    DET --> RD[Quita marca de no leído]

    CLK[[setInterval 5 s]] --> REL[Refresca los textos 'hace Ns']
```

**Puntos clave del flujo actual**

| Etapa | Qué pasa | Limitación |
|---|---|---|
| Origen | `fakeEvent()` en el navegador | Datos ficticios, nada persiste |
| Ingesta | `ingest()` decide lista o `pending` según pausa | No deduplica: si llega el mismo evento dos veces, aparece dos veces |
| Almacenamiento | Arreglo en memoria, tope 500 | Al recargar se pierde todo |
| Estadísticas | Se calculan sobre lo que hay en memoria | "Aprobado" ignora USD; solo cuenta lo visible en la sesión |
| Detalle | Se re-renderiza todo el HTML con `innerHTML` | — |

## 2. Cómo queda en Next.js (este repo)

El navegador ya no genera nada: pregunta cada 3 s a `/api/events` por los eventos posteriores al último cursor.
La ruta decide si usa el simulador o el endpoint real, así que el cambio a producción es solo configurar variables de entorno.

```mermaid
flowchart LR
    subgraph Navegador
      M[Monitor.tsx] --> HK[usePaymentStream<br/>polling cada NEXT_PUBLIC_EVENTS_POLL_MS]
      HK -- "GET /api/events?since=cursor" --> API
      API -- "{ events[], cursor }" --> RED[reducer ingest<br/>dedupe por id · pausa → pending · tope 500]
      RED --> M
      HK -. error .-> BO[backoff ×2 hasta 30 s<br/>indicador 'Sin conexión']
    end

    subgraph Servidor Next.js
      API[app/api/events/route.ts] --> Q{¿EVENTS_UPSTREAM_URL?}
      Q -- No --> MOCK[lib/payments/mock.ts<br/>genera eventos entre since y ahora]
      Q -- Sí --> UP[fetch al endpoint real<br/>Bearer EVENTS_UPSTREAM_TOKEN]
      UP --> AD[adaptUpstream<br/>normaliza y ordena]
    end

    UP --> EXT[(Endpoint de transacciones)]
```

### Contrato esperado del endpoint

```
GET <EVENTS_UPSTREAM_URL>?since=<cursor>&limit=<n>

200 OK
{
  "events": [ PaymentEvent, ... ],   // del más antiguo al más nuevo
  "cursor": "..."                    // se envía como `since` en la siguiente llamada
}
```

- Sin `since` → devolver el historial reciente (la primera carga).
- `PaymentEvent` está definido en `src/lib/payments/types.ts`.
- Si el endpoint real usa otro formato (otros nombres de campo, montos en soles en vez de céntimos, paginación distinta), solo hay que cambiar `adaptUpstream()`.

## 3. Flujo actual: casos con decisión del analista (Postgres)

El navegador ya no recibe eventos sueltos sino **casos**: cada evento llega con su contexto, queda abierto hasta que un analista lo decide, y luego se archiva.

```mermaid
flowchart LR
    subgraph Fuente["Fuente de eventos (por definir)"]
      FEED[scripts/feed.ts<br/>simulador: evento + contexto]
    end
    FEED -- "POST /api/ingest<br/>Bearer INGEST_TOKEN" --> ING[adaptIncoming<br/>valida y normaliza]
    ING --> DB[(Postgres<br/>events · status=open)]

    subgraph Navegador
      MON[Bandeja<br/>urgentes primero] -- "GET /api/events?since=cursor<br/>cada 3 s" --> API
      MON -- "Aprobar / Rechazar + nota<br/>(doble clic para confirmar)" --> RES
      HIS[Historial<br/>filtros: texto, resultado, urgencia,<br/>analista, fechas] -- "GET /api/history" --> HQ
    end

    API[/api/events/] --> DB
    API -- "events nuevos + closed (archivados)" --> MON
    RES[/api/events/:id/resolve/] -- "una transacción" --> TX[events.status = approved/rejected<br/>+ resolutions quién/cuándo/nota<br/>+ notifications en cola]
    TX --> DB
    HQ[/api/history/] --> DB
    DB -.-> NOTI[[notifications · queued<br/>canal por definir]]
```

- Si dos analistas deciden el mismo caso, el segundo recibe 409 («Diego Ramos ya lo rechazó») y el caso sale de su bandeja.
- Cuando cualquier analista archiva un caso, desaparece de la bandeja de todos en el siguiente polling (`closed`).
- Las notificaciones quedan en `notifications` con `status = queued`; falta definir el canal y el proceso que las envíe.
