# Plan de implementación — Módulo ML (scoring AML)

## Alcance de esta parte

Responsable: módulo de ML y su API. El agente investigador, el orquestador y la bandeja del analista son de otros miembros del equipo y consumen esta API.

Entregables:

1. **Modelo binario calibrado**: probabilidad de que una transacción sea lavado.
2. **Clasificador de familia de tipología**: llave de enrutamiento hacia agentes especializados (funnel).
3. **Score de caso**: agregación por cuenta y ventana de tiempo.
4. **Puntos de operación según capacidad de analistas**, cada uno con su costo (leakage y cola).
5. **Trazabilidad**: reason codes (SHAP), registro de auditoría y model card.
6. **Ciclo de feedback** con reentrenamiento simulado mes a mes.
7. **API REST** que sirve todo lo anterior.

Prioridad: **P0** = sin esto no hay demo · **P1** = responde al feedback recibido · **P2** = si sobra tiempo.

---

## Stack

| Pieza | Elección | Por qué |
|---|---|---|
| Datos y features | **DuckDB** (SQL con window functions) | 9,5M filas en 16 GB de RAM sin problema; las ventanas `RANGE` hacia atrás se escriben directo |
| Modelo | **LightGBM** + calibración isotónica (scikit-learn) | Rápido, maneja el desbalance y trae SHAP nativo (`pred_contrib`) |
| Selección y tuning | Gini univariado, PSI, Boruta (submuestra), **Optuna** | Metodología de modelamiento del banco (`modelamiento.xlsx`) |
| API | **FastAPI** + uvicorn | Documentación OpenAPI automática para el resto del equipo |
| Almacén | Archivo DuckDB (`data/aml.duckdb`) | Scores precalculados, auditoría y feedback en un solo lugar |
| Entorno | Python 3.13, `venv` + `requirements.txt` | Ya está instalado en la máquina |

Nota macOS: LightGBM necesita OpenMP (`brew install libomp`) si el wheel falla al importar.

---

## Estructura del repo

```
hackathon-aml/
├── data/
│   ├── raw/              # SAML-D.csv (no se versiona)
│   └── aml.duckdb        # tablas: transactions, features, scores, cases, audit_log, feedback
├── src/aml/
│   ├── config.py         # rutas, fechas de corte del split, familias de tipología
│   ├── ingest.py         # CSV -> DuckDB, tipos, timestamp unificado
│   ├── features.py       # SQL de features con ventanas solo hacia atrás
│   ├── split.py          # ventana de desarrollo (train/test 70/30) + OOT
│   ├── select.py         # Gini + fill rate, PSI, Boruta -> variables finalistas
│   ├── baseline.py       # "modelo vigente": reglas tradicionales de monitoreo
│   ├── metrics.py        # Gini, KS, PR-AUC, bootstrap, calibración por bandas
│   ├── train_binary.py   # LightGBM binario + calibración
│   ├── train_family.py   # LightGBM multiclase de familia
│   ├── cases.py          # agrupación en casos y score de caso
│   ├── thresholds.py     # curvas, puntos de operación y costo por modo
│   ├── explain.py        # reason codes con SHAP
│   ├── score_batch.py    # puntúa todo y escribe scores + auditoría
│   ├── retrain_sim.py    # reentrenamiento mes a mes con feedback (P2)
│   └── api/
│       ├── main.py
│       └── schemas.py    # contrato pydantic compartido con el equipo
├── models/               # artefactos versionados: binary_v1.txt, calibrator_v1.pkl, ...
├── reports/              # model_card.md, curvas, métricas por tipología
├── notebooks/            # solo exploración (EDA)
├── requirements.txt
└── PLAN.md
```

---

## Fases

### Fase 0 — Setup y datos (P0)

- Crear el `venv` e instalar `duckdb lightgbm scikit-learn pandas pyarrow fastapi uvicorn shap matplotlib`.
- Descargar SAML-D desde Kaggle: a mano desde la web, o con `kaggle datasets download berkanoztas/synthetic-transaction-monitoring-dataset-aml` (requiere tu propio token de Kaggle).
- `ingest.py`: cargar en DuckDB, unir `Date` + `Time` en `ts` y asignar un `txn_id` estable.
- EDA corta: proporción de lavado, rango de fechas, conteo por `Laundering_type`, valores de ubicación y de `Payment_type`. **Confirmar los nombres exactos de las 28 tipologías** antes de cerrar el mapeo de familias.

**Hecho cuando:** la tabla `transactions` existe y hay un resumen del EDA en `reports/eda.md`.

#### Resultados de la fase 0 (completada)

- **9.504.852 transacciones**, 9.873 de lavado (**0,104%**), del 2022-10-07 al 2023-08-23. La tasa es estable mes a mes.
- **Split fijado** según la metodología del banco: desarrollo oct–may (70/30 train/test, estratificado) y **OOT jun–ago** (3 meses, ~2,8k positivos). Las fechas están en `config.py`.
- **Las 17 tipologías calzan con las 5 familias.** Over-Invoicing tiene solo 54 casos y quedó dentro de `behavioural`.
- **Señales fuertes en datos crudos:**
  - Cash Deposit 0,62% y Cash Withdrawal 0,44% de lavado, contra ~0,056% en tarjetas, cheque y ACH.
  - Cross-border 0,28%.
  - Receptores en Marruecos, Nigeria, Albania, UAE, México y Turquía: 0,5–0,65%, contra 0,08% en UK.
  - Cambio de moneda dentro del país: 0,42%.
- **Montos:** el p99 del lavado es ~420k, contra ~45k en lo normal.
- **Las cuentas lavadoras tienen sobre todo tráfico normal:** solo el 1,3% de sus transacciones es lavado. Esto favorece las features de desviación respecto al propio historial.
- **Sin fuga por cuentas:** de los 1.028 emisores que lavan en test, el 99% aparece en train, pero solo el 13% lavó en train. Igual, los IDs no se usan como feature.
- **La ubicación de riesgo no se define a mano:** va como categórica a LightGBM. Si después se necesita una lista, se calcula solo con train.

### Fase 1 — Features point-in-time (P0)

Todas las ventanas usan `RANGE BETWEEN INTERVAL 'N' DAY PRECEDING AND INTERVAL 1 MICROSECOND PRECEDING`: solo transacciones **estrictamente anteriores**, ni siquiera las del mismo segundo.

| Grupo | Features |
|---|---|
| Velocidad del emisor | número de transacciones y monto total en 1, 7 y 30 días |
| Anomalía de monto | z-score contra el historial de 30 días; razón contra la mediana |
| Contrapartes | si la contraparte es nueva para el emisor; contrapartes únicas en 7 días (fan-out) |
| Lado receptor | número de transacciones y monto recibido en 7 días; emisores únicos en 7 días (fan-in) |
| Geografía | si es cross-border; si las monedas no coinciden; si la ubicación es de riesgo (definida en el EDA) |
| Estructuración | monto justo bajo un umbral de reporte; monto redondo; transacciones parecidas en 24 h |
| Temporal | horas desde la transacción anterior; hora del día; fin de semana |
| Categóricas | `Payment_type`, ubicaciones y monedas (categóricas nativas de LightGBM) |

**Excluidos siempre:** `Laundering_type`, IDs de cuenta y `Is_laundering`.

**Hecho cuando:** la tabla `features` existe y pasan dos tests de no-fuga:
1. **Truncamiento:** las features calculadas con datos hasta T son idénticas a las calculadas con todos los datos, para cada transacción anterior a T.
2. **Recálculo manual:** en transacciones de muestra, pandas recalcula a mano las features y coinciden con las de DuckDB.

#### Resultados de la fase 1 (completada)

- **39 features numéricas y 5 categóricas** sobre 9,5M filas, en **40 s** (`python -m aml.features && python -m aml.split`).
- **Tests de no-fuga OK** (`pytest tests/`). Además, el test de truncamiento detecta una fuga inyectada a propósito: una ventana con 1 día `FOLLOWING` cambia 6.802 filas.
- **Muestras:**

| Muestra | Período | Filas | Lavado |
|---|---|---|---|
| warmup (excluido) | oct 7 – nov 5 | 866k | 788 |
| train | nov 6 – may 31 (70%) | 4,33M | 4.373 |
| test | nov 6 – may 31 (30%) | 1,85M | 1.875 |
| oot | jun 1 – ago 23 | 2,46M | 2.837 |

- **Gini univariado en train (top):** `is_new_counterparty` 71, `pair_prev_cnt` 68, `s_hours_since_prev` 57, `s_amt_1d` 52, `s_out_in_ratio_7d` 51 (FR 30%), `s_cnt_1d` 51.
- **Ojo para el pitch:** en SAML-D el lavado va a contrapartes nuevas y desde cuentas *menos* activas que el promedio. Las cuentas normales de alta frecuencia dominan el volumen.
- **Gini univariado ~0 (`amount`, `hour`, `dow`, `is_round_100`, `is_near_10k`):** el filtro de la fase 1b las sacaría. Antes de descartar `amount`, conviene revisarla en el modelo, porque puede aportar por interacción (el p99 del lavado es 10 veces mayor).

### Fase 1b — Selección de variables (P1, según metodología)

- **Univariado (sobre train):** Gini por variable y fill rate. Pasa la variable que cumpla alguna de: Gini > 20% y FR > 10% · Gini > 15% y FR > 20% · Gini > 10% y FR > 40% · Gini > 5% y FR > 80%.
- **Estabilidad del Gini:** el Gini por mes dentro de train debe variar poco.
- **PSI train contra OOT:** si el PSI es > 0,25 la variable sale; entre 0,10 y 0,25 se revisa.
- **Boruta** sobre una submuestra (todos los positivos y ~200k negativos), para confirmar poder predictivo contra variables sombra.
- **Correlación:** de cada par con |ρ| > 0,9 se queda la de mayor Gini.
- **Entregable:** `reports/feature_selection.md` con la tabla de variables finalistas y el motivo de cada exclusión.

### Fase 2 — Baseline y modelo binario (P0)

**Muestras (metodología):**
- **Desarrollo:** oct 2022–may 2023, dividido en 70% train / 30% test, estratificado por `is_laundering`, con una asignación determinista por `txn_id`.
- **OOT:** jun–ago 2023. No se toca hasta elegir el modelo final.
- Representatividad: se compara la distribución de las top variables entre train, test y OOT.
- Por qué el test aleatorio no basta: patrones de una misma cuenta pueden quedar repartidos entre train y test. El OOT es la evaluación que vale.

**Baseline = "modelo vigente":** `baseline.py` implementa reglas típicas de monitoreo (monto alto, cash, cross-border hacia jurisdicción de riesgo, velocidad alta). Se le calcula el mismo Gini, KS y recall, y todo se compara contra él.

**Modelo:**
- LightGBM inicial con todas las variables → importancia → variables finalistas (fase 1b).
- **Optuna** (bayesiano, ~50 trials) con CV estratificado de 3 folds sobre train. La métrica a optimizar es PR-AUC.
- Calibración isotónica sobre test.

**Métricas (global, por mes y por segmento: tipo de pago, cross-border, familia):**
- **Gini y KS** (el idioma del banco) más PR-AUC (por el desbalance).
- Recall a un umbral de alerta, precisión@K y **recall por tipología**.
- **Bootstrap** (1000 remuestreos) para el IC 95% del Gini en OOT.
- **Calibración por bandas:** deciles de score con intervalo binomial. Equivale a las bandas de Vasicek, adaptado a AML.
- **Sensibilidad:** estrés de ±1σ y ±2σ en las top variables, junto con SHAP.

**Criterios de aceptación:**
- La diferencia de Gini entre train y OOT es **≤ 15 puntos**; si es mayor, se documenta y se justifica.
- Gana claramente al baseline en el OOT.
- La tasa observada cae dentro de la banda de calibración en la mayoría de los deciles.

**Hecho cuando:** `models/binary_v1`, `reports/metrics_binary.json` y `reports/model_comparison.md` (baseline vs. LightGBM inicial vs. final) existen.

#### Resultados de las fases 1b y 2 (completadas)

**Selección** (`python -m aml.select` → `reports/feature_selection.md`): quedaron **18 finalistas de 44**.
- El PSI excluyó los contadores acumulados desde el inicio del dataset (`s_days_since_first` con PSI 3,17, `s_prev_cnt_all` 0,84, `r_prev_cnt_all` 0,29, `pair_prev_cnt` 0,28). Crecen con el calendario, así que el modelo habría aprendido "qué fecha es".
- La correlación quitó duplicados como `log_amount`/`amount` y `cross_border`/`currency_mismatch`.
- Boruta rechazó las categóricas de moneda y ubicación y algunos contadores redundantes.

**Modelo** (`python -m aml.train_binary tune && python -m aml.train_binary fit` → `reports/model_comparison.md`):

| Modelo | Features | Gini OOT | KS OOT | PR-AUC OOT | Recall @1% de alertas |
|---|---|---|---|---|---|
| Baseline de reglas (vigente) | 6 reglas | 44,7 | 41,0 | 0,004 | 9,4% |
| LightGBM inicial | 44 | 99,98 | 99,1 | 0,987 | 99,6% |
| **LightGBM final** (Optuna, 30 trials) | 18 | **99,94** (IC 99,92–99,96) | 98,2 | 0,976 | 99,0% |

- **Gap de Gini train − OOT: 0,05 pts** (criterio ≤ 15).
- **Recall por tipología con el umbral del 1%:** ≥ 94,7% en todas. La más difícil es Smurfing con 94,7%; la siguen Cash_Withdrawal (97,5%) y Scatter-Gather (97,7%).
- **El baseline**, para atrapar el 65% del lavado, alerta el 24% de todas las transacciones.
- **Calibración de Platt sobre test:** no usé la isotónica porque daba p = 0 exacto a 2,39M de transacciones, 8 de ellas de lavado. En OOT pasan 3 de 7 bandas, **todas las bajas** (las que deciden el auto-cierre). En las bandas medias sobreestima levemente, que es la dirección conservadora.
- **Ablación (¿hay fuga?):**

| Features quitadas | Gini OOT | PR-AUC OOT |
|---|---|---|
| `is_new_counterparty` | 99,4 | 0,87 |
| + `pair_cnt_7d` | 99,0 | 0,84 |
| + `r_hours_since_prev` y `s_hours_since_prev` | 98,3 | 0,78 |

  No hay una sola variable que filtre la respuesta. La separabilidad es propia de SAML-D: el 77% del lavado va a una contraparte nueva, contra el 5% de lo normal. **Va como limitación en la model card**, porque en datos reales hay que esperar métricas bastante menores.

### Fase 3 — Casos y puntos de operación (P0)

- `cases.py`: las transacciones sobre el umbral de alerta se agrupan por `sender_account` en ventanas de 7 días.
- Score del caso: máximo score, número de transacciones marcadas, monto marcado total y score medio. Partir con el máximo y, si alcanza el tiempo, un modelo pequeño a nivel de caso (P2).
- Etiqueta del caso para evaluar: positivo si contiene al menos una transacción de lavado.
- `thresholds.py`:
  - Curva de tasa de auto-cierre contra leakage, global y **por familia**.
  - Puntos de operación: **normal**, **capacidad reducida** y **sin analista**. Cada uno con su umbral, % de auto-cierre, leakage esperado y casos en cola por día.
  - Se elige la mayor tasa de auto-cierre que cumpla la restricción de leakage (por ejemplo, ≤ 0,5% y 0 casos de las familias graves).
- Esto equivale al **punto de corte teórico** de la metodología. El impacto se expresa como errores tipo I (casos falsos para el analista, horas) y tipo II (lavado no detectado), en vez de en mora.
- Los umbrales se fijan sobre test y se reportan sobre OOT.
- Guardar en `models/thresholds_v1.json`.

**Hecho cuando:** la tabla de puntos de operación y la curva están en `reports/` y se calcularon sobre valid, no sobre test.

#### Resultados de la fase 3 (+ fases 4 y 5 base) — completadas

El pipeline completo corre en ~1 minuto:

```
python -m aml.train_family && python -m aml.score_batch && python -m aml.cases && python -m aml.thresholds && python -m aml.export
```

- **Umbral de alerta:** p ≥ 0,000463, que da 99% de recall de transacciones en test. En OOT se alerta el 1,2% (29.642 transacciones).
- **Casos:** alertas del mismo emisor dentro de 7 días; queda 1,16 alertas por caso. En OOT son 25.601 casos, 1.680 con lavado.
- **Puntos de operación** (elegidos en test, reportados en OOT, 84 días):

| Modo | Auto-cierre | Lavado que se escapa | Cola (casos/día) | Alta prioridad (precisión) |
|---|---|---|---|---|
| normal | 61,2% | 0,18% (3 de 1.680) | 119 | 20/día (99,5%) |
| capacidad reducida (50%) | 79,5% | 0,42% (7) | 63 | 20/día |
| sin analista | 61,2% | 0,18% | 0 (119/día en retención preventiva) | — |

- **Funnel OOT** (positivos = transacciones de lavado): 2,46M transacciones → 29.642 alertas (pierde 0,95%) → 25.601 casos → 9.944 escalados (pierde 0,11% más) → 1.650 de alta prioridad.
- **Familias de los casos de lavado auto-cerrados en modo normal:** layering 2 y structuring 1; behavioural, cash y concentration 0.
- **Clasificador de familia** (`reports/family_model.md`): F1 macro 0,76 y accuracy 81% en OOT. Concentration se confunde con layering. El 5% va a `generic`.
- **Reason codes:** top 3 contribuciones SHAP positivas, con texto en español (`aml/explain.py`).
- **Export a Postgres:** 25.601 casos y 29.642 transacciones (66 MB, 8 s). **No incluye etiquetas reales.** Probado contra `aml_dev` local con los tests de contrato.

#### Scoring en vivo (`POST /score/live`) — completado

- **Predictor LightGBM en Python puro** (`aml/api/predictor.py`): coincide con LightGBM en 10⁻¹⁶ (7.921 filas, con NaN). Sin lightgbm, numpy ni scipy en Vercel. El modelo compacto (3,8 MB) vive en `aml.meta['live_model']`.
- **Features en vivo** (`aml/api/live.py`): una consulta indexada sobre `aml.history` (1,56M transacciones desde el 1 de julio de 2023), más `aml.pairs_before` y `aml.accounts_before` para las features "desde siempre".
- **Validación:** idéntico al batch en 400 transacciones de agosto (18 de 18 features, Δp ≤ 7e-16, familia 400 de 400).
- **Carga:** `python -m aml.export_live`, o `--model-only` tras reentrenar. Supabase queda en 389 MB de 500.

### Fase 4 — Clasificador de familia (P1)

Mapeo de las 17 tipologías sospechosas a 5 familias (validado en la fase 0; ver `config.py`):

| Familia | Ejemplos de tipología |
|---|---|
| `structuring` | Structuring, Smurfing, Deposit-Send |
| `layering` | Layered fan-out/fan-in, Stacked bipartite, Cycle, Scatter-gather, Gather-scatter |
| `concentration` (mulas) | Fan-in, Fan-out, Bipartite |
| `cash` | Cash withdrawal, Single large |
| `behavioural` | Behavioural change, Over-invoicing |

- LightGBM multiclase entrenado **solo con positivos**, con las mismas features. `Laundering_type` se usa solo como target.
- En inferencia devuelve la familia y su probabilidad. Si la confianza es baja (< 0,5), la familia es `generic` y el caso va al agente general.

**Hecho cuando:** existen el F1 macro y la matriz de confusión por familia.

### Fase 5 — Explicabilidad y auditoría (P1)

- `explain.py`: con `pred_contrib=True`, tomar el top 5 de features por contribución y convertirlo en reason codes legibles, por ejemplo `{"code": "VELOCITY_7D", "value": 14, "baseline": 1.2, "text": "14 transacciones en 7 días (media 1,2)"}`.
- `score_batch.py` puntúa test (y valid), y escribe en `scores` y en `audit_log`: `txn_id`, `ts_scored`, snapshot de features (JSON), score crudo, score calibrado, banda, familia, reason codes, `model_version` y `threshold_version`.
- `reports/model_card.md`: datos de entrenamiento, split, métricas globales y por tipología, limitaciones (datos sintéticos, sin KYC) y uso previsto. Sigue la sección de "Limitaciones del modelo" de la metodología: debilidades de discriminación y de calibración.
- `reports/ficha_viabilidad.md` (1 página): propósito, técnicas, supuestos, dentro y fuera de alcance, limitaciones.

### Fase 6 — API (P0 para la base, P1 para el resto)

| Método | Ruta | Devuelve | Prioridad |
|---|---|---|---|
| GET | `/health` | Estado y versiones cargadas | P0 |
| POST | `/score/transactions` | Por cada `txn_id`: score, banda, familia y reason codes | P0 |
| GET | `/cases?mode=normal&limit=50` | Casos ordenados por prioridad, ya con banda y familia | P0 |
| GET | `/cases/{case_id}` | Detalle: transacciones, score de caso y reason codes agregados | P0 |
| GET | `/score/account/{id}?from=&to=` | Score agregado de la cuenta en una ventana | P1 |
| GET | `/thresholds` | Puntos de operación vigentes y su costo | P1 |
| GET | `/model/metrics` | Curvas y métricas del funnel por etapa | P1 |
| GET | `/audit/{txn_id}` | Registro completo de auditoría | P1 |
| POST | `/feedback` | Recibe la decisión del agente y del analista (`case_id`, `actor`, `decision`, `notes`) | P1 |

Reglas del contrato que hay que acordar con el equipo:
- **El agente puede subir la banda que devuelve la API, pero nunca bajarla.**
- Bandas: `auto_close_eligible` · `review` · `high_priority`.
- **Fallback:** si el modelo no carga, `/score` responde con reglas simples (monto alto, cross-border, velocidad) y `"model_version": "rules_fallback"`.

`schemas.py` se comparte en cuanto esté listo, aunque los endpoints devuelvan datos falsos, para que el equipo empiece a integrar desde el principio.

#### Estado de la fase 6 (base completada)

**Arquitectura:** el batch corre en local (DuckDB + LightGBM) y exporta a **Postgres**; la **API en Vercel** solo lee y escribe Postgres, sin cargar el modelo. La guía para el equipo está en `docs/API.md` y el contrato en `docs/openapi.json`.

- Los backends `mock` y `postgres` se eligen con `AML_BACKEND`. La banda se deriva del score con los umbrales del `mode`, no se guarda.
- La regla "el agente no baja la banda" se aplica en `POST /feedback` (responde 422).
- Los 10 tests de contrato pasan con los dos backends (Postgres local `aml_dev` cargado con `seed_mock`).
- Las dependencias de Vercel ocupan 46 MB (`requirements.txt`). El stack de ML está en `requirements-ml.txt` (`pip install -r requirements-ml.txt`).
- **Pendiente:** `aml/export.py`, que llena `aml.cases`, `aml.txn_scores` y `aml.meta` con data real. Depende de la fase 3 (casos y puntos de operación) y de la fase 5 (reason codes).

### Fase 7 — Feedback y reentrenamiento simulado (P2)

- `retrain_sim.py`: por cada mes de test se puntúa, se simula el feedback del analista con la verdad de SAML-D (más una muestra aleatoria del 5% de los auto-cerrados) y se reentrena sumando ese mes.
- Gráfico: leakage y PR-AUC mes a mes. Muestra que el sistema aprende.
- Monitoreo de drift: distribución semanal del score (PSI simple).

### Fase 8 — Material para la demo (P1)

- Funnel con volumen que entra y sale de cada etapa: transacciones → alertas → casos → auto-cierre / review / prioridad alta, con el leakage de cada etapa.
- Tabla de puntos de operación según capacidad (contingencia sin analista).
- Un caso de ejemplo con sus reason codes, de punta a punta.

---

## Orden de trabajo sugerido

1. Fase 0 → **compartir `schemas.py` con datos falsos** para desbloquear al equipo.
2. Fases 1, 2 y 3: el núcleo. Con esto ya hay demo.
3. Fases 6 (P0), 4 y 5.
4. Fases 8 y 7.

## Decisiones abiertas (con el equipo)

- [ ] ¿Quién arma los casos: el ML (propuesto) o el orquestador?
- [ ] Restricción de leakage aceptable para el auto-cierre (¿0,5%? ¿0 en familias graves?).
- [ ] ¿Qué familias van a "nunca auto-cerrar"?
- [ ] Capacidad de analistas para simular cada modo (casos por hora por analista).
- [ ] Ventana del caso: ¿7 días por cuenta emisora, o también por receptora?

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Fuga temporal en las features (métricas infladas) | Test de point-in-time en la fase 1 y split por fecha |
| Tipologías sintéticas demasiado separables (AUC ≈ 1) | Reportar recall por tipología y precisión@K, no solo AUC; decirlo explícitamente en la model card |
| Desbalance extremo (~0,1%) | PR-AUC como métrica principal y calibración sobre valid |
| Familias con muy pocos ejemplos | Fusionar familias o mandar a `generic` |
| El equipo se bloquea esperando la API | `schemas.py` y endpoints con datos falsos desde el día 1 |
