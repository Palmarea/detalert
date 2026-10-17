"""Puntos de operación por capacidad de analistas + funnel + métricas para la API.

Umbrales elegidos en TEST (casos), reportados en OOT. Modos:
- normal: mayor umbral de auto-cierre con <= MAX_MISS_NORMAL de casos de lavado
  auto-cerrados; prioridad alta = menor umbral con precisión >= HP_PRECISION.
- reduced_capacity: la cola (review + high_priority) baja a REDUCED_CAPACITY de
  la normal subiendo el auto-cierre; se reporta cuánto lavado cuesta.
- no_analyst: mismo auto-cierre seguro que normal; todo lo demás pasa a
  high_priority con retención preventiva (nadie revisa, nada se cierra de más).

Uso:
    python -m aml.thresholds
"""

import json

import duckdb
import numpy as np
import pandas as pd

from aml.config import DB_PATH, MODELS_DIR, REPORTS_DIR

VERSION = "thresholds_v1"
MAX_MISS_NORMAL = 0.01
HP_PRECISION = 0.99
REDUCED_CAPACITY = 0.5
GRID = np.unique(np.round(np.logspace(-4, np.log10(0.5), 400), 6))
HP_GRID = np.round(np.linspace(0.5, 0.995, 100), 3)


def evaluate(d: pd.DataFrame, a: float, h: float, days: float) -> dict:
    ac = d.case_score < a
    hp = d.case_score >= h
    pos = d.is_laundering == 1
    missed = (ac & pos).sum()
    return {
        "auto_close_rate": round(float(ac.mean()), 4),
        "expected_leakage": round(float(missed / max(1, ac.sum())), 5),
        "missed_laundering_pct": round(float(missed / max(1, pos.sum())), 4),
        "missed_cases": int(missed),
        "queue_cases_per_day": round(float((~ac).sum() / days), 1),
        "high_priority_per_day": round(float(hp.sum() / days), 1),
        "high_priority_precision": round(float(pos[hp].mean()), 4) if hp.any() else None,
    }


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    cases = con.execute("SELECT * FROM cases").df()
    test, oot = cases[cases["sample"] == "test"], cases[cases["sample"] == "oot"]
    oot_days = (oot.window_end.max() - oot.window_start.min()).total_seconds() / 86400
    test_days = (test.window_end.max() - test.window_start.min()).total_seconds() / 86400

    pos_t = test.is_laundering == 1
    miss = np.array([((test.case_score < a) & pos_t).sum() / pos_t.sum() for a in GRID])
    a_normal = float(GRID[miss <= MAX_MISS_NORMAL].max())
    prec = np.array([pos_t[test.case_score >= h].mean() if (test.case_score >= h).any() else 0 for h in HP_GRID])
    h_normal = float(HP_GRID[prec >= HP_PRECISION].min())

    queue_normal = (test.case_score >= a_normal).mean()
    queue = np.array([(test.case_score >= a).mean() for a in GRID])
    a_reduced = float(GRID[queue <= REDUCED_CAPACITY * queue_normal].min())

    modes = [
        ("normal", 100, a_normal, h_normal, False),
        ("reduced_capacity", int(REDUCED_CAPACITY * 100), a_reduced, h_normal, False),
        ("no_analyst", 0, a_normal, a_normal, True),
    ]
    ops, report = [], []
    for mode, cap, a, h, hold in modes:
        ev_oot = evaluate(oot, a, h, oot_days)
        ev_test = evaluate(test, a, h, test_days)
        ops.append({"mode": mode, "analyst_capacity_pct": cap, "auto_close_threshold": a,
                    "high_priority_threshold": h, "auto_close_rate": ev_oot["auto_close_rate"],
                    "expected_leakage": ev_oot["expected_leakage"],
                    "missed_laundering_pct": ev_oot["missed_laundering_pct"],
                    "queue_cases_per_day": 0.0 if mode == "no_analyst" else ev_oot["queue_cases_per_day"],
                    "preventive_hold": hold})
        report.append({"modo": mode, "auto_cierre <": a, "alta prioridad >=": h,
                       **{f"OOT {k}": v for k, v in ev_oot.items()},
                       "TEST missed%": ev_test["missed_laundering_pct"]})

    alert = json.loads((MODELS_DIR / "alert_threshold.json").read_text())
    thresholds = {"threshold_version": VERSION, "alert_threshold": alert["alert_threshold"], "operating_points": ops}
    (MODELS_DIR / f"{VERSION}.json").write_text(json.dumps(thresholds, indent=2))

    # Funnel en OOT, en unidades de transacciones de lavado (modo normal).
    tot = con.execute("SELECT count(*), sum(is_laundering) FROM features WHERE sample = 'oot'").fetchone()
    al = con.execute("SELECT count(*), sum(is_laundering) FROM case_txns WHERE sample = 'oot'").fetchone()
    esc = con.execute("""SELECT count(DISTINCT c.case_id), sum(t.is_laundering) FROM cases c
                         JOIN case_txns t USING (case_id) WHERE c.sample = 'oot' AND c.case_score >= ?""",
                      [a_normal]).fetchone()
    hp = con.execute("""SELECT count(DISTINCT c.case_id), sum(t.is_laundering) FROM cases c
                        JOIN case_txns t USING (case_id) WHERE c.sample = 'oot' AND c.case_score >= ?""",
                     [h_normal]).fetchone()
    funnel = [
        {"stage": "transacciones", "n_in": tot[0], "n_out": tot[0], "positives_out": int(tot[1]), "leakage": 0.0},
        {"stage": "alertas", "n_in": tot[0], "n_out": al[0], "positives_out": int(al[1]),
         "leakage": round(1 - al[1] / tot[1], 4)},
        {"stage": "casos", "n_in": al[0], "n_out": len(oot), "positives_out": int(al[1]), "leakage": 0.0},
        {"stage": "escalados (review + alta prioridad)", "n_in": len(oot), "n_out": esc[0],
         "positives_out": int(esc[1]), "leakage": round(1 - esc[1] / al[1], 4)},
        {"stage": "alta prioridad", "n_in": esc[0], "n_out": hp[0], "positives_out": int(hp[1]),
         "leakage": round(1 - hp[1] / esc[1], 4)},
    ]

    # Recall extremo a extremo por tipología: la transacción de lavado termina en un caso escalado.
    typ = con.execute("""
        SELECT f.laundering_type,
               avg(CASE WHEN c.case_score >= ? THEN 1.0 ELSE 0.0 END) AS recall
        FROM features f
        LEFT JOIN case_txns t USING (txn_id)
        LEFT JOIN cases c USING (case_id)
        WHERE f.sample = 'oot' AND f.is_laundering = 1
        GROUP BY 1 ORDER BY 2""", [a_normal]).df()
    mb = json.loads((REPORTS_DIR / "metrics_binary.json").read_text())["final"]["oot"]
    base = json.loads((REPORTS_DIR / "metrics_baseline.json").read_text())["oot"]
    meta = json.loads((MODELS_DIR / "binary_v1_meta.json").read_text())
    metrics = {"model_version": f"binary_{meta['version']}", "threshold_version": VERSION, "sample": "oot",
               "gini": mb["gini"], "ks": mb["ks"], "pr_auc": mb["pr_auc"], "recall_at_1pct": mb["recall@1%"],
               "baseline_gini": base["gini"],
               "recall_by_typology": {r.laundering_type: round(r.recall, 4) for r in typ.itertuples()},
               "funnel": funnel}
    (MODELS_DIR / "api_metrics_v1.json").write_text(json.dumps(metrics, indent=2))

    # Leakage por familia real en modo normal (OOT).
    fam = oot[oot.is_laundering == 1].assign(auto=lambda d: d.case_score < a_normal).groupby("true_family") \
        .agg(casos=("auto", "size"), auto_cerrados=("auto", "sum"))
    rep = pd.DataFrame(report)
    md = ["# Puntos de operación\n",
          f"Umbrales elegidos en **test** (casos), reportados en **OOT** ({oot_days:.0f} días, {len(oot):,} casos, "
          f"{int(oot.is_laundering.sum()):,} con lavado). Umbral de alerta: p ≥ {alert['alert_threshold']:.6f} "
          f"(recall {alert['target_recall']:.0%} de transacciones en test).\n",
          rep.T.to_markdown(), "\n## Funnel (OOT, modo normal; positivos = transacciones de lavado)\n",
          pd.DataFrame(funnel).to_markdown(index=False),
          "\n## Casos de lavado auto-cerrados por familia real (OOT, modo normal)\n", fam.to_markdown(),
          "\n## Recall extremo a extremo por tipología (OOT, modo normal)\n", typ.to_markdown(index=False)]
    (REPORTS_DIR / "operating_points.md").write_text("\n".join(md) + "\n")
    print(rep.T.to_string())
    print(pd.DataFrame(funnel).to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
