"""Evaluador de modelos LightGBM en Python puro (sin lightgbm/numpy/scipy).

Permite puntuar en vivo dentro de Vercel con un bundle liviano. El modelo se
serializa con `compact_model` (desde el Booster, en el batch local) y se guarda
en Postgres; aquí solo se recorren los árboles.

Contribuciones: método de Saabas (diferencia de valores internos a lo largo del
camino de decisión). Es una aproximación de SHAP, suficiente para reason codes.
"""

import math

# Índices dentro de cada nodo compacto.
_FEAT, _THR, _CAT, _DEFL, _MISS, _LEFT, _RIGHT, _VAL = range(8)
_MISS_NONE, _MISS_ZERO, _MISS_NAN = 0, 1, 2
_MISSING_CODES = {"None": _MISS_NONE, "Zero": _MISS_ZERO, "NaN": _MISS_NAN}


def compact_model(booster) -> dict:
    """Booster de LightGBM -> dict JSON compacto. Se usa solo en el batch local."""
    d = booster.dump_model()
    trees = []
    for info in d["tree_info"]:
        nodes: list[list] = []

        def walk(n) -> int:
            idx = len(nodes)
            if "leaf_value" in n:  # hoja: valor en _VAL, hijos = -1
                nodes.append([-1, 0.0, None, False, 0, -1, -1, n["leaf_value"]])
                return idx
            is_cat = n["decision_type"] == "=="
            thr = [int(x) for x in str(n["threshold"]).split("||")] if is_cat else float(n["threshold"])
            nodes.append([n["split_feature"], None if is_cat else thr, thr if is_cat else None,
                          bool(n["default_left"]), _MISSING_CODES[n["missing_type"]], -1, -1,
                          n["internal_value"]])
            nodes[idx][_LEFT] = walk(n["left_child"])
            nodes[idx][_RIGHT] = walk(n["right_child"])
            return idx

        walk(info["tree_structure"])
        trees.append(nodes)
    return {
        "objective": d["objective"].split()[0],
        "num_class": d["num_class"],
        "feature_names": d["feature_names"],
        "pandas_categorical": booster.pandas_categorical or [],
        "categorical_features": [d["feature_names"][i] for i in
                                 (booster.params.get("categorical_feature") or [])
                                 if isinstance(i, int)],
        "trees": trees,
    }


class TreeModel:
    def __init__(self, m: dict):
        self.names: list[str] = m["feature_names"]
        self.num_class: int = m["num_class"]
        self.trees: list[list] = m["trees"]
        # Mapeo categoría -> código, en el orden de pandas_categorical (una lista por feature categórica).
        cat_feats = [n for n in self.names if n in set(m.get("categorical_features") or [])] or \
            [n for n in self.names if n in ("payment_type",)]
        self.cat_maps = {f: {v: i for i, v in enumerate(vals)}
                         for f, vals in zip(cat_feats, m.get("pandas_categorical") or [])}

    def _vector(self, x: dict) -> list[float]:
        out = []
        for n in self.names:
            v = x.get(n)
            if n in self.cat_maps:
                v = self.cat_maps[n].get(v, -1) if v is not None else -1
                out.append(float(v))
            else:
                out.append(float("nan") if v is None else float(v))
        return out

    @staticmethod
    def _go_left(node: list, v: float) -> bool:
        if node[_CAT] is not None:  # split categórico: izquierda si la categoría está en el set
            return (not math.isnan(v)) and v >= 0 and int(v) in node[_CAT]
        miss = node[_MISS]
        if math.isnan(v):
            if miss == _MISS_NAN:
                return node[_DEFL]
            v = 0.0  # missing_type None/Zero: NaN se trata como 0
        if miss == _MISS_ZERO and v == 0.0:
            return node[_DEFL]
        return v <= node[_THR]

    def _tree(self, nodes: list, xv: list[float], contrib: list[float] | None) -> float:
        i = 0
        while nodes[i][_LEFT] != -1:
            node = nodes[i]
            nxt = node[_LEFT] if self._go_left(node, xv[node[_FEAT]]) else node[_RIGHT]
            if contrib is not None:
                contrib[node[_FEAT]] += nodes[nxt][_VAL] - node[_VAL]
            i = nxt
        return nodes[i][_VAL]

    def raw(self, x: dict, with_contrib: bool = False):
        """Margen (log-odds) por clase; opcionalmente contribuciones por feature (clase 0 / binario)."""
        xv = self._vector(x)
        k = self.num_class
        margins = [0.0] * k
        contrib = [0.0] * len(self.names) if with_contrib else None
        for t, nodes in enumerate(self.trees):
            c = t % k
            margins[c] += self._tree(nodes, xv, contrib if c == 0 else None)
        return (margins, contrib) if with_contrib else margins

    def predict_binary(self, x: dict, with_contrib: bool = False):
        if with_contrib:
            (m,), contrib = self.raw(x, True)
            return _sigmoid(m), m, dict(zip(self.names, contrib))
        (m,) = self.raw(x)
        return _sigmoid(m), m

    def predict_multiclass(self, x: dict) -> list[float]:
        ms = self.raw(x)
        mx = max(ms)
        ex = [math.exp(v - mx) for v in ms]
        s = sum(ex)
        return [e / s for e in ex]


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def platt(margin: float, coef: float, intercept: float) -> float:
    """Calibración de Platt sobre el logit del score crudo (= margen del modelo binario)."""
    return _sigmoid(coef * margin + intercept)
