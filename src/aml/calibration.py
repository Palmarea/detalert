"""Calibración de Platt sobre el logit del score crudo.

Se prefiere sobre la isotónica porque nunca devuelve p = 0 (crítico para el
auto-cierre) y en OOT queda calibrada en las bandas bajas, que son las que deciden
qué se cierra solo. En las bandas medias sobreestima levemente: es la dirección
conservadora (escala de más, no de menos).
"""

import numpy as np
from sklearn.linear_model import LogisticRegression


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


class PlattCalibrator:
    def fit(self, raw, y) -> "PlattCalibrator":
        self.lr = LogisticRegression(C=1e6).fit(_logit(raw)[:, None], np.asarray(y))
        return self

    def predict(self, raw):
        return self.lr.predict_proba(_logit(raw)[:, None])[:, 1]
