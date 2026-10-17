# Clasificador de familia

Entrenado con 4,373 positivos de train; early stopping en test (87 árboles). Si la confianza es < 0.5, la familia es `generic`.


## TEST

F1 macro **0.7772** · accuracy 0.8085 · 4.6% va a `generic` · accuracy sin generic 0.8234

Matriz de confusión (filas = real, columnas = predicha):

|               |   structuring |   layering |   concentration |   cash |   behavioural |
|:--------------|--------------:|-----------:|----------------:|-------:|--------------:|
| structuring   |           610 |         91 |               2 |      0 |             0 |
| layering      |            62 |        450 |              30 |      2 |             0 |
| concentration |            37 |        125 |              43 |      0 |             0 |
| cash          |             0 |          9 |               0 |    287 |             0 |
| behavioural   |             0 |          1 |               0 |      0 |           126 |

```
               precision    recall  f1-score   support

  structuring       0.86      0.87      0.86       703
     layering       0.67      0.83      0.74       544
concentration       0.57      0.21      0.31       205
         cash       0.99      0.97      0.98       296
  behavioural       1.00      0.99      1.00       127

     accuracy                           0.81      1875
    macro avg       0.82      0.77      0.78      1875
 weighted avg       0.80      0.81      0.79      1875
```

## OOT

F1 macro **0.7581** · accuracy 0.8065 · 5.3% va a `generic` · accuracy sin generic 0.8254

Matriz de confusión (filas = real, columnas = predicha):

|               |   structuring |   layering |   concentration |   cash |   behavioural |
|:--------------|--------------:|-----------:|----------------:|-------:|--------------:|
| structuring   |           910 |        150 |              13 |      0 |             0 |
| layering      |            98 |        629 |              54 |      1 |             0 |
| concentration |            41 |        177 |              44 |      0 |             0 |
| cash          |             0 |         12 |               1 |    443 |             0 |
| behavioural   |             0 |          0 |               0 |      2 |           262 |

```
               precision    recall  f1-score   support

  structuring       0.87      0.85      0.86      1073
     layering       0.65      0.80      0.72       782
concentration       0.39      0.17      0.24       262
         cash       0.99      0.97      0.98       456
  behavioural       1.00      0.99      1.00       264

     accuracy                           0.81      2837
    macro avg       0.78      0.76      0.76      2837
 weighted avg       0.80      0.81      0.79      2837
```
