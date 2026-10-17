# EDA — SAML-D

## Resumen

|   filas |   lavado |   pct_lavado | desde               | hasta               |   emisores |   receptores |
|--------:|---------:|-------------:|:--------------------|:--------------------|-----------:|-------------:|
| 9504852 |     9873 |       0.1039 | 2022-10-07 10:35:19 | 2023-08-23 10:57:12 |     292715 |       652266 |

## Por mes (para definir el split temporal)

| mes     |   filas |   lavado |   pct_lavado |
|:--------|--------:|---------:|-------------:|
| 2022-10 |  708654 |      694 |       0.0979 |
| 2022-11 |  897621 |      794 |       0.0885 |
| 2022-12 |  900341 |      907 |       0.1007 |
| 2023-01 |  908320 |      940 |       0.1035 |
| 2023-02 |  904806 |      946 |       0.1046 |
| 2023-03 |  908562 |      927 |       0.102  |
| 2023-04 |  902883 |      962 |       0.1065 |
| 2023-05 |  917601 |      866 |       0.0944 |
| 2023-06 |  897243 |     1024 |       0.1141 |
| 2023-07 |  902239 |      983 |       0.109  |
| 2023-08 |  656582 |      830 |       0.1264 |

## Tipologías

| laundering_type        |   sospechosa |   filas | familia       |
|:-----------------------|-------------:|--------:|:--------------|
| Structuring            |            1 |    1870 | structuring   |
| Cash_Withdrawal        |            1 |    1334 | cash          |
| Deposit-Send           |            1 |     945 | structuring   |
| Smurfing               |            1 |     932 | structuring   |
| Layered_Fan_In         |            1 |     656 | layering      |
| Layered_Fan_Out        |            1 |     529 | layering      |
| Stacked Bipartite      |            1 |     506 | layering      |
| Behavioural_Change_1   |            1 |     394 | behavioural   |
| Bipartite              |            1 |     383 | concentration |
| Cycle                  |            1 |     382 | layering      |
| Fan_In                 |            1 |     364 | concentration |
| Gather-Scatter         |            1 |     354 | layering      |
| Behavioural_Change_2   |            1 |     345 | behavioural   |
| Scatter-Gather         |            1 |     338 | layering      |
| Single_large           |            1 |     250 | cash          |
| Fan_Out                |            1 |     237 | concentration |
| Over-Invoicing         |            1 |      54 | behavioural   |
| Normal_Small_Fan_Out   |            0 | 3477717 |               |
| Normal_Fan_Out         |            0 | 2302220 |               |
| Normal_Fan_In          |            0 | 2104285 |               |
| Normal_Group           |            0 |  528351 |               |
| Normal_Cash_Withdrawal |            0 |  305031 |               |
| Normal_Cash_Deposits   |            0 |  223801 |               |
| Normal_Periodical      |            0 |  210526 |               |
| Normal_Plus_Mutual     |            0 |  155041 |               |
| Normal_Mutual          |            0 |  125335 |               |
| Normal_Foward          |            0 |   42031 |               |
| Normal_single_large    |            0 |   20641 |               |

**Tipologías sospechosas sin familia asignada:** ninguna

## Tipo de pago

| payment_type    |   filas |   lavado |   pct_lavado |
|:----------------|--------:|---------:|-------------:|
| Credit card     | 2012909 |     1136 |       0.0564 |
| Debit card      | 2012103 |     1124 |       0.0559 |
| Cheque          | 2011419 |     1087 |       0.054  |
| ACH             | 2008807 |     1159 |       0.0577 |
| Cross-border    |  933931 |     2628 |       0.2814 |
| Cash Withdrawal |  300477 |     1334 |       0.444  |
| Cash Deposit    |  225206 |     1405 |       0.6239 |

## Ubicación del banco emisor

| sender_bank_location   |   filas |   lavado |   pct_lavado |
|:-----------------------|--------:|---------:|-------------:|
| UK                     | 9183088 |     9253 |       0.1008 |
| Turkey                 |   20902 |       27 |       0.1292 |
| Switzerland            |   20503 |       41 |       0.2    |
| Pakistan               |   20346 |       25 |       0.1229 |
| UAE                    |   20081 |       34 |       0.1693 |
| Nigeria                |   20027 |       25 |       0.1248 |
| Spain                  |   19391 |       27 |       0.1392 |
| Germany                |   19259 |       43 |       0.2233 |
| USA                    |   19027 |       36 |       0.1892 |
| Italy                  |   18895 |       45 |       0.2382 |
| France                 |   18702 |       31 |       0.1658 |
| Japan                  |   18468 |       38 |       0.2058 |
| Morocco                |   18437 |       55 |       0.2983 |
| Austria                |   18050 |       38 |       0.2105 |
| Mexico                 |   17662 |       44 |       0.2491 |
| Albania                |   17648 |       28 |       0.1587 |
| India                  |   17596 |       42 |       0.2387 |
| Netherlands            |   16770 |       41 |       0.2445 |

## Ubicación del banco receptor

| receiver_bank_location   |   filas |   lavado |   pct_lavado |
|:-------------------------|--------:|---------:|-------------:|
| UK                       | 8864634 |     7308 |       0.0824 |
| Pakistan                 |   38980 |      169 |       0.4336 |
| Austria                  |   38844 |      154 |       0.3965 |
| Albania                  |   38783 |      235 |       0.6059 |
| Japan                    |   38729 |       83 |       0.2143 |
| Morocco                  |   38704 |      253 |       0.6537 |
| Germany                  |   38540 |      102 |       0.2647 |
| France                   |   38512 |       82 |       0.2129 |
| Mexico                   |   38385 |      197 |       0.5132 |
| Nigeria                  |   38272 |      251 |       0.6558 |
| Netherlands              |   37314 |      148 |       0.3966 |
| Spain                    |   37288 |       87 |       0.2333 |
| India                    |   36936 |      137 |       0.3709 |
| USA                      |   36850 |       87 |       0.2361 |
| Italy                    |   36517 |      131 |       0.3587 |
| Switzerland              |   36081 |       77 |       0.2134 |
| UAE                      |   35897 |      195 |       0.5432 |
| Turkey                   |   35586 |      177 |       0.4974 |

## Cross-border y cambio de moneda

| cross_border   | cambio_moneda   |   filas |   pct_lavado |
|:---------------|:----------------|--------:|-------------:|
| False          | False           | 8414812 |       0.0734 |
| False          | True            |  155692 |       0.4181 |
| True           | False           |    4178 |       0.9335 |
| True           | True            |  930170 |       0.3232 |

## Montos por clase

|   is_laundering |     p50 |     p90 |      p99 |              max |
|----------------:|--------:|--------:|---------:|-----------------:|
|               0 | 6114.63 | 16558.4 |  44938.2 | 999962           |
|               1 | 5322.79 | 21197.6 | 419540   |      1.26185e+07 |
