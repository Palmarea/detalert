"""Scoring batch (como el proceso nocturno de un banco): test y OOT -> tabla `scores`.

Cada fila: score crudo, probabilidad calibrada, familia predicha y su confianza.
Train no se puntúa: sus scores serían in-sample.

Uso:
    python -m aml.score_batch
"""

import json
import pickle
import time

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

from aml.config import DB_PATH, MODELS_DIR
from aml.data import load

SAMPLES = ["test", "oot"]


class Scorer:
    """Carga los artefactos versionados y puntúa un DataFrame de features."""

    def __init__(self, version: str = "v1"):
        self.meta = json.loads((MODELS_DIR / f"binary_{version}_meta.json").read_text())
        self.fmeta = json.loads((MODELS_DIR / f"family_{version}_meta.json").read_text())
        self.binary = lgb.Booster(model_file=str(MODELS_DIR / f"binary_{version}.txt"))
        self.family = lgb.Booster(model_file=str(MODELS_DIR / f"family_{version}.txt"))
        with open(MODELS_DIR / f"calibrator_{version}.pkl", "rb") as fh:
            self.cal = pickle.load(fh)
        self.features = self.meta["features"]
        self.model_version = f"binary_{version}"

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.features]
        raw = self.binary.predict(X)
        fam = self.family.predict(X)
        conf = fam.max(1)
        family = np.array(self.fmeta["classes"])[fam.argmax(1)]
        family = np.where(conf < self.fmeta["generic_below"], "generic", family)
        return pd.DataFrame({"txn_id": df.txn_id.to_numpy(), "score_raw": raw, "p": self.cal.predict(raw),
                             "family_pred": family, "family_conf": conf})


def main() -> None:
    t0 = time.time()
    scorer = Scorer()
    parts = []
    for s in SAMPLES:
        df = load([s], cols=scorer.features)
        sc = scorer.score(df)
        sc["sample"] = s
        parts.append(sc)
        print(f"{s}: {len(sc):,} puntuadas")
    scores = pd.concat(parts, ignore_index=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE OR REPLACE TABLE scores AS SELECT * FROM scores")
    print(con.execute("""SELECT s.sample, count(*) n, round(avg(p)*100, 4) AS p_media_pct,
                                round(100*avg(f.is_laundering), 4) AS tasa_real_pct
                         FROM scores s JOIN features f USING (txn_id) GROUP BY 1""").df().to_string(index=False))
    con.close()
    print(f"Listo en {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
