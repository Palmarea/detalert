# Automejora del modelo con la salida de los agentes

**Resumen:** les entregamos la salida de los agentes como dataset (`salida_agentes_para_ml.jsonl` y `.csv`, una fila por caso) y las propuestas de umbral en el mismo formato de su página de umbrales. Con eso, el modelo puede mejorar en cuatro ciclos: umbrales, familia, variables nuevas y etiquetas del analista. La bandeja ya muestra el espectro y las propuestas en vivo (`/umbrales.html`).

## Lo que encontraron los agentes en 14 casos reales

| Señal | Cuántos | Qué le dice al modelo |
|---|---|---|
| La familia de la API no coincide con la que infirió el agente | **14 de 14** | El clasificador de familia necesita entrenarse; hay etiquetas débiles para hacerlo |
| El agente pidió más contexto | **7 de 14** | Faltan variables: `receptores_del_emisor_7d` (4 veces) y `contrapartes_90d` (4 veces) |
| Decisiones | 7 escaladas · 3 prioridad alta · 4 cerradas | Distribución por banda para calibrar la cola |
| El agente bajó una banda | **0** | Se cumple el contrato |

## Los archivos

| Archivo | Qué trae |
|---|---|
| `salida_agentes_para_ml.jsonl` | Una fila por caso: `case_id`, `case_score`, `banda_modelo`, `family_api`, `accion_agente`, `decision_agente`, `agent_band`, `banda_subio`, `familia_inferida`, `confianza`, `tipologias`, `tipologia_normal_mas_cercana`, `firmas_disparadas` (con sus valores), `evidencia` (variable y valor), `n_objeciones`, `pidio_mas_contexto`, `consultas_pedidas`, `contingencia`, `resolucion_analista`, versiones del modelo y de los umbrales |
| `salida_agentes_para_ml.csv` | Lo mismo, sin las columnas anidadas, para abrir rápido |
| `propuestas_para_ml.json` | Etiquetas de familia y propuestas del agente de aprendizaje |
| Su base (`POST /feedback`) | La decisión de cada caso con `actor: "agent"`: ya tienen 11 registros |

Las filas con `origen: "score_live"` son casos del jurado (`/score/live`): no tienen `case_id` de ustedes.

## Ciclo 1 · Umbrales (lo que dibuja su página)

1. **Señal del agente:**
   - **Endurecer:** casos en cierre automático que el agente escaló, o en los que una firma del negocio se disparó. Propone bajar el umbral de cierre.
   - **Relajar:** casos de revisión que el agente marca como falso positivo probable. Propone subirlo, pero queda **bloqueado** hasta que el analista apruebe N casos.
2. **Formato:** cada propuesta llega con la forma exacta de `PROPS` de su `umbrales.html`: `id`, `status`, `ask`, `from`, `to`, `guards`, `evidence` y `log`.
3. **Su compuerta:** la simulación OOT con sus tres límites:
   - lavado que se cierra solo ≤ 0,30 %;
   - precisión de prioridad alta ≥ 95 %;
   - cola ≤ 130 casos por día.

   Si pasa, publican `thresholds_v1.1-agente`; si no, `rejected` con el motivo.
4. **Lo que les pedimos implementar:**

| Endpoint | Qué hace |
|---|---|
| `POST /thresholds/proposals` | Recibe una propuesta del agente (formato `PROPS`) |
| `GET /thresholds/proposals` | Lista las propuestas con su `status`, `guards` calculados por su simulación y su `log` |
| `POST /thresholds/proposals/{id}/apply` | La aplica si pasó los límites, y versiona los umbrales |

Mientras no existan, el agente publica sus propuestas en la bandeja (`POST /api/agent-learning`) y la página las muestra con `guards` parciales. Cuando existan, la bandeja lee de su API, y el estado y los límites pasan a ser los de su simulación, la fuente de verdad.

## Ciclo 2 · Familia (`train_family.py`)

- **Etiqueta débil:** `familia_inferida`. Úsenla con `confianza ≥ 60` o cuando haya alguna `firmas_disparadas` de esa familia.
- **Pesos sugeridos:** `resolucion_analista` (cuando exista) > firma disparada + confianza alta > solo la confianza del agente.
- `family_mock_overridden = true` marca los casos donde el agente corrigió su `family`. Hoy son los 14.

## Ciclo 3 · Variables nuevas

Lo que el agente pidió y no estaba entre las 18 variables (el skill de negocio ya lo marca como hueco):

| Consulta del agente | Variable sugerida | Para qué |
|---|---|---|
| `receptores_del_emisor_7d` | `s_uniq_rcv_7d`: receptores distintos del emisor en 7 días | Separar la dispersión en abanico (Fan_Out) del pago de nómina |
| `contrapartes_90d` | `pair_cnt_90d` o antigüedad de la contraparte | Distinguir "contraparte nueva" de "relación antigua sin uso reciente" |
| `salidas_del_receptor_7d` | `r_out_amt_7d`, monto que reenvía el receptor | Confirmar la cuenta mula |
| `subgrafo_2_3_saltos` | Variables de ciclo a 2-3 saltos | Detectar Cycle y Bipartite |

## Ciclo 4 · El analista como etiqueta

Cuando el analista aprueba o rechaza en la bandeja, eso debe llegarles por `POST /feedback` con `actor: "analyst"` (`approved`, `rejected` o `sar_filed`). Es la etiqueta más confiable: `sar_filed` > `rejected` / `approved` > decisión del agente.

## Reglas para no aprender mal

- **El agente nunca baja una banda.** Relajar umbrales requiere al analista.
- **Del lado del agente:** ningún cambio mayor a 25 %, nada se propone con menos de 5 casos, y cada `case_id` citado existe.
- **De su lado:** la simulación OOT decide. Los umbrales se versionan, y cada decisión guarda `model_version` y `threshold_version`.
- **Datos sintéticos:** en un banco real las métricas bajan. Validen con OOT antes de publicar.

## En vivo en la bandeja

`/umbrales.html` (botón "Umbrales y aprendizaje") se refresca cada 10 s. Muestra el espectro vigente, las propuestas del agente con su estado, la evidencia y el registro. Cuando su API tenga `GET /thresholds/proposals`, la página mostrará directamente sus estados y límites.
