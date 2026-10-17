# Demo: el agente aprende

Cuatro transacciones de cuentas reales (SAML-D, historial jul–ago 2023), listas en `C:/hk/casos_jurado/`. Cada una muestra una cosa distinta: cierre automático, memoria de la cuenta, alta prioridad y un umbral que el agente aprende a ajustar.

Medidas el 17/10/2026 con `POST /score/live` (sin IA, no guarda nada en ML) y el evaluador en código (`lib/aml-evaluador.js` con `skill/limites.json`). El script que las buscó es `C:/hk/buscar-perfiles.js` (usó 33 de 40 llamadas).

## Los 4 perfiles

| Perfil | Archivo | Qué muestra | Banda ML | p_laundering | Firmas en código | Qué se espera del agente |
|---|---|---|---|---|---|---|
| 1 Cierre | `perfil_1_cierre.json` | Retiro de 140,50 a su contraparte de siempre (ratio 0,04 de su media) | auto_close_eligible | 0,000002 | ninguna; sin señales extremas | Ruta **auto**: cierra sin IA (`decision auto_closed`), en milisegundos |
| 2 Comportamiento | `perfil_2_comportamiento.json` | Débito de 12 500 a una contraparte **nueva**, 4 veces su media (z 1,76) | review | 0,5175 | **F-behavioural-1** (contraparte nueva + salto de monto) | Pasa al agente; familia behavioural; escala al analista. La cuenta 6324740324 ya tiene dictamen (C-6324740324-2023-07-28), así que la memoria trae antecedentes |
| 3 Prioridad | `perfil_3_prioridad.json` | Tarjeta de crédito de 9 000 a contraparte nueva | high_priority | 0,9953 | ninguna (el riesgo lo pone el modelo) | Pasa al agente; alta prioridad / retención preventiva; el agente debe decir que el código no encontró firma que respalde la familia |
| 4 Aprendizaje | `perfil_4_aprendizaje.json` | ACH de 9 924,40 a contraparte nueva, **2,60** veces su media (z 1,11) | review | 0,3820 | ninguna: F-behavioural-1 queda **justo por debajo** (umbral `s_amt_ratio_mean_30d_min` = 3,0; valor 2,60, un 13 % menos) | 1.ª vez: sin firma. Tras aprobar 3,0 → 2,5 (un 16,7 %, dentro del tope del 25 %): **la firma se dispara** y `context.aml.aprendizaje` dice qué cambió |

Variable y umbral del perfil 4 en `skill/limites.json`: `firmas["F-behavioural-1"].umbrales.s_amt_ratio_mean_30d_min` (hoy 3.0). El otro camino de la firma (`s_amt_z_30d_min` = 2,5) no se acerca (z = 1,11).

## Guion de la demo

Antes: `skill/limites.json` sin `historial_aprendizaje` (parámetros iniciales). Bandeja abierta en el navegador.

1. **Cierre automático.** Ejecuta `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_1_cierre.json`.
   - En la terminal, el jurado ve: banda auto_close_eligible, "Firmas disparadas: ninguna", decisión auto_closed y tiempos de IA en 0 ms.
   - En la bandeja (busca `jurado`): el caso aparece cerrado. Mensaje: "lo de bajo riesgo no gasta IA".
2. **Alta prioridad.** Ejecuta `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_3_prioridad.json`.
   - El jurado ve: banda high_priority (p 0,995), el agente decide y propone retención.
   - Pasos: evaluador → cognitivo → contexto → memoria → decisor → compuerta.
3. **Comportamiento + memoria (1.ª vez).** Ejecuta `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_2_comportamiento.json`.
   - El jurado ve: firma F-behavioural-1 disparada, con evidencia (contraparte nueva, monto 4 veces la media).
   - En la bandeja, `context.aml.aprendizaje.casos_previos` ≥ 1 y `aprendio` dice "Usó N decisiones previas sobre la cuenta …".
4. **Perfil 4, antes de aprender.** Ejecuta `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_4_aprendizaje.json`.
   - El jurado ve: "Firmas disparadas: ninguna", aunque el monto es 2,6 veces lo normal y va a una contraparte nueva.
   - Mensaje: "la regla de negocio exige 3 veces; este caso queda en zona gris".
5. **El agente revisa sus casos.** Ejecuta `node C:/hk/hk-aprender.js`. Hace **una** llamada a la IA y gasta plan.
   - Se escriben `reportes/aprendizaje.md` y `aprendizaje.json`; ábrelos y muestra la tabla de propuestas.
   - Cada propuesta trae id, valor actual, valor propuesto, motivo y los casos que la respaldan.
   - La compuerta en código descarta lo que cambie más del 25 % o cite casos que no existen.
6. **Aprobar la propuesta.** Busca la propuesta de `F-behavioural-1 · s_amt_ratio_mean_30d_min` y ejecuta `node C:/hk/hk-aprender.js aprobar <id> --confirmo`.
   - En la terminal: "Aplicada F-behavioural-1.s_amt_ratio_mean_30d_min: 3 → 2.5. Respaldo en skill/historial/…".
   - Mensaje: "un humano aprueba; queda respaldo y traza".
7. **Volver a sellar el skill.** Ejecuta `node C:/hk/hk.js aprobar-skill --confirmo`. Sin este paso, el agente se niega a analizar porque `limites.json` cambió.
8. **Perfil 4, después de aprender.** Ejecuta otra vez `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_4_aprendizaje.json`. Es la misma transacción.
   - Ahora sale "Firmas disparadas: F-behavioural-1".
   - En la bandeja, `context.aml.aprendizaje` muestra:
     - `cambios_aplicados`: firma, variable, antes 3, después 2,5 y fecha;
     - `version_parametros`: un sha distinto al del paso 4;
     - `aprendio`: "… la firma F-behavioural-1 con el umbral ajustado el dd/mm (3 → 2,5)".
   - Se comparan los dos eventos `jurado` del perfil 4, uno al lado del otro.
9. **Memoria (2.ª vez).** Ejecuta de nuevo `node C:/hk/hk-jurado.js --enviar --archivo C:/hk/casos_jurado/perfil_2_comportamiento.json`.
   - `casos_previos` sube en 1 (ahora cuenta el dictamen del paso 3).
   - `memoria_cuenta` lista esa decisión previa con su fecha y resumen, y el decisor la recibe como antecedente.

En lugar de `node C:/hk/hk-jurado.js --enviar …` también sirve doble clic en `C:/hk/PROBAR_CASO.cmd`, que pregunta los datos uno por uno. En ese caso se copian los valores del JSON y la fecha `ts` queda la del sistema, no la del archivo. Para el perfil 4 usa siempre `--archivo`.

## Riesgos de la demo

- **La propuesta del paso 6 la redacta la IA y puede no salir igual.** Si no propone `F-behavioural-1.s_amt_ratio_mean_30d_min` con un valor ≤ 2,60, la firma no se dispara en el paso 8.
  - Prepáralo antes con un ensayo. Los pasos 1–4 dejan dictámenes que respaldan la propuesta: el perfil 4 escaló sin firma con ratio 2,6.
  - Hoy no existe un comando para cargar una propuesta a mano.
- Los perfiles 2 y 4 comparten la receptora 980501511 (que también está en C-3049253016). Por eso el perfil 4 también muestra antecedentes.
- Al terminar, para volver al estado inicial: copia el respaldo de `skill/historial/limites-….json` sobre `skill/limites.json` y vuelve a ejecutar `node C:/hk/hk.js aprobar-skill --confirmo`.
- Cada análisis de los perfiles 2, 3 y 4 hace dos llamadas a la IA (cognitivo y decisor). El perfil 1 no gasta IA. Revisa el tope diario (HK_TOPE_DIA, 40 por defecto).
