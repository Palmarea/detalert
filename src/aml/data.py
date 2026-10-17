"""Carga de muestras desde la tabla `features` a pandas, con categóricas consistentes."""

import duckdb
import pandas as pd

from aml.config import DB_PATH
from aml.features import CATEGORICAL_FEATURES, FEATURES

META = ["txn_id", "ts", "sample", "is_laundering", "laundering_type", "family", "sender_account"]


def categories(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Categorías fijas (todas las vistas en la tabla) para que train/test/oot compartan códigos."""
    return {
        c: [r[0] for r in con.execute(f"SELECT DISTINCT {c} FROM features WHERE {c} IS NOT NULL ORDER BY 1").fetchall()]
        for c in CATEGORICAL_FEATURES
    }


def load(samples: list[str], cols: list[str] | None = None, where: str = "", con=None) -> pd.DataFrame:
    own = con is None
    con = con or duckdb.connect(str(DB_PATH), read_only=True)
    cols = cols or FEATURES
    in_list = ", ".join(f"'{s}'" for s in samples)
    extra = f"AND ({where})" if where else ""
    df = con.execute(
        f"SELECT {', '.join(META + [c for c in cols if c not in META])} FROM features "
        f"WHERE sample IN ({in_list}) {extra}"
    ).df()
    for c, cats in categories(con).items():
        if c in df:
            df[c] = pd.Categorical(df[c].astype(object), categories=cats)
    if own:
        con.close()
    return df
