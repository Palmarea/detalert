"""Métricas en el idioma de la metodología del banco (Gini, KS) más las propias de AML."""

import numpy as np
import pandas as pd
from scipy.stats import beta
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def gini(y, s) -> float:
    return 2 * roc_auc_score(y, s) - 1


def ks(y, s) -> float:
    fpr, tpr, _ = roc_curve(y, s)
    return float(np.max(tpr - fpr))


def recall_at_alert_rate(y, s, rate: float) -> float:
    """Recall si se alerta el top `rate` de transacciones por score."""
    y, s = np.asarray(y), np.asarray(s)
    k = max(1, int(round(len(s) * rate)))
    top = np.argpartition(-s, k - 1)[:k]
    return float(y[top].sum() / max(1, y.sum()))


def precision_at_k(y, s, k: int) -> float:
    y, s = np.asarray(y), np.asarray(s)
    top = np.argpartition(-s, k - 1)[:k]
    return float(y[top].mean())


def summary(y, s) -> dict:
    y, s = np.asarray(y), np.asarray(s)
    return {
        "n": int(len(y)),
        "positivos": int(y.sum()),
        "gini": round(gini(y, s) * 100, 2),
        "ks": round(ks(y, s) * 100, 2),
        "pr_auc": round(float(average_precision_score(y, s)), 4),
        "recall@1%": round(recall_at_alert_rate(y, s, 0.01), 4),
        "recall@5%": round(recall_at_alert_rate(y, s, 0.05), 4),
        "precision@1000": round(precision_at_k(y, s, 1000), 4),
    }


def bootstrap_gini(y, s, n_boot: int = 200, seed: int = 0) -> tuple[float, float]:
    """IC 95% del Gini con bootstrap estratificado (remuestrea positivos y negativos por separado)."""
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y), np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    out = []
    for _ in range(n_boot):
        p = rng.choice(pos, len(pos))
        n = rng.choice(neg, len(neg))
        yy = np.r_[np.ones(len(p)), np.zeros(len(n))]
        out.append(gini(yy, np.r_[p, n]))
    lo, hi = np.percentile(out, [2.5, 97.5])
    return round(lo * 100, 2), round(hi * 100, 2)


def calibration_bands(y, p, n_bins: int = 10) -> pd.DataFrame:
    """Calibración por bandas de score (equivalente AML de las bandas de Vasicek).

    Agrupa por cuantiles de la probabilidad predicha; para cada banda compara la
    tasa observada con el IC 95% binomial (Clopper-Pearson) alrededor de la PD media
    predicha. `ok` = la tasa observada cae dentro de la banda.
    """
    df = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    df["banda"] = pd.qcut(df.p.rank(method="first"), n_bins, labels=False) + 1
    g = df.groupby("banda").agg(n=("y", "size"), eventos=("y", "sum"), p_media=("p", "mean"),
                                p_min=("p", "min"), p_max=("p", "max"))
    g["tasa_obs"] = g.eventos / g.n
    # Banda: eventos esperados bajo p_media con IC binomial al 95%.
    exp_lo = np.nan_to_num(beta.ppf(0.025, g.n * g.p_media, g.n * (1 - g.p_media) + 1), nan=0.0)
    exp_hi = np.nan_to_num(beta.ppf(0.975, g.n * g.p_media + 1, g.n * (1 - g.p_media)), nan=1.0)
    g["banda_lo"], g["banda_hi"] = exp_lo, exp_hi
    g["ok"] = (g.tasa_obs >= g.banda_lo) & (g.tasa_obs <= g.banda_hi)
    return g.reset_index()


def binned_gini(x: pd.Series, y: pd.Series, n_bins: int = 20, bins=None):
    """Gini univariado con binning (captura relaciones no monótonas, como en scorecards).

    Devuelve (gini, mapping) donde mapping permite aplicar los mismos bins a otra muestra.
    """
    enc, mapping = _bin_encode(x, y, n_bins, bins)
    if enc.nunique() < 2:
        return 0.0, mapping
    return gini(y, enc), mapping


def _bin_codes(x: pd.Series, edges) -> pd.Series:
    if edges is None:  # categórica
        return x.astype("string").fillna("<NA>")
    codes = pd.Series(np.searchsorted(edges, x.to_numpy(dtype=float), side="right"), index=x.index).astype("string")
    return codes.mask(x.isna(), "<NA>")


def _bin_encode(x, y, n_bins, mapping=None):
    if mapping is None:
        if isinstance(x.dtype, pd.CategoricalDtype) or x.dtype == object or pd.api.types.is_string_dtype(x):
            edges = None
        else:
            qs = np.unique(np.nanquantile(x.to_numpy(dtype=float), np.linspace(0, 1, n_bins + 1)[1:-1]))
            edges = qs
        codes = _bin_codes(x, edges)
        rates = y.groupby(codes).mean()
        mapping = {"edges": edges, "rates": rates.to_dict(), "prior": float(y.mean())}
    codes = _bin_codes(x, mapping["edges"])
    enc = codes.map(mapping["rates"]).astype(float).fillna(mapping["prior"])
    return enc, mapping


def psi(expected: pd.Series, actual: pd.Series, n_bins: int = 10) -> float:
    """Population Stability Index con bins definidos sobre `expected` (train)."""
    if isinstance(expected.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(expected):
        e = expected.astype("string").fillna("<NA>").value_counts(normalize=True)
        a = actual.astype("string").fillna("<NA>").value_counts(normalize=True)
    else:
        edges = np.unique(np.nanquantile(expected.to_numpy(dtype=float), np.linspace(0, 1, n_bins + 1)[1:-1]))
        e = _bin_codes(expected, edges).value_counts(normalize=True)
        a = _bin_codes(actual, edges).value_counts(normalize=True)
    idx = e.index.union(a.index)
    e, a = e.reindex(idx, fill_value=0) + 1e-6, a.reindex(idx, fill_value=0) + 1e-6
    return float(((a - e) * np.log(a / e)).sum())
