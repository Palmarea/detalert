# Monitor de pagos

Monitor de casos de pago para analistas de fraude: los eventos llegan con su contexto (decisión, factores, reglas, auditoría), el analista los aprueba o rechaza, y cada decisión queda archivada en Postgres con su notificación en cola.

```bash
npm install
npm run db:up      # Postgres en Docker (puerto 5433)
npm run dev        # app en http://localhost:3000
npm run feed       # en otra terminal: simula la fuente de eventos
```

## Estructura

```
scripts/feed.ts                         # simulador de la fuente: genera evento + contexto → POST /api/ingest
src/
  middleware.ts                         # exige sesión (salvo /login y /api/ingest)
  app/
    page.tsx                            # bandeja de casos abiertos
    historial/page.tsx                  # casos archivados con filtros
    api/ingest/route.ts                 # POST: entrada de eventos (token INGEST_TOKEN)
    api/events/route.ts                 # GET: casos abiertos (polling)
    api/events/[id]/resolve/route.ts    # POST: aprobar / rechazar
    api/history/route.ts                # GET: consulta del historial
  components/monitor/                   # Monitor, History, EventCard, EventDetail, Agent
  lib/db/index.ts                       # conexión y esquema (se crea solo)
  lib/payments/
    ingest.ts                           # adaptIncoming(): único punto a ajustar al definir la fuente real
    repo.ts                             # consultas: guardar, abiertos, resolver, historial
    decision.ts                         # tipo del contexto + generador simulado (lo usa el feed)
    catalog.ts                          # tipos, filtros y criterios de urgencia
docs/flujo-eventos.md                   # flujo completo y contratos
```

## Acceso (demo)

Todo el sitio exige sesión. `/login` tiene accesos de un clic; también se puede escribir el correo y la contraseña:

| Usuario | Rol | Contraseña |
|---|---|---|
| `analista@demo.local` | Analista de fraude | `demo1234` |
| `supervisor@demo.local` | Supervisor de riesgo | `demo1234` |

- La sesión es una cookie httpOnly firmada con HMAC-SHA256 (`src/lib/auth/session.ts`) y dura 8 h.
- `src/middleware.ts` redirige a `/login` las páginas sin sesión y responde 401 en `/api/*`.
- En producción hay que definir `AUTH_SECRET` (`openssl rand -base64 32`); sin él la app no arranca.
- Los usuarios viven en `src/lib/auth/users.ts`: reemplazar por el proveedor de identidad real.

## Fuente de eventos

El mecanismo real aún no está definido. Sea cual sea (webhook, cola, pull), debe terminar enviando a:

```
POST /api/ingest
Authorization: Bearer <INGEST_TOKEN>      # en desarrollo: dev-ingest-token
{ "events": [ { "event": PaymentEvent, "context": Decision } ] }
```

Es idempotente (un `id` repetido se ignora). Si el formato real es otro, solo se ajusta `adaptIncoming()` en `src/lib/payments/ingest.ts`.

`npm run feed` simula esa fuente: envía un historial de 15 eventos (3 urgentes) y luego uno cada 2,5–6,5 s. Opciones: `--no-history`, `--once`, `--url <base>`.

## Base de datos

| Tabla | Qué guarda |
|---|---|
| `events` | cada caso con su `data`, su `context` y `status` (`open` → `approved`/`rejected`) |
| `resolutions` | quién lo decidió, cuándo, la acción y la nota (una por caso) |
| `notifications` | cola de salida, canal `por_definir`, estado `queued` |

Consultar a mano: `docker compose exec db psql -U monitor`. Borrar todo: `docker compose down -v`.

Detalle del flujo en [docs/flujo-eventos.md](docs/flujo-eventos.md).
