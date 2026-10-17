"""Tests de no-fuga temporal (point-in-time) de las features.

1. Truncamiento: las features de una transacción anterior a T no pueden cambiar
   si se borran todos los datos posteriores a T.
2. Recálculo manual: pandas recalcula features de transacciones de muestra
   directamente desde las transacciones crudas estrictamente anteriores.

Corre sobre oct-nov 2022 para que tarde segundos:
    .venv/bin/pytest -q tests/
"""

import duckdb
import numpy as np
import pandas as pd
import pytest

from aml.config import DB_PATH
from aml.features import CATEGORICAL_FEATURES, FEATURES, build_features

WINDOW_END = "2022-12-01"
CUTOFF = "2022-11-15"


@pytest.fixture(scope="module")
def con():
    if not DB_PATH.exists():
        pytest.skip("Falta data/aml.duckdb: corre primero python -m aml.ingest")
    c = duckdb.connect()
    c.execute(f"ATTACH '{DB_PATH}' AS src (READ_ONLY)")
    c.execute(f"CREATE TABLE tx_full AS SELECT * FROM src.transactions WHERE ts < '{WINDOW_END}'")
    c.execute(f"CREATE TABLE tx_cut  AS SELECT * FROM tx_full WHERE ts < '{CUTOFF}'")
    build_features(c, "tx_full", "f_full")
    build_features(c, "tx_cut", "f_cut")
    yield c
    c.close()


def test_truncation_invariance(con):
    cols = ", ".join(f"a.{c} AS a_{c}, b.{c} AS b_{c}" for c in FEATURES)
    df = con.execute(f"SELECT {cols} FROM f_cut b JOIN f_full a USING (txn_id)").df()
    (n_cut,) = con.execute("SELECT count(*) FROM f_cut").fetchone()
    assert len(df) == n_cut > 0

    bad = {}
    for c in FEATURES:
        a, b = df[f"a_{c}"], df[f"b_{c}"]
        if c in CATEGORICAL_FEATURES:
            diff = (a.fillna("<NA>") != b.fillna("<NA>")).sum()
        else:
            diff = (~np.isclose(a.astype(float), b.astype(float), rtol=1e-9, atol=1e-6, equal_nan=True)).sum()
        if diff:
            bad[c] = int(diff)
    assert not bad, f"Features que cambian al ver datos futuros: {bad}"


def _sample(con, n=8):
    # Mezcla de transacciones con historial rico, de lavado y de cuentas nuevas.
    return con.execute("""
        (SELECT * FROM f_full WHERE s_cnt_7d BETWEEN 3 AND 40 AND r_cnt_7d > 1 ORDER BY hash(txn_id) LIMIT 4)
        UNION ALL (SELECT * FROM f_full WHERE is_laundering = 1 AND s_in_cnt_7d > 0 ORDER BY hash(txn_id) LIMIT 3)
        UNION ALL (SELECT * FROM f_full WHERE s_prev_cnt_all = 0 ORDER BY hash(txn_id) LIMIT 1)
    """).df()


def test_manual_recompute(con):
    sample = _sample(con)
    assert len(sample) >= 6
    for _, row in sample.iterrows():
        ts = row.ts
        past = con.execute(
            "SELECT * FROM tx_full WHERE ts < ? AND (sender_account IN (?, ?) OR receiver_account IN (?, ?))",
            [ts, row.sender_account, row.receiver_account, row.sender_account, row.receiver_account],
        ).df()
        d7, d30 = ts - pd.Timedelta(days=7), ts - pd.Timedelta(days=30)
        s = past[past.sender_account == row.sender_account]
        r = past[past.receiver_account == row.receiver_account]
        s_in = past[past.receiver_account == row.sender_account]
        r_out = past[past.sender_account == row.receiver_account]

        expected = {
            "s_cnt_7d": (s.ts >= d7).sum(),
            "s_cnt_30d": (s.ts >= d30).sum(),
            "s_amt_30d": s.loc[s.ts >= d30, "amount"].sum(),
            "s_uniq_rcv_7d": s.loc[s.ts >= d7, "receiver_account"].nunique(),
            "s_prev_cnt_all": len(s),
            "pair_prev_cnt": (s.receiver_account == row.receiver_account).sum(),
            "r_cnt_7d": (r.ts >= d7).sum(),
            "r_uniq_snd_7d": r.loc[r.ts >= d7, "sender_account"].nunique(),
            "s_in_cnt_7d": (s_in.ts >= d7).sum(),
            "s_in_amt_7d": s_in.loc[s_in.ts >= d7, "amount"].sum(),
            "r_out_amt_7d": r_out.loc[r_out.ts >= d7, "amount"].sum(),
            "s_hours_since_prev": (ts - s.ts.max()).total_seconds() / 3600 if len(s) else np.nan,
        }
        for k, v in expected.items():
            got = row[k]
            assert np.isclose(float(got), float(v), rtol=1e-9, atol=1e-6, equal_nan=True), (
                f"txn {row.txn_id}: {k} = {got}, esperado {v}"
            )
