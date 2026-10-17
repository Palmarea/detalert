/* Acceso a datos de los casos (solo servidor). */
import { pool, ready, sql } from "@/lib/db";
import { urgencyReason } from "./catalog";
import type { Decision } from "./decision";
import type { EventsPage, PaymentEvent, ResolutionAction, Urgency } from "./types";

interface Row {
  seq: string;
  id: string;
  type: PaymentEvent["type"];
  created_at: Date;
  data: PaymentEvent["data"];
  context: Decision | null;
  r_action: ResolutionAction | null;
  r_note: string | null;
  r_at: Date | null;
  r_email: string | null;
  r_name: string | null;
  r_role: string | null;
  n_channel: string | null;
  n_status: "queued" | "sent" | "failed" | null;
}

const SELECT = `
  select e.seq, e.id, e.type, e.created_at, e.data, e.context,
         r.action r_action, r.note r_note, r.at r_at, r.actor_email r_email, r.actor_name r_name, r.actor_role r_role,
         n.channel n_channel, n.status n_status
  from events e
  left join resolutions r on r.event_id = e.id
  left join notifications n on n.resolution_id = r.id`;

function toEvent(r: Row): PaymentEvent {
  return {
    id: r.id,
    type: r.type,
    created_at: r.created_at.toISOString(),
    data: r.data,
    ...(r.context ? { context: r.context } : {}),
    ...(r.r_action && r.r_at
      ? {
          resolution: {
            action: r.r_action,
            note: r.r_note,
            at: r.r_at.toISOString(),
            by: { email: r.r_email!, name: r.r_name!, role: r.r_role! },
            notification: r.n_channel && r.n_status ? { channel: r.n_channel, status: r.n_status } : null,
          },
        }
      : {}),
  };
}

/* Guarda eventos entrantes. Idempotente: si el id ya existe, se ignora. */
export async function saveEvents(items: { event: PaymentEvent; context?: Decision }[]) {
  await ready();
  let inserted = 0;
  for (const { event: e, context } of items) {
    const res = await pool.query(
      `insert into events (id, type, created_at, data, context, urgency_reason)
       values ($1, $2, $3, $4, $5, $6) on conflict (id) do nothing`,
      [e.id, e.type, e.created_at, e.data, context ?? null, urgencyReason(e)],
    );
    inserted += res.rowCount ?? 0;
  }
  return inserted;
}

/* Casos abiertos para el monitor. Cursor = "<último seq de evento>.<último id de resolución>". */
export async function openEvents(cursor: string | null): Promise<EventsPage> {
  if (!cursor) {
    const rows = await sql<Row>(`${SELECT} where e.status = 'open' order by e.seq desc limit 500`);
    const [{ max }] = await sql<{ max: string | null }>(`select max(id)::text max from resolutions`);
    const newest = rows[0]?.seq ?? 0;
    return { events: rows.reverse().map(toEvent), closed: [], cursor: `${newest}.${max ?? 0}` };
  }
  const [es, rs] = cursor.split(".").map((n) => Number(n) || 0);
  const rows = await sql<Row>(`${SELECT} where e.status = 'open' and e.seq > $1 order by e.seq limit 200`, [es]);
  const closed = await sql<{ id: string; event_id: string }>(`select id::text, event_id from resolutions where id > $1 order by id`, [rs]);
  return {
    events: rows.map(toEvent),
    closed: closed.map((c) => c.event_id),
    cursor: `${rows.at(-1)?.seq ?? es}.${closed.at(-1)?.id ?? rs}`,
  };
}

type Actor = { email: string; name: string; role: string };

/* Marca un caso: lo archiva, registra quién/cuándo/nota y deja la notificación en cola. Todo en una transacción. */
export async function resolveEvent(id: string, action: ResolutionAction, note: string | null, by: Actor) {
  await ready();
  const c = await pool.connect();
  try {
    await c.query("begin");
    const cur = await c.query<{ status: string; data: PaymentEvent["data"]; type: string }>(
      `select status, data, type from events where id = $1 for update`,
      [id],
    );
    if (!cur.rowCount) {
      await c.query("rollback");
      return { ok: false as const, status: 404, error: "El caso no existe." };
    }
    if (cur.rows[0].status !== "open") {
      await c.query("rollback");
      const [prev] = await sql<{ actor_name: string; action: string }>(`select actor_name, action from resolutions where event_id = $1`, [id]);
      const verb = prev?.action === "approved" ? "aprobó" : "rechazó";
      return { ok: false as const, status: 409, error: prev ? `${prev.actor_name} ya lo ${verb}.` : "El caso ya fue archivado." };
    }
    const d = cur.rows[0].data;
    await c.query(`update events set status = $2 where id = $1`, [id, action]);
    const res = await c.query<{ id: string; at: Date }>(
      `insert into resolutions (event_id, action, note, actor_email, actor_name, actor_role)
       values ($1, $2, $3, $4, $5, $6) returning id::text, at`,
      [id, action, note, by.email, by.name, by.role],
    );
    const r = res.rows[0];
    await c.query(`insert into notifications (resolution_id, event_id, payload) values ($1, $2, $3)`, [
      r.id,
      id,
      {
        event_id: id,
        type: cur.rows[0].type,
        action,
        note,
        by,
        at: r.at.toISOString(),
        payment_id: d.payment_id,
        amount: d.amount,
        currency: d.currency,
        merchant: d.merchant,
        customer: d.customer.name,
      },
    ]);
    await c.query("commit");
    return { ok: true as const };
  } catch (err) {
    await c.query("rollback").catch(() => {});
    throw err;
  } finally {
    c.release();
  }
}

export interface HistoryFilter {
  q?: string;
  outcome?: ResolutionAction | "all";
  urgency?: Urgency;
  analyst?: string; // email
  from?: string; // YYYY-MM-DD
  to?: string;
  limit?: number;
  offset?: number;
}

/* Casos archivados con filtros. Fechas en hora de Lima. */
export async function history(f: HistoryFilter) {
  const where = [`e.status <> 'open'`];
  const p: unknown[] = [];
  const add = (cond: string, v: unknown) => {
    p.push(v);
    where.push(cond.replaceAll("$?", `$${p.length}`));
  };
  if (f.q) add(`(e.id ilike $? or e.data->>'payment_id' ilike $? or e.data->>'order_id' ilike $? or e.data->'customer'->>'name' ilike $? or e.data->>'merchant' ilike $? or r.note ilike $?)`, `%${f.q}%`);
  if (f.outcome && f.outcome !== "all") add(`r.action = $?`, f.outcome);
  if (f.urgency === "urgent") where.push(`e.urgency_reason is not null`);
  if (f.urgency === "normal") where.push(`e.urgency_reason is null`);
  if (f.analyst) add(`r.actor_email = $?`, f.analyst);
  if (f.from) add(`r.at >= ($?::date at time zone 'America/Lima')`, f.from);
  if (f.to) add(`r.at < (($?::date + 1) at time zone 'America/Lima')`, f.to);

  const limit = Math.min(100, f.limit ?? 50);
  const rows = await sql<Row & { total: string }>(
    `${SELECT} where ${where.join(" and ")} order by r.at desc limit ${limit} offset ${Math.max(0, f.offset ?? 0)}`,
    p,
  );
  const [{ total }] = await sql<{ total: string }>(
    `select count(*)::text total from events e left join resolutions r on r.event_id = e.id where ${where.join(" and ")}`,
    p,
  );
  const analysts = await sql<{ email: string; name: string }>(
    `select distinct actor_email email, actor_name name from resolutions order by name`,
  );
  return { events: rows.map(toEvent), total: Number(total), analysts };
}
