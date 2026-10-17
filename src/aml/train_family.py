"""Clasificador de familia de tipología: la llave de enrutamiento del funnel.

Multiclase LightGBM entrenado SOLO con positivos de train (Laundering_type solo
como target, nunca como feature). En inferencia se aplica a lo alertado; si la
confianza es < GENERIC_BELOW el caso va al agente general (`generic`).

Uso:
    python -m aml.train_family
"""

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from aml.config import FAMILIES, MODELS_DIR, REPORTS_DIR
from aml.data import load
from aml.features import CATEGORICAL_FEATURES

VERSION = "v1"
CLASSES = list(FAMILIES)
GENERIC_BELOW = 0.5
PARAMS = {"objective": "multiclass", "num_class": len(CLASSES), "learning_rate": 0.05, "num_leaves": 31,
          "min_child_samples": 20, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
          "verbosity": -1, "seed": 5}


def features() -> list[str]:
    return json.loads((MODELS_DIR / "binary_v1_meta.json").read_text())["features"]


def main() -> None:
    feats = features()
    pos = {s: load([s], cols=feats, where="is_laundering = 1") for s in ("train", "test", "oot")}
    y = {s: df.family.map(CLASSES.index).to_numpy() for s, df in pos.items()}
    cats = [c for c in feats if c in CATEGORICAL_FEATURES]

    dtr = lgb.Dataset(pos["train"][feats], y["train"], categorical_feature=cats)
    dte = lgb.Dataset(pos["test"][feats], y["test"], categorical_feature=cats, reference=dtr)
    model = lgb.train(PARAMS, dtr, num_boost_round=2000, valid_sets=[dte],
                      callbacks=[lgb.early_stopping(50, verbose=False)])

    out, md = {}, ["# Clasificador de familia\n",
                   f"Entrenado con {len(y['train']):,} positivos de train; early stopping en test "
                   f"({model.best_iteration} árboles). Si la confianza es < {GENERIC_BELOW}, la familia es `generic`.\n"]
    for s in ("test", "oot"):
        proba = model.predict(pos[s][feats], num_iteration=model.best_iteration)
        pred = proba.argmax(1)
        conf = proba.max(1)
        out[s] = {"f1_macro": round(f1_score(y[s], pred, average="macro"), 4),
                  "accuracy": round(float((pred == y[s]).mean()), 4),
                  "pct_generic": round(float((conf < GENERIC_BELOW).mean()), 4),
                  "accuracy_no_generic": round(float((pred == y[s])[conf >= GENERIC_BELOW].mean()), 4)}
        cm = pd.DataFrame(confusion_matrix(y[s], pred, labels=range(len(CLASSES))), index=CLASSES, columns=CLASSES)
        md += [f"\n## {s.upper()}\n", f"F1 macro **{out[s]['f1_macro']}** · accuracy {out[s]['accuracy']} · "
               f"{out[s]['pct_generic']:.1%} va a `generic` · accuracy sin generic {out[s]['accuracy_no_generic']}\n",
               "Matriz de confusión (filas = real, columnas = predicha):\n", cm.to_markdown(),
               "\n```\n" + classification_report(y[s], pred, labels=range(len(CLASSES)), target_names=CLASSES) + "```"]
    model.save_model(str(MODELS_DIR / f"family_{VERSION}.txt"), num_iteration=model.best_iteration)
    (MODELS_DIR / f"family_{VERSION}_meta.json").write_text(json.dumps(
        {"version": VERSION, "classes": CLASSES, "features": feats, "generic_below": GENERIC_BELOW, "metrics": out}, indent=2))
    (REPORTS_DIR / "family_model.md").write_text("\n".join(md) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
