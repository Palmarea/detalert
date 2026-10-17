# Puntos de operación

Umbrales elegidos en **test** (casos), reportados en **OOT** (83 días, 25,601 casos, 1,680 con lavado). Umbral de alerta: p ≥ 0.000463 (recall 99% de transacciones en test).

|                             | 0        | 1                | 2          |
|:----------------------------|:---------|:-----------------|:-----------|
| modo                        | normal   | reduced_capacity | no_analyst |
| auto_cierre <               | 0.002355 | 0.006996         | 0.002355   |
| alta prioridad >=           | 0.775    | 0.775            | 0.002355   |
| OOT auto_close_rate         | 0.6116   | 0.7948           | 0.6116     |
| OOT expected_leakage        | 0.00019  | 0.00034          | 0.00019    |
| OOT missed_laundering_pct   | 0.0018   | 0.0042           | 0.0018     |
| OOT missed_cases            | 3        | 7                | 3          |
| OOT queue_cases_per_day     | 119.2    | 62.9             | 119.2      |
| OOT high_priority_per_day   | 19.8     | 19.8             | 119.2      |
| OOT high_priority_precision | 0.9952   | 0.9952           | 0.1686     |
| TEST missed%                | 0.0097   | 0.0187           | 0.0097     |

## Funnel (OOT, modo normal; positivos = transacciones de lavado)

| stage                               |    n_in |   n_out |   positives_out |   leakage |
|:------------------------------------|--------:|--------:|----------------:|----------:|
| transacciones                       | 2456064 | 2456064 |            2837 |    0      |
| alertas                             | 2456064 |   29642 |            2810 |    0.0095 |
| casos                               |   29642 |   25601 |            2810 |    0      |
| escalados (review + alta prioridad) |   25601 |    9944 |            2807 |    0.0011 |
| alta prioridad                      |    9944 |    1650 |            2761 |    0.0164 |

## Casos de lavado auto-cerrados por familia real (OOT, modo normal)

| true_family   |   casos |   auto_cerrados |
|:--------------|--------:|----------------:|
| behavioural   |      74 |               0 |
| cash          |     107 |               0 |
| concentration |     135 |               0 |
| layering      |     497 |               2 |
| structuring   |     867 |               1 |

## Recall extremo a extremo por tipología (OOT, modo normal)

| laundering_type      |   recall |
|:---------------------|---------:|
| Smurfing             | 0.954373 |
| Cash_Withdrawal      | 0.98     |
| Fan_Out              | 0.98374  |
| Cycle                | 0.987654 |
| Deposit-Send         | 0.988281 |
| Scatter-Gather       | 0.988506 |
| Layered_Fan_Out      | 0.992308 |
| Layered_Fan_In       | 0.994118 |
| Stacked Bipartite    | 0.994764 |
| Behavioural_Change_2 | 1        |
| Over-Invoicing       | 1        |
| Fan_In               | 1        |
| Structuring          | 1        |
| Bipartite            | 1        |
| Behavioural_Change_1 | 1        |
| Gather-Scatter       | 1        |
| Single_large         | 1        |
