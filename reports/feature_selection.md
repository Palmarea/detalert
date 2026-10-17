# Selección de variables

Criterios (metodología): univariado [(20, 10), (15, 20), (10, 40), (5, 80)] (Gini %, FR %) · PSI > 0.25 excluye · |rho| > 0.9 · Boruta 20 iteraciones con LightGBM sobre todos los positivos + 200,000 negativos de train.

Gini = Gini con binning (20 cuantiles; las categóricas por categoría), calculado sobre train. PSI calculado entre train y OOT.

**Finalistas: 18 de 44.**

## Finalistas

| feature              | tipo   |   gini |   fill_rate |   gini_mes_min |   gini_mes_max |    psi | boruta     |   boruta_hits |
|:---------------------|:-------|-------:|------------:|---------------:|---------------:|-------:|:-----------|--------------:|
| is_new_counterparty  | num    |   71.2 |       100   |           62.4 |           76.4 | 0      | confirmada |            20 |
| r_hours_since_prev   | num    |   64.5 |        94.7 |           62.2 |           67.9 | 0.0179 | confirmada |            20 |
| s_hours_since_prev   | num    |   57.1 |        97.2 |           55.9 |           59.6 | 0.004  | confirmada |            20 |
| s_amt_7d             | num    |   51.5 |       100   |           48.1 |           57.2 | 0.0016 | tentativa  |             7 |
| s_cnt_7d             | num    |   50.4 |       100   |           48.6 |           52.4 | 0.0017 | tentativa  |             6 |
| s_cnt_30d            | num    |   48.9 |       100   |           45.7 |           54   | 0.0016 | confirmada |            20 |
| pair_cnt_7d          | num    |   45.9 |       100   |           42.4 |           49.2 | 0.0006 | confirmada |            19 |
| s_amt_ratio_mean_30d | num    |   44.2 |        95.4 |           41.7 |           47.7 | 0.0022 | confirmada |            18 |
| r_uniq_snd_7d        | num    |   41.5 |       100   |           38.8 |           44.2 | 0.0004 | tentativa  |            14 |
| payment_type         | cat    |   40.9 |       100   |           37.2 |           46.4 | 0      | confirmada |            20 |
| s_amt_z_30d          | num    |   36.2 |        91.8 |           33.7 |           41.3 | 0.0025 | tentativa  |            13 |
| r_uniq_snd_30d       | num    |   30.1 |       100   |           25.4 |           34.1 | 0.0012 | confirmada |            20 |
| amount               | num    |   28.7 |       100   |           24   |           39.5 | 0.0001 | confirmada |            20 |
| currency_mismatch    | num    |   25.3 |       100   |           22   |           31.8 | 0      | confirmada |            20 |
| s_out_in_ratio_7d    | num    |   22.9 |        30.4 |           15.5 |           27.7 | 0.0094 | tentativa  |            12 |
| r_out_cnt_7d         | num    |   17.6 |       100   |           15.7 |           19.6 | 0.0002 | confirmada |            20 |
| s_in_cnt_7d          | num    |    8   |       100   |            0.3 |           11.8 | 0.0078 | confirmada |            20 |
| s_cash_cnt_30d       | num    |    6.8 |       100   |            4.6 |           10.5 | 0      | confirmada |            19 |

## Excluidas

| feature                | tipo   |   gini |   fill_rate |   gini_mes_min |   gini_mes_max |    psi | boruta     |   boruta_hits | motivo_exclusion                              |
|:-----------------------|:-------|-------:|------------:|---------------:|---------------:|-------:|:-----------|--------------:|:----------------------------------------------|
| pair_prev_cnt          | num    |   74.6 |       100   |           63.5 |           82.6 | 0.2828 | confirmada |            20 | inestable (PSI 0.28)                          |
| s_amt_1d               | num    |   52.3 |       100   |           48.6 |           54.9 | 0.0007 | tentativa  |            12 | correlación con s_hours_since_prev (rho=0.91) |
| s_cnt_1d               | num    |   50.6 |       100   |           47.9 |           53   | 0.0008 | rechazada  |             2 | correlación con s_hours_since_prev (rho=0.91) |
| s_amt_30d              | num    |   46.4 |       100   |           44.2 |           48.8 | 0.0021 | confirmada |            17 | correlación con s_cnt_30d (rho=0.91)          |
| r_cnt_7d               | num    |   43.9 |       100   |           39.9 |           49   | 0.0003 | confirmada |            20 | correlación con r_hours_since_prev (rho=0.92) |
| s_uniq_rcv_7d          | num    |   42.7 |       100   |           39.3 |           45.6 | 0.0017 | rechazada  |             0 | correlación con s_cnt_30d (rho=0.91)          |
| r_amt_7d               | num    |   41.5 |       100   |           36.6 |           48.3 | 0.0002 | tentativa  |            11 | correlación con r_hours_since_prev (rho=0.92) |
| s_uniq_rcv_30d         | num    |   41.2 |       100   |           36.1 |           44.9 | 0.0022 | confirmada |            20 | correlación con s_cnt_30d (rho=0.93)          |
| s_prev_cnt_all         | num    |   31.8 |       100   |           28   |           38.2 | 0.8375 | confirmada |            20 | inestable (PSI 0.84)                          |
| r_cnt_30d              | num    |   30.5 |       100   |           23.7 |           34.4 | 0.0002 | rechazada  |             3 | Boruta rechazada                              |
| r_prev_cnt_all         | num    |   29.8 |       100   |           19.4 |           39.6 | 0.2944 | confirmada |            20 | inestable (PSI 0.29)                          |
| s_days_since_first     | num    |   28.8 |        97.2 |           20.2 |           43.5 | 3.1692 | confirmada |            20 | inestable (PSI 3.17)                          |
| log_amount             | num    |   28.7 |       100   |           24   |           39.5 | 0.0001 | tentativa  |             9 | correlación con amount (rho=1.00)             |
| received_currency      | cat    |   22.5 |       100   |           19.4 |           25.5 | 0.0005 | rechazada  |             0 | Boruta rechazada                              |
| cross_border           | num    |   20.9 |       100   |           18.2 |           27.3 | 0      | confirmada |            18 | correlación con currency_mismatch (rho=0.92)  |
| s_xborder_cnt_30d      | num    |   20.6 |       100   |           18.3 |           23.4 | 0.0006 | rechazada  |             0 | Boruta rechazada                              |
| receiver_bank_location | cat    |   19.1 |       100   |           17.2 |           21.9 | 0.0008 | rechazada  |             0 | Boruta rechazada                              |
| r_out_amt_7d           | num    |   11.2 |       100   |            4.5 |           14.6 | 0.0003 | confirmada |            20 | correlación con r_out_cnt_7d (rho=0.99)       |
| s_in_amt_7d            | num    |    7.2 |       100   |            2.2 |           11.9 | 0.0115 | tentativa  |            14 | correlación con s_in_cnt_7d (rho=0.98)        |
| payment_currency       | cat    |    6.5 |       100   |            4.5 |           11.5 | 0.0003 | rechazada  |             0 | Boruta rechazada                              |
| hour                   | num    |    4.2 |       100   |            0.5 |            9.2 | 0.0001 | confirmada |            20 | univariado (Gini/FR bajo umbral)              |
| sender_bank_location   | cat    |    3.6 |       100   |            2.1 |            7.9 | 0.0006 | rechazada  |             0 | univariado (Gini/FR bajo umbral)              |
| dow                    | num    |    2.1 |       100   |           -1.3 |            4.7 | 0.0008 | rechazada  |             0 | univariado (Gini/FR bajo umbral)              |
| is_weekend             | num    |    1.4 |       100   |            0.1 |            3   | 0.0002 | rechazada  |             0 | univariado (Gini/FR bajo umbral)              |
| is_round_100           | num    |    0   |       100   |            0   |            0   | 0      | rechazada  |             0 | univariado (Gini/FR bajo umbral)              |
| is_near_10k            | num    |    0   |       100   |            0   |            0   | 0      | rechazada  |             0 | univariado (Gini/FR bajo umbral)              |

## Alertas

- Gini inestable entre meses (rango > 15 pts): amount, pair_prev_cnt, r_prev_cnt_all, s_days_since_first, log_amount
- PSI en zona de revisión (0,10-0,25): ninguna
