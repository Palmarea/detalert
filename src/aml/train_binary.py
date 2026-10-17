"""Modelo binario: LightGBM inicial, Optuna, modelo final, calibración y evaluación.

Muestra de entrenamiento: todos los positivos de train + NEG_RATE de los negativos
(determinista por txn_id). El submuestreo cambia la escala de probabilidad; la
calibración isotónica sobre test la corrige.

Uso:
    python -m aml.train_binary tune      # Optuna -> models/binary_params.json
    python -m aml.train_binary fit       # entrena inicial + final, evalúa, escribe reportes
"""

import json
import pickle
import sys
import time

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from aml.config import MODELS_DIR, REPORTS_DIR, TYPOLOGY_TO_FAMILY
from aml.data import load
from aml.features import CATEGORICAL_FEATURES, FEATURES
from aml.metrics import bootstrap_gini, calibration_bands, gini, summary

NEG_RATE = 0.10  # hash(txn_id) % 10 == 0
N_TRIALS = 30
SEED = 11
VERSION = "v1"
TRAIN_WHERE = "is_laundering = 1 OR hash(txn_id) % 10 = 0"

BASE_PARAMS = {
    "objective": "binary",
    "metric": "average_precision",
    "verbosity": -1,
    "seed": SEED,
    "num_threads": 0,
    "feature_pre_filter": False,
}


def selected_features() -> list[str]:
    s = json.loads((MODELS_DIR / "selected_features.json").read_text())
    return s["numeric"] + s["categorical"]


def dataset(df: pd.DataFrame, feats: list[str]) -> lgb.Dataset:
    cats = [c for c in feats if c in CATEGORICAL_FEATURES]
    return lgb.Dataset(df[feats], df.is_laundering, categorical_feature=cats, free_raw_data=False)


def tune() -> None:
    feats = selected_features()
    tr = load(["train"], cols=feats, where=TRAIN_WHERE)
    print(f"Muestra de tuning: {len(tr):,} filas, {tr.is_laundering.sum():,} positivos, {len(feats)} features")
    ds = dataset(tr, feats)

    def objective(trial: optuna.Trial) -> float:
        params = BASE_PARAMS | {
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 255, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 500, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": 1,
            "lambda_l1": trial.suggest_float("lambda_l1", 1e-3, 10, log=True),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10, log=True),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 1, 20, log=True),
        }
        cv = lgb.cv(params, ds, num_boost_round=3000, nfold=3, stratified=True, seed=SEED,
                    callbacks=[lgb.early_stopping(100, verbose=False)])
        key = "valid average_precision-mean"
        trial.set_user_attr("best_iter", len(cv[key]))
        return cv[key][-1]

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEED))
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False,
                   callbacks=[lambda s, t: print(f"trial {t.number}: PR-AUC CV {t.value:.4f} "
                                                 f"(mejor {s.best_value:.4f}) iters {t.user_attrs['best_iter']}", flush=True)])
    best = {"params": BASE_PARAMS | study.best_params | {"bagging_freq": 1},
            "num_boost_round": study.best_trial.user_attrs["best_iter"],
            "cv_pr_auc": study.best_value, "n_trials": N_TRIALS}
    (MODELS_DIR / "binary_params.json").write_text(json.dumps(best, indent=2))
    study.trials_dataframe().to_csv(REPORTS_DIR / "optuna_trials.csv", index=False)
    print(json.dumps(best, indent=2))


def evaluate(name: str, model: lgb.Booster, feats: list[str], samples: dict[str, pd.DataFrame]) -> dict:
    out = {}
    for s, df in samples.items():
        out[s] = summary(df.is_laundering, model.predict(df[feats]))
    out["gap_gini_train_oot"] = round(out["train"]["gini"] - out["oot"]["gini"], 2)
    print(name, json.dumps(out, indent=1))
    return out


def fit() -> None:
    t0 = time.time()
    feats_sel = selected_features()
    best = json.loads((MODELS_DIR / "binary_params.json").read_text())

    print("Cargando muestras...")
    tr = load(["train"], cols=FEATURES, where=TRAIN_WHERE)
    full = {
        "train": load(["train"], cols=FEATURES),
        "test": load(["test"], cols=FEATURES),
        "oot": load(["oot"], cols=FEATURES),
    }

    # 1. Modelo inicial: todas las features, parámetros por defecto (metodología: "modelo inicial").
    init = lgb.train(BASE_PARAMS | {"learning_rate": 0.05}, dataset(tr, FEATURES), num_boost_round=500)
    m_init = evaluate("inicial", init, FEATURES, full)

    # 2. Modelo final: finalistas + hiperparámetros de Optuna.
    model = lgb.train(best["params"], dataset(tr, feats_sel), num_boost_round=best["num_boost_round"])
    m_final = evaluate("final", model, feats_sel, full)

    # 3. Calibración isotónica sobre test (probabilidad real en la población completa).
    raw = {s: model.predict(df[feats_sel]) for s, df in full.items()}
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(raw["test"], full["test"].is_laundering)
    oot = full["oot"].assign(score_raw=raw["oot"], p=iso.predict(raw["oot"]))
    bands = calibration_bands(oot.is_laundering, oot.p)

    # 4. Detalle sobre OOT: bootstrap, por mes, por segmento, por tipología.
    ci = bootstrap_gini(oot.is_laundering, oot.score_raw)
    alert_thr = np.quantile(raw["test"], 0.99)  # umbral que alerta el 1% en test
    oot["alerta"] = oot.score_raw >= alert_thr

    def seg_table(col):
        rows = []
        for k, g in oot.groupby(col, observed=True):
            if g.is_laundering.sum() >= 10 and g.is_laundering.nunique() == 2:
                rows.append({col: k, "n": len(g), "positivos": int(g.is_laundering.sum()),
                             "gini": round(gini(g.is_laundering, g.score_raw) * 100, 1),
                             "recall@umbral_1%": round(g.alerta[g.is_laundering == 1].mean(), 3)})
        return pd.DataFrame(rows)

    oot["mes"] = oot.ts.dt.to_period("M").astype(str)
    oot["cross_border"] = oot.cross_border.map({0: "doméstica", 1: "cross-border"})
    pos = oot[oot.is_laundering == 1]
    by_typ = pos.groupby("laundering_type").agg(n=("alerta", "size"), recall=("alerta", "mean"),
                                                p_media=("p", "mean")).round(3)
    by_typ["familia"] = by_typ.index.map(TYPOLOGY_TO_FAMILY)
    by_typ = by_typ.sort_values("recall")

    # 5. Sensibilidad (estrés ±1σ, ±2σ en top-5 por gain) e importancia SHAP.
    imp = pd.Series(model.feature_importance("gain"), index=feats_sel).sort_values(ascending=False)
    smp = oot.sample(200_000, random_state=SEED)
    base_p = iso.predict(model.predict(smp[feats_sel]))
    sens = []
    for f in [f for f in imp.index if f not in CATEGORICAL_FEATURES][:5]:
        sd = full["train"][f].std()
        row = {"feature": f}
        for k in (-2, -1, 1, 2):
            x = smp[feats_sel].copy()
            x[f] = x[f] + k * sd
            p = iso.predict(model.predict(x))
            row[f"{k:+d}σ Δp media (pb)"] = round((p.mean() - base_p.mean()) * 1e4, 2)
            row[f"{k:+d}σ Δalertas %"] = round(((model.predict(x) >= alert_thr).mean()
                                               / max(1e-9, (model.predict(smp[feats_sel]) >= alert_thr).mean()) - 1) * 100, 1)
        sens.append(row)
    sens = pd.DataFrame(sens)
    contrib = model.predict(smp[feats_sel].iloc[:50_000], pred_contrib=True)[:, :-1]
    shap_imp = pd.Series(np.abs(contrib).mean(0), index=feats_sel).sort_values(ascending=False)

    # 6. Guardar artefactos.
    model.save_model(str(MODELS_DIR / f"binary_{VERSION}.txt"))
    with open(MODELS_DIR / f"calibrator_{VERSION}.pkl", "wb") as fh:
        pickle.dump(iso, fh)
    meta = {"version": VERSION, "features": feats_sel, "alert_threshold_raw_top1pct_test": float(alert_thr),
            "neg_rate": NEG_RATE, "params": best["params"], "num_boost_round": best["num_boost_round"]}
    (MODELS_DIR / f"binary_{VERSION}_meta.json").write_text(json.dumps(meta, indent=2))

    baseline = json.loads((REPORTS_DIR / "metrics_baseline.json").read_text())
    metrics = {"inicial": m_init, "final": m_final, "oot_gini_ic95": ci,
               "calibracion_bandas_ok": f"{int(bands.ok.sum())}/{len(bands)}"}
    (REPORTS_DIR / "metrics_binary.json").write_text(json.dumps(metrics, indent=2))

    def row(name, m, n_feats):
        return {"modelo": name, "features": n_feats, "Gini test": m["test"]["gini"], "Gini OOT": m["oot"]["gini"],
                "KS OOT": m["oot"]["ks"], "PR-AUC OOT": m["oot"]["pr_auc"],
                "recall@1% OOT": m["oot"]["recall@1%"], "recall@5% OOT": m["oot"]["recall@5%"],
                "precision@1000 OOT": m["oot"]["precision@1000"]}
    comp = pd.DataFrame([row("Baseline reglas (vigente)", baseline, 6),
                         row("LightGBM inicial", m_init, len(FEATURES)),
                         row("LightGBM final", m_final, len(feats_sel))])

    md = [
        "# Modelo binario — comparación y evaluación\n",
        "## Comparación con el modelo vigente\n", comp.to_markdown(index=False),
        f"\n- Gini OOT del modelo final: **{m_final['oot']['gini']}** (IC 95% bootstrap: {ci[0]} – {ci[1]}).",
        f"- Gap de Gini train − OOT: **{m_final['gap_gini_train_oot']} pts** (criterio: ≤ 15).",
        f"- Bandas de calibración OK en OOT: **{int(bands.ok.sum())}/{len(bands)}**.",
        f"- Umbral de alerta: top 1% de score en test (raw ≥ {alert_thr:.4f}).\n",
        "## Métricas por muestra (modelo final)\n",
        pd.DataFrame({k: v for k, v in m_final.items() if isinstance(v, dict)}).T.to_markdown(),
        "\n## Por mes (OOT)\n", seg_table("mes").to_markdown(index=False),
        "\n## Por tipo de pago (OOT)\n", seg_table("payment_type").to_markdown(index=False),
        "\n## Doméstica vs cross-border (OOT)\n", seg_table("cross_border").to_markdown(index=False),
        "\n## Recall por tipología con el umbral del 1% (OOT)\n", by_typ.to_markdown(),
        "\n## Calibración por bandas (OOT, IC binomial 95%)\n",
        bands.assign(p_media=bands.p_media.map("{:.5f}".format), tasa_obs=bands.tasa_obs.map("{:.5f}".format),
                     banda_lo=bands.banda_lo.map("{:.5f}".format), banda_hi=bands.banda_hi.map("{:.5f}".format))
             [["banda", "n", "eventos", "p_media", "tasa_obs", "banda_lo", "banda_hi", "ok"]].to_markdown(index=False),
        "\n## Sensibilidad (estrés en top-5 features, OOT, 200k filas)\n", sens.to_markdown(index=False),
        "\n## Importancia SHAP (media |contribución|, OOT)\n", shap_imp.round(4).to_frame("shap").to_markdown(),
    ]
    (REPORTS_DIR / "model_comparison.md").write_text("\n".join(md) + "\n")
    print(comp.to_string(index=False))
    print(f"Listo en {time.time() - t0:.0f}s")


if __name__ == "__main__":
    {"tune": tune, "fit": fit}[sys.argv[1]]()
