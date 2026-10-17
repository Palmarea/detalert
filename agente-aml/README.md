# Agente cognitivo AML · material para el equipo

Esta carpeta trae lo que el equipo necesita para integrarse con el agente AML del hack. **El código del agente corre en local y no está en este repo.**

| Carpeta | Qué hay |
|---|---|
| `para_equipo/PARA_FRONTEND.md` | Qué llega a la bandeja (`/api/ingest`), el pensamiento del agente (`context.aml.pasos`), el caso del jurado y cómo mostrarlo |
| `para_equipo/PARA_ML.md` | Qué recibe `/feedback`, qué endpoints usa el agente, los casos enviados y el ciclo de aprendizaje |
| `para_equipo/propuestas_para_ml.json` | Etiquetas de familia y propuestas del agente de aprendizaje |
| `skill/` | El skill de negocio (`aml-transaction-reviewer`), la matriz de reglas y sus límites en código |
| `dictamenes/aml/` | Dos dictámenes reales y lo que se mandó a la bandeja |
| `postman/hack-aml.postman_collection.json` | Colección para probar la API de ML y la bandeja. Llena `ml_key` e `ingest_token` en tu entorno de Postman, nunca en el archivo |
| `casos_jurado/` | Transacciones de ejemplo para el caso en vivo (`POST /score/live`) |

## Flujo

API de ML (caso, banda, familia, razones) → **agente evaluador** (código: banda + firmas del negocio) → **agente cognitivo** (IA: investiga con el skill) → **agente decisor** (IA: busca la explicación legítima, objeta y decide) → **compuerta** (código: la banda nunca baja; lo grave lo firma una persona) → bandeja del analista (`POST /api/ingest`) + feedback a ML (`POST /feedback`).
