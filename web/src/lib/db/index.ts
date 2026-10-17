/* Conexión a Postgres (solo servidor). El esquema se crea solo la primera vez que se usa. */
import { Pool, type QueryResultRow } from "pg";

const g = globalThis as unknown as { __pgPool?: Pool; __pgSchema?: Promise<void> };

export const pool = (g.__pgPool ??= new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://monitor:monitor@localhost:5433/monitor",
  max: 5,
}));

/* events: cada caso recibido con su contexto. status = open hasta que un analista lo marca (archivado).
   resolutions: una por caso, con quién, cuándo y la nota.
   notifications: cola de salida; el canal está por definir, así que todo queda en 'queued'. */
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
`;

export function ready() {
  return (g.__pgSchema ??= pool.query(SCHEMA).then(
    () => undefined,
    (err) => {
      g.__pgSchema = undefined; // reintentar en la próxima llamada
      throw err;
    },
  ));
}

export async function sql<T extends QueryResultRow>(text: string, params?: unknown[]) {
  await ready();
  return (await pool.query<T>(text, params)).rows;
}
