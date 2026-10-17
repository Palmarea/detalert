El modelo `binary_v1` es un LightGBM que predice **`is_laundering`** (1 = lavado, 0 = normal) **por transacción**.

- **Qué devuelve:** `p_laundering`, una probabilidad calibrada con Platt. Un valor de 0.02 significa más o menos un 2% de probabilidad real de lavado.
- **Cómo se convierte en banda:** con umbrales versionados se asigna `auto_close_eligible` / `review` / `high_priority`.
- **Familia:** el contrato de la API también tiene `family` (structuring, layering, concentration, cash, behavioural, generic). Pero ese clasificador multiclase, la Fase 4 del PLAN con `train_family.py`, **todavía no está entrenado**. Hoy esa familia solo sale del mock.
- **Resultado en OOT** (jun–ago 2023): Gini 99.94, PR-AUC 0.976, recall@1% 0.99.

## Las 18 columnas finales

Todas se calculan **solo con el pasado**: usan transacciones estrictamente anteriores a la que se evalúa, así que no hay leakage. El prefijo `s_` es el emisor (sender), `r_` el receptor y `pair_` la pareja emisor→receptor.

| # | Columna | Qué mide | Gini univ. |
|---|---|---|---|
| 1 | `is_new_counterparty` | 1 si es la primera vez que el emisor le envía a este receptor | 71.2 |
| 2 | `r_hours_since_prev` | Horas desde la transacción anterior que recibió el receptor | 64.5 |
| 3 | `s_hours_since_prev` | Horas desde la transacción anterior que envió el emisor | 57.1 |
| 4 | `s_amt_7d` | Monto total enviado por el emisor en los últimos 7 días | 51.5 |
| 5 | `s_cnt_7d` | Nº de transacciones enviadas por el emisor en 7 días | 50.4 |
| 6 | `s_cnt_30d` | Nº de transacciones enviadas por el emisor en 30 días | 48.9 |
| 7 | `pair_cnt_7d` | Nº de envíos emisor→receptor en los últimos 7 días | 45.9 |
| 8 | `s_amt_ratio_mean_30d` | Monto actual ÷ monto promedio del emisor en 30 días | 44.2 |
| 9 | `r_uniq_snd_7d` | Nº de emisores distintos que le enviaron al receptor en 7 días (fan-in) | 41.5 |
| 10 | `payment_type` *(categórica)* | Tipo de pago (Cash Deposit, Cross-border, ACH, etc.) | 40.9 |
| 11 | `s_amt_z_30d` | Z-score del monto actual frente al historial de 30 días del emisor | 36.2 |
| 12 | `r_uniq_snd_30d` | Nº de emisores distintos hacia el receptor en 30 días | 30.1 |
| 13 | `amount` | Monto de la transacción | 28.7 |
| 14 | `currency_mismatch` | 1 si la moneda de pago es distinta de la moneda recibida | 25.3 |
| 15 | `s_out_in_ratio_7d` | Lo que el emisor envió ÷ lo que recibió en 7 días (pass-through / layering) | 22.9 |
| 16 | `r_out_cnt_7d` | Nº de envíos que hizo el receptor en 7 días (si reenvía, parece cuenta mula) | 17.6 |
| 17 | `s_in_cnt_7d` | Nº de transacciones que recibió el emisor en 7 días | 8.0 |
| 18 | `s_cash_cnt_30d` | Nº de operaciones en efectivo del emisor en 30 días | 6.8 |

Se partió de 44 candidatas y quedaron estas 18 tras cuatro filtros: Gini/fill-rate univariado, PSI ≤ 0.25, correlación |ρ| ≤ 0.9 y Boruta. El detalle de las excluidas y el motivo de cada una está en [feature_selection.md](reports/feature_selection.md).
