"""Features point-in-time sobre `transactions` -> tabla `features`.

Regla de oro: toda agregación histórica usa solo transacciones ESTRICTAMENTE
anteriores a la actual (ni siquiera las del mismo segundo). Los atributos de la
propia transacción (monto, tipo de pago, ubicaciones) sí se usan: se conocen al
momento de puntuarla.

Uso:
    python -m aml.features
"""

import time

import duckdb

from aml.config import DB_PATH, TYPOLOGY_TO_FAMILY

# Frame "solo pasado": desde N días antes hasta 1 microsegundo antes de ts.
_PAST = "RANGE BETWEEN INTERVAL {n} DAY PRECEDING AND INTERVAL 1 MICROSECOND PRECEDING"
_ALL_PAST = "RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 MICROSECOND PRECEDING"

# Columnas de features que salen de build_features (orden estable para el modelo).
NUMERIC_FEATURES = [
    # transacción actual
    "amount", "log_amount", "is_round_100", "is_near_10k", "cross_border",
    "currency_mismatch", "hour", "dow", "is_weekend",
    # emisor: velocidad y montos
    "s_cnt_1d", "s_cnt_7d", "s_cnt_30d", "s_amt_1d", "s_amt_7d", "s_amt_30d",
    "s_amt_z_30d", "s_amt_ratio_mean_30d", "s_uniq_rcv_7d", "s_uniq_rcv_30d",
    "s_cash_cnt_30d", "s_xborder_cnt_30d", "s_prev_cnt_all", "s_days_since_first",
    "s_hours_since_prev",
    # emisor: dinero que le entró (pass-through / layering)
    "s_in_cnt_7d", "s_in_amt_7d", "s_out_in_ratio_7d",
    # par emisor-receptor
    "pair_prev_cnt", "pair_cnt_7d", "is_new_counterparty",
    # receptor: concentración (fan-in) y salida (mula)
    "r_cnt_7d", "r_cnt_30d", "r_amt_7d", "r_uniq_snd_7d", "r_uniq_snd_30d",
    "r_prev_cnt_all", "r_hours_since_prev", "r_out_cnt_7d", "r_out_amt_7d",
]
CATEGORICAL_FEATURES = [
    "payment_type", "payment_currency", "received_currency",
    "sender_bank_location", "receiver_bank_location",
]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def _family_case() -> str:
    whens = " ".join(f"WHEN '{t}' THEN '{f}'" for t, f in TYPOLOGY_TO_FAMILY.items())
    return f"CASE laundering_type {whens} ELSE NULL END"


def build_features(con: duckdb.DuckDBPyConnection, src: str = "transactions", dst: str = "features") -> None:
    p1, p7, p30 = (_PAST.format(n=n) for n in (1, 7, 30))
    con.execute(f"""
    CREATE OR REPLACE TABLE {dst} AS
    WITH t AS (SELECT * FROM {src}),

    snd AS (
        SELECT txn_id,
            count(*)                OVER s1  AS s_cnt_1d,
            count(*)                OVER s7  AS s_cnt_7d,
            count(*)                OVER s30 AS s_cnt_30d,
            coalesce(sum(amount)    OVER s1, 0)  AS s_amt_1d,
            coalesce(sum(amount)    OVER s7, 0)  AS s_amt_7d,
            coalesce(sum(amount)    OVER s30, 0) AS s_amt_30d,
            avg(amount)             OVER s30 AS _s_mean_30d,
            stddev_samp(amount)     OVER s30 AS _s_std_30d,
            count(DISTINCT receiver_account) OVER s7  AS s_uniq_rcv_7d,
            count(DISTINCT receiver_account) OVER s30 AS s_uniq_rcv_30d,
            coalesce(sum(CASE WHEN payment_type IN ('Cash Deposit', 'Cash Withdrawal') THEN 1 ELSE 0 END) OVER s30, 0) AS s_cash_cnt_30d,
            coalesce(sum(CASE WHEN sender_bank_location <> receiver_bank_location THEN 1 ELSE 0 END) OVER s30, 0) AS s_xborder_cnt_30d,
            count(*)                OVER sall AS s_prev_cnt_all,
            min(ts)                 OVER sall AS _s_first_ts,
            max(ts)                 OVER sall AS _s_prev_ts
        FROM t
        WINDOW s1   AS (PARTITION BY sender_account ORDER BY ts {p1}),
               s7   AS (PARTITION BY sender_account ORDER BY ts {p7}),
               s30  AS (PARTITION BY sender_account ORDER BY ts {p30}),
               sall AS (PARTITION BY sender_account ORDER BY ts {_ALL_PAST})
    ),

    rcv AS (
        SELECT txn_id,
            count(*)             OVER r7  AS r_cnt_7d,
            count(*)             OVER r30 AS r_cnt_30d,
            coalesce(sum(amount) OVER r7, 0) AS r_amt_7d,
            count(DISTINCT sender_account) OVER r7  AS r_uniq_snd_7d,
            count(DISTINCT sender_account) OVER r30 AS r_uniq_snd_30d,
            count(*)             OVER rall AS r_prev_cnt_all,
            max(ts)              OVER rall AS _r_prev_ts
        FROM t
        WINDOW r7   AS (PARTITION BY receiver_account ORDER BY ts {p7}),
               r30  AS (PARTITION BY receiver_account ORDER BY ts {p30}),
               rall AS (PARTITION BY receiver_account ORDER BY ts {_ALL_PAST})
    ),

    pair AS (
        SELECT txn_id,
            count(*) OVER pall AS pair_prev_cnt,
            count(*) OVER p7   AS pair_cnt_7d
        FROM t
        WINDOW pall AS (PARTITION BY sender_account, receiver_account ORDER BY ts {_ALL_PAST}),
               p7   AS (PARTITION BY sender_account, receiver_account ORDER BY ts {p7})
    ),

    -- Flujos acumulados por cuenta. RANGE ... CURRENT ROW incluye a los pares
    -- del mismo ts, así el ASOF con '<' devuelve todo lo estrictamente anterior.
    inflow AS (
        SELECT receiver_account AS acct, ts,
            count(*)    OVER (PARTITION BY receiver_account ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_cnt,
            sum(amount) OVER (PARTITION BY receiver_account ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_amt
        FROM t
    ),
    outflow AS (
        SELECT sender_account AS acct, ts,
            count(*)    OVER (PARTITION BY sender_account ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_cnt,
            sum(amount) OVER (PARTITION BY sender_account ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_amt
        FROM t
    ),
    -- Entradas del emisor en [ts-7d, ts): acumulado antes de ts menos acumulado antes de ts-7d.
    s_in AS (
        SELECT t.txn_id,
            coalesce(a.cum_cnt, 0) - coalesce(b.cum_cnt, 0) AS s_in_cnt_7d,
            coalesce(a.cum_amt, 0) - coalesce(b.cum_amt, 0) AS s_in_amt_7d
        FROM t
        ASOF LEFT JOIN inflow a ON a.acct = t.sender_account AND a.ts < t.ts
        ASOF LEFT JOIN inflow b ON b.acct = t.sender_account AND b.ts < t.ts - INTERVAL 7 DAY
    ),
    -- Salidas del receptor en [ts-7d, ts): ¿la cuenta que recibe reenvía dinero?
    r_out AS (
        SELECT t.txn_id,
            coalesce(a.cum_cnt, 0) - coalesce(b.cum_cnt, 0) AS r_out_cnt_7d,
            coalesce(a.cum_amt, 0) - coalesce(b.cum_amt, 0) AS r_out_amt_7d
        FROM t
        ASOF LEFT JOIN outflow a ON a.acct = t.receiver_account AND a.ts < t.ts
        ASOF LEFT JOIN outflow b ON b.acct = t.receiver_account AND b.ts < t.ts - INTERVAL 7 DAY
    )

    SELECT
        t.txn_id, t.ts, t.sender_account, t.receiver_account,
        t.is_laundering, t.laundering_type, {_family_case()} AS family,

        t.amount,
        ln(1 + t.amount)                                    AS log_amount,
        (t.amount % 100 = 0)::TINYINT                       AS is_round_100,
        (t.amount >= 9000 AND t.amount < 10000)::TINYINT    AS is_near_10k,
        (t.sender_bank_location <> t.receiver_bank_location)::TINYINT AS cross_border,
        (t.payment_currency <> t.received_currency)::TINYINT          AS currency_mismatch,
        hour(t.ts)                                          AS hour,
        dayofweek(t.ts)                                     AS dow,
        (dayofweek(t.ts) IN (0, 6))::TINYINT                AS is_weekend,

        snd.s_cnt_1d, snd.s_cnt_7d, snd.s_cnt_30d,
        snd.s_amt_1d, snd.s_amt_7d, snd.s_amt_30d,
        (t.amount - snd._s_mean_30d) / nullif(snd._s_std_30d, 0) AS s_amt_z_30d,
        t.amount / nullif(snd._s_mean_30d, 0)                    AS s_amt_ratio_mean_30d,
        snd.s_uniq_rcv_7d, snd.s_uniq_rcv_30d,
        snd.s_cash_cnt_30d, snd.s_xborder_cnt_30d,
        snd.s_prev_cnt_all,
        date_diff('second', snd._s_first_ts, t.ts) / 86400.0 AS s_days_since_first,
        date_diff('second', snd._s_prev_ts,  t.ts) / 3600.0  AS s_hours_since_prev,

        s_in.s_in_cnt_7d, s_in.s_in_amt_7d,
        snd.s_amt_7d / nullif(s_in.s_in_amt_7d, 0) AS s_out_in_ratio_7d,

        pair.pair_prev_cnt, pair.pair_cnt_7d,
        (pair.pair_prev_cnt = 0)::TINYINT AS is_new_counterparty,

        rcv.r_cnt_7d, rcv.r_cnt_30d, rcv.r_amt_7d,
        rcv.r_uniq_snd_7d, rcv.r_uniq_snd_30d, rcv.r_prev_cnt_all,
        date_diff('second', rcv._r_prev_ts, t.ts) / 3600.0 AS r_hours_since_prev,
        r_out.r_out_cnt_7d, r_out.r_out_amt_7d,

        t.payment_type, t.payment_currency, t.received_currency,
        t.sender_bank_location, t.receiver_bank_location
    FROM t
    JOIN snd   USING (txn_id)
    JOIN rcv   USING (txn_id)
    JOIN pair  USING (txn_id)
    JOIN s_in  USING (txn_id)
    JOIN r_out USING (txn_id)
    ORDER BY t.txn_id
    """)


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    t0 = time.time()
    build_features(con)
    n, cols = con.execute("SELECT count(*) FROM features").fetchone()[0], len(con.execute("DESCRIBE features").fetchall())
    print(f"features: {n:,} filas x {cols} columnas en {time.time() - t0:.0f}s")
    con.close()


if __name__ == "__main__":
    main()
