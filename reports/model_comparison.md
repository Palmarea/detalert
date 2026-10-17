# Modelo binario — comparación y evaluación

## Comparación con el modelo vigente

| modelo                    |   features |   Gini test |   Gini OOT |   KS OOT |   PR-AUC OOT |   recall@1% OOT |   recall@5% OOT |   precision@1000 OOT |
|:--------------------------|-----------:|------------:|-----------:|---------:|-------------:|----------------:|----------------:|---------------------:|
| Baseline reglas (vigente) |          6 |       46.73 |      44.7  |    40.97 |       0.004  |          0.0938 |          0.2806 |                0.005 |
| LightGBM inicial          |         44 |       99.94 |      99.98 |    99.08 |       0.9866 |          0.9958 |          1      |                1     |
| LightGBM final            |         18 |       99.91 |      99.94 |    98.21 |       0.9756 |          0.9898 |          0.9993 |                1     |

- Gini OOT del modelo final: **99.94** (IC 95% bootstrap: 99.92 – 99.96).
- Gap de Gini train − OOT: **0.05 pts** (criterio: ≤ 15).
- Bandas de calibración OK en OOT: **3/7**.
- Umbral de alerta: top 1% de score en test (raw ≥ 0.0180).

## Métricas por muestra (modelo final)

|       |           n |   positivos |   gini |    ks |   pr_auc |   recall@1% |   recall@5% |   precision@1000 |
|:------|------------:|------------:|-------:|------:|---------:|------------:|------------:|-----------------:|
| train | 4.3279e+06  |        4373 |  99.99 | 99.53 |   0.9823 |      0.9995 |      1      |            1     |
| test  | 1.85481e+06 |        1875 |  99.91 | 97.74 |   0.95   |      0.9851 |      0.9995 |            0.999 |
| oot   | 2.45606e+06 |        2837 |  99.94 | 98.21 |   0.9756 |      0.9898 |      0.9993 |            1     |

## Por mes (OOT)

| mes     |      n |   positivos |   gini |   recall@umbral_1% |
|:--------|-------:|------------:|-------:|-------------------:|
| 2023-06 | 897243 |        1024 |   99.9 |              0.984 |
| 2023-07 | 902239 |         983 |  100   |              0.995 |
| 2023-08 | 656582 |         830 |   99.9 |              0.986 |

## Por tipo de pago (OOT)

| payment_type    |      n |   positivos |   gini |   recall@umbral_1% |
|:----------------|-------:|------------:|-------:|-------------------:|
| ACH             | 519028 |         314 |  100   |              0.994 |
| Cash Deposit    |  58542 |         391 |   98.5 |              0.964 |
| Cash Withdrawal |  76865 |         400 |   98.8 |              0.975 |
| Cheque          | 520560 |         288 |  100   |              0.993 |
| Credit card     | 519840 |         317 |  100   |              1     |
| Cross-border    | 240669 |         801 |  100   |              0.998 |
| Debit card      | 520560 |         326 |  100   |              0.991 |

## Doméstica vs cross-border (OOT)

| cross_border   |       n |   positivos |   gini |   recall@umbral_1% |
|:---------------|--------:|------------:|-------:|-------------------:|
| cross-border   |  240801 |         933 |  100   |              0.997 |
| doméstica      | 2215263 |        1904 |   99.9 |              0.984 |

## Recall por tipología con el umbral del 1% (OOT)

| laundering_type      |   n |   recall |   p_media | familia       |
|:---------------------|----:|---------:|----------:|:--------------|
| Smurfing             | 263 |    0.947 |     0.733 | structuring   |
| Cash_Withdrawal      | 400 |    0.975 |     0.83  | cash          |
| Scatter-Gather       |  87 |    0.977 |     0.96  | layering      |
| Fan_Out              | 123 |    0.984 |     0.965 | concentration |
| Deposit-Send         | 256 |    0.992 |     0.943 | structuring   |
| Layered_Fan_Out      | 130 |    0.992 |     0.932 | layering      |
| Layered_Fan_In       | 170 |    0.994 |     0.968 | layering      |
| Stacked Bipartite    | 191 |    0.995 |     0.975 | layering      |
| Behavioural_Change_1 | 126 |    1     |     0.907 | behavioural   |
| Single_large         |  56 |    1     |     0.944 | cash          |
| Over-Invoicing       |  14 |    1     |     0.924 | behavioural   |
| Gather-Scatter       | 123 |    1     |     0.944 | layering      |
| Cycle                |  81 |    1     |     0.932 | layering      |
| Bipartite            |  55 |    1     |     0.978 | concentration |
| Behavioural_Change_2 | 124 |    1     |     0.96  | behavioural   |
| Fan_In               |  84 |    1     |     0.975 | concentration |
| Structuring          | 554 |    1     |     0.994 | structuring   |

## Calibración por bandas (OOT, IC binomial 95%)

| banda           |       n |   eventos |   p_media |   tasa_obs |   banda_lo |   banda_hi | ok    |
|:----------------|--------:|----------:|----------:|-----------:|-----------:|-----------:|:------|
| [0, 0.0001)     | 2387270 |         7 |   0       |    0       |    0       |    0       | True  |
| [0.0001, 0.001) |   49971 |        26 |   0.00032 |    0.00052 |    0.00018 |    0.00052 | True  |
| [0.001, 0.01)   |   13203 |        29 |   0.00299 |    0.0022  |    0.00213 |    0.00407 | True  |
| [0.01, 0.1)     |    2533 |        50 |   0.02967 |    0.01974 |    0.02341 |    0.03704 | False |
| [0.1, 0.5)      |     387 |        61 |   0.21751 |    0.15762 |    0.17741 |    0.26199 | False |
| [0.5, 0.9)      |     224 |       189 |   0.76854 |    0.84375 |    0.70771 |    0.82212 | False |
| [0.9, 1)        |    2476 |      2475 |   0.98969 |    0.9996  |    0.98488 |    0.99329 | False |

## Sensibilidad (estrés en top-5 features, OOT, 200k filas)

| feature            |   -2σ Δp media (pb) |   -2σ Δalertas % |   -1σ Δp media (pb) |   -1σ Δalertas % |   +1σ Δp media (pb) |   +1σ Δalertas % |   +2σ Δp media (pb) |   +2σ Δalertas % |
|:-------------------|--------------------:|-----------------:|--------------------:|-----------------:|--------------------:|-----------------:|--------------------:|-----------------:|
| r_hours_since_prev |               -1.45 |            128   |               -1.24 |            109.4 |                8.66 |            150.4 |                9.87 |            175.2 |
| r_out_cnt_7d       |                1.48 |             60.3 |                1.45 |             56.9 |              157.36 |            695.6 |              128.06 |            684.9 |
| s_hours_since_prev |               -4.06 |            -29.3 |               -3.79 |            -27.2 |                1.11 |             70.7 |                1.15 |             90.6 |
| s_cnt_30d          |                3.4  |            220.4 |                3.25 |            218.3 |                3.11 |            291.8 |                1.98 |            233.3 |
| r_uniq_snd_30d     |                0    |             32.5 |                0.03 |             31.2 |               84.68 |            669.8 |               72.08 |            641.9 |

## Importancia SHAP (media |contribución|, OOT)

|                      |   shap |
|:---------------------|-------:|
| is_new_counterparty  | 0.8552 |
| s_hours_since_prev   | 0.6134 |
| payment_type         | 0.5458 |
| r_hours_since_prev   | 0.4518 |
| amount               | 0.3482 |
| pair_cnt_7d          | 0.2426 |
| s_amt_7d             | 0.1992 |
| s_cnt_30d            | 0.1912 |
| r_out_cnt_7d         | 0.173  |
| r_uniq_snd_7d        | 0.141  |
| s_cash_cnt_30d       | 0.1064 |
| s_amt_z_30d          | 0.1038 |
| s_amt_ratio_mean_30d | 0.1012 |
| r_uniq_snd_30d       | 0.0865 |
| s_out_in_ratio_7d    | 0.0766 |
| s_cnt_7d             | 0.0554 |
| currency_mismatch    | 0.0533 |
| s_in_cnt_7d          | 0.0339 |
