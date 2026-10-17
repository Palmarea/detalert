"""Reason codes del batch: contribuciones SHAP de LightGBM (pred_contrib) -> texto legible.

Las plantillas viven en aml/api/reasons.py, compartidas con el scoring en vivo de la API.
"""

import numpy as np
import pandas as pd

from aml.api.reasons import TOP_K, top_reasons


def _json_value(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 6)
    return str(v)


def reason_codes(model, X: pd.DataFrame, top_k: int = TOP_K) -> list[list[dict]]:
    contrib = model.predict(X, pred_contrib=True)[:, :-1]  # última columna = bias
    feats = list(X.columns)
    return [top_reasons(dict(zip(feats, contrib[i].tolist())),
                        {f: _json_value(X.iat[i, j]) for j, f in enumerate(feats)}, top_k)
            for i in range(len(X))]


def snapshot(X: pd.DataFrame) -> list[dict]:
    return [{c: _json_value(v) for c, v in zip(X.columns, row)} for row in X.itertuples(index=False)]
