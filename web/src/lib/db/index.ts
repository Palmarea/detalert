/* Conexión a Postgres (solo servidor). El esquema se crea solo la primera vez que se usa. */
import { Pool, type QueryResultRow } from "pg";

const g = globalThis as unknown as { __pgPool?: Pool; __pgSchema?: Promise<void> };

/* DATABASE_URL, o la que crea la integración de Neon en Vercel aunque tenga otro prefijo
   (POSTGRES_URL, STORAGE_DATABASE_URL…). En local, sin ninguna, usa el Postgres de docker-compose. */
function connectionString() {
  const env = process.env;
  const key = ["DATABASE_URL", "POSTGRES_URL"].find((k) => env[k]) ?? Object.keys(env).find((k) => /(^|_)(DATABASE_URL|POSTGRES_URL)$/.test(k) && env[k]);
  if (key) return env[key]!;
  if (process.env.NODE_ENV === "production") throw new Error("Falta DATABASE_URL: conecta la base Neon al proyecto en Vercel y vuelve a desplegar.");
  return "postgres://monitor:monitor@localhost:5433/monitor";
}

/* Se crea en la primera consulta, no al importar: así el build no necesita la base. */
export const pool = () => (g.__pgPool ??= new Pool({ connectionString: connectionString(), max: 5 }));

/* events: cada caso recibido con su contexto. status = open hasta que un analista lo marca (archivado).
   resolutions: una por caso, con quién, cuándo y la nota.
   notifications: cola de salida; el canal está por definir, así que todo queda en 'queued'.
   evidence: casos rechazados que el analista archivó como evidencia (categoría + indicadores + foto del caso)
             para alimentar análisis de riesgo futuros (listas de bloqueo, reentrenar reglas).
   agent_learning: una sola fila (id = 1) con el último cuerpo de POST /api/agent-learning (propuestas de umbrales).
   agent_events: pasos en vivo del equipo de agentes (ml → evaluador → cognitivo → … → envio). */
const SCHEMA = `
create table if not exists events (
  seq            bigserial primary key,
  id             text not null unique,
  type           text not null,
  created_at     timestamptz not null,
  received_at    timestamptz not null default now(),
  data           jsonb not null,
  context        jsonb,
  urgency_reason text,
  status         text not null default 'open' check (status in ('open', 'approved', 'rejected'))
);
create index if not exists events_open_idx on events (status, seq desc);

create table if not exists resolutions (
  id          bigserial primary key,
  event_id    text not null unique references events(id),
  action      text not null check (action in ('approved', 'rejected')),
  note        text,
  actor_email text not null,
  actor_name  text not null,
  actor_role  text not null,
  at          timestamptz not null default now()
);
create index if not exists resolutions_at_idx on resolutions (at desc);

create table if not exists notifications (
  id            bigserial primary key,
  resolution_id bigint not null references resolutions(id),
  event_id      text not null references events(id),
  channel       text not null default 'por_definir',
  status        text not null default 'queued' check (status in ('queued', 'sent', 'failed')),
  payload       jsonb not null,
  created_at    timestamptz not null default now(),
  sent_at       timestamptz
);

create table if not exists evidence (
  id            bigserial primary key,
  event_id      text not null unique references events(id),
  resolution_id bigint not null references resolutions(id),
  category      text not null,
  indicators    text[] not null default '{}',
  snapshot      jsonb not null,
  actor_email   text not null,
  at            timestamptz not null default now()
);
create index if not exists evidence_category_idx on evidence (category, at desc);

create table if not exists agent_learning (
  id         int primary key check (id = 1),
  body       jsonb not null,
  updated_at timestamptz not null default now()
);

-- agent_events: pasos del equipo de agentes en vivo (POST /api/agent-events); la bandeja los lee por polling.
create table if not exists agent_events (
  id          bigserial primary key,
  event_id    text not null,
  case_id     text,
  paso        text not null,
  estado      text not null,
  at          timestamptz,
  ms          int,
  resumen     text,
  datos       jsonb,
  received_at timestamptz not null default now()
);
create index if not exists agent_events_received_idx on agent_events (received_at);

-- Solo la zona de revisión (40 ≤ riesgo < 70) queda abierta; el resto lo califica el agente a su nombre.
-- Idempotente; misma regla que THRESHOLDS, needsReview() y agentAction() en src/lib/payments/catalog.ts
-- 1) Reabre lo que el agente archivó con una regla anterior pero cae en la zona de revisión
with r as (
  delete from resolutions r using events e
  where r.event_id = e.id and r.actor_email = 'agente@sistema' and (e.data->>'risk_score')::int between 40 and 69
  returning e.id
)
update events set status = 'open' where id in (select id from r);
-- 2) Archiva a nombre del agente lo abierto fuera de la zona de revisión
with x as (
  update events set status = case when (data->>'risk_score')::int >= 70 then 'rejected' else 'approved' end
  where status = 'open' and (data->>'risk_score')::int not between 40 and 69
  returning id, status
)
insert into resolutions (event_id, action, note, actor_email, actor_name, actor_role)
select id, status, 'Calificado por el agente al recibirlo', 'agente@sistema', 'Agente antifraude', 'Agente automático' from x;
`;

export function ready() {
  return (g.__pgSchema ??= pool().query(SCHEMA).then(
    () => undefined,
    (err) => {
      g.__pgSchema = undefined; // reintentar en la próxima llamada
      throw err;
    },
  ));
}

export async function sql<T extends QueryResultRow>(text: string, params?: unknown[]) {
  await ready();
  return (await pool().query<T>(text, params)).rows;
}
