"""Configuración central del módulo ML: rutas, columnas y familias de tipología."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "aml.duckdb"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"

# Columnas originales de SAML-D -> nombre normalizado en DuckDB.
RAW_COLUMNS = {
    "Time": "time",
    "Date": "date",
    "Sender_account": "sender_account",
    "Receiver_account": "receiver_account",
    "Amount": "amount",
    "Payment_currency": "payment_currency",
    "Received_currency": "received_currency",
    "Sender_bank_location": "sender_bank_location",
    "Receiver_bank_location": "receiver_bank_location",
    "Payment_type": "payment_type",
    "Is_laundering": "is_laundering",
    "Laundering_type": "laundering_type",
}

# Columnas que NUNCA pueden entrar como feature (etiquetas o identificadores).
FORBIDDEN_FEATURES = {
    "txn_id",
    "sender_account",
    "receiver_account",
    "is_laundering",
    "laundering_type",
    "family",
}

# Familias de tipología sospechosa -> llave de enrutamiento del funnel.
# Validado contra el EDA: cubre las 17 tipologías sospechosas de SAML-D.
# Positivos por familia: structuring 3747, layering 2765, cash 1584,
# concentration 984, behavioural 793.
FAMILIES: dict[str, list[str]] = {
    "structuring": ["Structuring", "Smurfing", "Deposit-Send"],
    "layering": [
        "Layered_Fan_Out",
        "Layered_Fan_In",
        "Stacked Bipartite",
        "Cycle",
        "Scatter-Gather",
        "Gather-Scatter",
    ],
    "concentration": ["Fan_In", "Fan_Out", "Bipartite"],
    "cash": ["Cash_Withdrawal", "Single_large"],
    "behavioural": ["Behavioural_Change_1", "Behavioural_Change_2", "Over-Invoicing"],
}

TYPOLOGY_TO_FAMILY = {t: fam for fam, types in FAMILIES.items() for t in types}

# Muestras según la metodología del banco (datos: 2022-10-07 -> 2023-08-23).
# Desarrollo: ts < OOT_START, dividido en train/test por TEST_FRACTION (estratificado).
# OOT: ts >= OOT_START (jun-ago, 3 meses, ~2.8k positivos).
OOT_START = "2023-06-01"
TEST_FRACTION = 0.30
SPLIT_SEED = 42
