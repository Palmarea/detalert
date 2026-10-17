"""Selección de variables según la metodología de modelamiento del banco.

1. Univariado (train): Gini con binning + fill rate, umbrales de la metodología.
2. Estabilidad del Gini por mes dentro de train (informativo).
3. PSI train vs OOT: > 0.25 excluye, 0.10-0.25 se marca.
4. Correlación (Spearman) |rho| > 0.9: se queda la de mayor Gini.
5. Boruta con LightGBM sobre submuestra (todos los positivos + negativos muestreados).

Final = pasa 1, PSI <= 0.25, no eliminada por 4 y Boruta != rechazada.

Uso:
    python -m aml.select
"""

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import binom

from aml.config import MODELS_DIR, REPORTS_DIR
from aml.data import load
from aml.features import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from aml.metrics import binned_gini, psi

# (gini mínimo, fill rate mínimo), en %. Basta cumplir una condición.
UNIVARIATE_RULES = [(20, 10), (15, 20), (10, 40), (5, 80)]
PSI_DROP, PSI_WARN = 0.25, 0.10
CORR_MAX = 0.9
BORUTA_ITERS = 20
BORUTA_NEG = 200_000
SEED = 7


def passes_univariate(g: float, fr: float) -> bool:
    return any(g > gmin and fr > frmin for gmin, frmin in UNIVARIATE_RULES)


def boruta(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    pos = df[df.is_laundering == 1]
    neg = df[df.is_laundering == 0].sample(min(BORUTA_NEG, (df.is_laundering == 0).sum()), random_state=SEED)
    sub = pd.concat([pos, neg])
    X, y = sub[feats].reset_index(drop=True), sub.is_laundering.to_numpy()
    hits = pd.Series(0, index=feats)
    imp_sum = pd.Series(0.0, index=feats)
    for it in range(BORUTA_ITERS):
        shadow = X.apply(lambda c: c.iloc[rng.permutation(len(c))].reset_index(drop=True))
        shadow.columns = [f"shadow_{c}" for c in feats]
        XX = pd.concat([X, shadow], axis=1)
        m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.1, num_leaves=31, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, random_state=SEED + it, verbose=-1)
        m.fit(XX, y)
        imp = pd.Series(m.booster_.feature_importance("gain"), index=XX.columns)
        max_shadow = imp[shadow.columns].max()
        hits += (imp[feats] > max_shadow).astype(int)
        imp_sum += imp[feats]
        print(f"  boruta iter {it + 1}/{BORUTA_ITERS}: max shadow gain {max_shadow:,.0f}")
    # Prueba binomial con p=0.5 (Boruta clásico), alfa 0.05.
    p_conf = binom.sf(hits - 1, BORUTA_ITERS, 0.5)
    p_rej = binom.cdf(hits, BORUTA_ITERS, 0.5)
    status = np.where(p_conf < 0.05, "confirmada", np.where(p_rej < 0.05, "rechazada", "tentativa"))
    return pd.DataFrame({"boruta_hits": hits, "boruta": status, "boruta_gain_medio": imp_sum / BORUTA_ITERS})


def main() -> None:
    print("Cargando train y oot...")
    train = load(["train"])
    oot = load(["oot"], cols=FEATURES)
    y = train.is_laundering
    month = train.ts.dt.to_period("M").astype(str)

    rows = []
    for c in FEATURES:
        g, mapping = binned_gini(train[c], y)
        fr = train[c].notna().mean() * 100
        by_month = []
        for _, idx in train.groupby(month).groups.items():
            gm, _ = binned_gini(train.loc[idx, c], y.loc[idx], bins=mapping)
            by_month.append(gm * 100)
        rows.append({
            "feature": c,
            "tipo": "cat" if c in CATEGORICAL_FEATURES else "num",
            "gini": round(g * 100, 1),
            "fill_rate": round(fr, 1),
            "gini_mes_min": round(min(by_month), 1),
            "gini_mes_max": round(max(by_month), 1),
            "psi": round(psi(train[c], oot[c]), 4),
        })
    t = pd.DataFrame(rows).set_index("feature")
    t["univariado_ok"] = [passes_univariate(g, fr) for g, fr in zip(t.gini, t.fill_rate)]
    t["gini_inestable"] = (t.gini_mes_max - t.gini_mes_min) > 15

    # Correlación entre numéricas que pasaron el univariado.
    cand = [c for c in NUMERIC_FEATURES if t.loc[c, "univariado_ok"]]
    corr = train[cand].sample(200_000, random_state=SEED).corr(method="spearman").abs()
    t["eliminada_por_corr"] = ""
    order = t.loc[cand].sort_values("gini", ascending=False).index
    kept: list[str] = []
    for c in order:
        twin = next((k for k in kept if corr.loc[c, k] > CORR_MAX), None)
        if twin:
            t.loc[c, "eliminada_por_corr"] = f"{twin} (rho={corr.loc[c, twin]:.2f})"
        else:
            kept.append(c)

    print("Boruta...")
    b = boruta(train, FEATURES)
    t = t.join(b)

    def motivo(r) -> str:
        if not r.univariado_ok:
            return "univariado (Gini/FR bajo umbral)"
        if r.psi > PSI_DROP:
            return f"inestable (PSI {r.psi:.2f})"
        if r.eliminada_por_corr:
            return f"correlación con {r.eliminada_por_corr}"
        if r.boruta == "rechazada":
            return "Boruta rechazada"
        return ""

    t["motivo_exclusion"] = t.apply(motivo, axis=1)
    t["final"] = t.motivo_exclusion == ""
    t = t.sort_values(["final", "gini"], ascending=[False, False])

    selected = t.index[t.final].tolist()
    MODELS_DIR.mkdir(exist_ok=True)
    (MODELS_DIR / "selected_features.json").write_text(json.dumps({
        "numeric": [c for c in selected if c in NUMERIC_FEATURES],
        "categorical": [c for c in selected if c in CATEGORICAL_FEATURES],
    }, indent=2))

    cols = ["tipo", "gini", "fill_rate", "gini_mes_min", "gini_mes_max", "psi",
            "boruta", "boruta_hits", "motivo_exclusion"]
    md = [
        "# Selección de variables\n",
        f"Criterios (metodología): univariado {UNIVARIATE_RULES} (Gini %, FR %) · PSI > {PSI_DROP} excluye "
        f"· |rho| > {CORR_MAX} · Boruta {BORUTA_ITERS} iteraciones con LightGBM sobre todos los positivos "
        f"+ {BORUTA_NEG:,} negativos de train.\n",
        "Gini = Gini con binning (20 cuantiles; las categóricas por categoría), calculado sobre train. "
        "PSI calculado entre train y OOT.\n",
        f"**Finalistas: {len(selected)} de {len(FEATURES)}.**\n",
        "## Finalistas\n", t.loc[t.final, cols[:-1]].to_markdown(),
        "\n## Excluidas\n", t.loc[~t.final, cols].to_markdown(),
        "\n## Alertas\n",
        "- Gini inestable entre meses (rango > 15 pts): " + (", ".join(t.index[t.gini_inestable]) or "ninguna"),
        "- PSI en zona de revisión (0,10-0,25): " + (", ".join(t.index[(t.psi > PSI_WARN) & (t.psi <= PSI_DROP)]) or "ninguna"),
    ]
    (REPORTS_DIR / "feature_selection.md").write_text("\n".join(md) + "\n")
    print(t[cols].to_string())
    print(f"\nFinalistas ({len(selected)}): {selected}")


if __name__ == "__main__":
    main()
