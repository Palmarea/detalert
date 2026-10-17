# Cómo mejoramos el skill AML

Para el equipo de negocio que escribió SKILL.md y matriz.md. Todo sale de 14 casos ya dictaminados: 11 del banco y 3 de prueba cargados a mano. No hay datos inventados.

---

## 1. Resumen

- Solo 4 de las 10 firmas se dispararon en los 14 casos; las 6 de capas, efectivo y concentración no se dispararon nunca.
- Tuvimos que resolver en limites.json 7 choques entre el skill, la matriz y el contrato de la API; proponemos una redacción nueva para cada uno.
- Varias firmas no pueden decidir bien con las 18 variables de hoy: necesitan 6 columnas nuevas de ML, y el ajuste fino de umbrales necesita que los analistas registren su resolución (hoy hay 0 resoluciones).

---

## 2. Qué pasó con cada firma en 14 casos

"Más cerca del umbral" = el caso que estuvo más cerca de dispararla, con sus valores reales.

| Firma | Veces | Más cerca del umbral (valores observados) | Qué sugiere |
|---|---|---|---|
| F-behavioural-1 Contraparte nueva + salto de monto | 3 | Se disparó con ratio 7,71 / z 4,90; ratio 6,89 / z 6,47; y ratio 3,57 / z 2,26 (este último entró solo por el ratio, apenas sobre 3,0). El siguiente caso más alto tuvo ratio 1,39. | Mantener. Separa bien: los que entran están lejos de los que no. |
| F-behavioural-2 Cuenta dormida | 2 | Las 2 entraron por horas sin enviar (810 h y 3.888 h), con 0 envíos en 30 días. Por la otra vía (envíos 7d / 30d ≥ 0,85) el valor más alto fue 0,41: nadie se acercó. En los 3 casos de prueba no hay historial y la firma no sabe qué hacer. | Depende de una variable que no existe: antigüedad de la cuenta. Hay que distinguir "dormida" de "nueva". |
| F-structuring-1 Pitufeo en pareja | 1 | Se disparó con un retiro de 84,04 (no está cerca de 8.000) porque el acumulado de 7 días era 32.643. El caso terminó cerrado como normal. El único monto en la franja 8.000–9.999 de un caso del banco (8.849) no tenía envíos previos al mismo par. | Volver al "Y" del skill: monto en la franja **y** acumulado alto. El "O" de la matriz dio un falso positivo. |
| F-structuring-2 Abanico inferido | 2 | Entraron con 10 envíos en 1,7 h y 5 envíos en 5,7 h (justo bajo el tope de 6 h). Quedó fuera uno con 6 envíos pero 19,9 h desde el anterior, y otro con 0,6 h pero solo 4 envíos. En un caso disparado, el analista objetó que 5 envíos en 7 días contra 29 en 30 días es la cadencia normal del cliente. | Depende de una variable que no existe: receptores distintos del emisor. Mientras no llegue, pedir además que la semana sea una ráfaga frente al mes. |
| F-concentration-1 Fan-in acelerado | 0 | Un caso de prioridad alta cumplía todo (6 emisores distintos en 7 días, ratio 7d/30d de 0,86, contraparte nueva) salvo la rapidez: 20,4 h contra el máximo de 4 h. | Revisar el tope de 4 h. Con un solo caso no alcanza para cambiarlo (mínimo 5). |
| F-layering-1 Emisor puente | 0 | El más cercano: 2 entradas en 7 días, salida/entrada 1,26 (tope 1,15), 0,6 h, pero el receptor no reenvió nada (0 contra mínimo 2). | Sin datos para mover. Falla en dos condiciones a la vez. |
| F-layering-2 Receptor mula | 0 | Un receptor con 4 reenvíos no tenía emisores en 7 días; otro con 6 emisores reenvió solo 2 veces y a las 20,4 h. | Depende de una variable que no existe: cuánto dinero reenvía el receptor. Contar reenvíos no basta. |
| F-layering-3 Fricción internacional | 0 | El único pago transfronterizo: cambio de moneda sí, contraparte nueva sí, ratio de monto 1,09 (mínimo 2,5). La otra vía de la matriz (bancos en países distintos) no se pudo evaluar. | Depende de una variable que no existe: ubicación de los bancos. |
| F-cash-1 Depósito y giro | 0 | El más cercano: 3 operaciones en efectivo, 1 entrada, salida/entrada 14,6, pero 33,9 h desde el envío anterior (máximo 24 h). | Sin datos para mover. Un caso no alcanza. |
| F-cash-2 Uso intensivo de efectivo | 0 | Dos retiros con 9 y 5 operaciones en efectivo en 30 días, pero 0 entradas en 7 días y monto normal. Un depósito de 31.428,9 con z 6,47 no entró porque era la primera operación en efectivo del cliente (el conteo solo mira el pasado). | Depende de una variable que no existe: monto en efectivo y si la operación actual es en efectivo. Hoy un depósito grande "primerizo" se escapa. |

Otros datos de los 14 casos:

- Decisiones: 4 cerradas automáticamente, 7 escaladas al analista, 3 en prioridad alta.
- El agente usó REJECT 1 vez; en los otros 2 casos de prioridad alta pidió investigar.
- Consultas pedidas: receptores del emisor en 7 días (4 casos) y contrapartes de 90 días (4 casos). Las salidas del receptor y el subgrafo de 2–3 saltos no se pidieron nunca.
- Familia: el agente cambió la familia de la API en los 14 casos. En ninguno coincidieron. Los 3 casos que la API marcó como cash quedaron como normal; de los 6 marcados como structuring, 3 quedaron como behavioural y 3 como generic.
- Propuestas automáticas de ajuste: 0. Ninguna firma llegó a 5 casos y no hay resoluciones de analistas.

---

## 3. Contradicciones que resolvimos en código

Para cada una: qué choca, qué hicimos y la redacción que proponemos para el skill.

**1. APPROVE en banda review.**
- Choque: el skill (§5) permite aprobar en review si las variables se ven legítimas. La API solo deja cerrar solo al agente lo que viene en auto_close_eligible.
- Qué hicimos: APPROVE cierra solo si la banda es auto_close_eligible. En review se escala, con la nota "el agente recomienda aprobar; lo decide el analista".
- Redacción nueva: "APPROVE cierra el caso solo en banda auto_close_eligible. En review, el agente puede recomendar aprobar, pero el caso va al analista."

**2. REJECT, que el agente no puede usar.**
- Choque: el skill y la matriz piden REJECT. La API no tiene "rechazado" para el agente: sus decisiones son cerrar, escalar o prioridad alta. "Rechazado" y "reporte de operación sospechosa" son decisiones del analista.
- Qué hicimos: REJECT se traduce en prioridad alta con retención preventiva. El analista ratifica.
- Redacción nueva: "Cuando hay convergencia clara, el agente retiene y sube a prioridad alta. El rechazo y el reporte los decide el analista."

**3. Umbral de cierre: 0,02 contra 0,0024.**
- Choque: la matriz (§2) pone como ejemplo de cierre p_laundering ≤ 0,02. El umbral real de la API es 0,002355 (0,006996 si el equipo trabaja con capacidad reducida). Entre 0,0024 y 0,02 la API dice review, no cierre. El umbral de prioridad alta es 0,775.
- Qué hicimos: manda la banda de la API.
- Redacción nueva: "El cierre lo define la banda que entrega la API, no un número fijo. El skill no repite umbrales de probabilidad."

**4. Family "de mentira" contra el 81 % de la guía.**
- Choque: el skill dice que la familia de la API es un valor de prueba y que no hay que creerle. La guía de la API dice que es una sugerencia con 81 % de acierto en prueba, y que concentration y layering se confunden entre sí.
- Qué hicimos: el agente la audita igual. En los 14 casos la cambió.
- Redacción nueva: "La familia de la API es una sugerencia (81 % de acierto en prueba). Se cambia solo si se dispara una firma de otra familia. Si ninguna firma se dispara, se conserva y se marca como no confirmada. Entre concentration y layering, mirar siempre las dos."

**5. F-layering-3 usa la ubicación de los bancos.**
- Choque: la matriz acepta "bancos en países distintos" como alternativa al salto de monto. Ese dato no viene en las 18 variables ni en lo que entrega la API.
- Qué hicimos: solo cuenta el ratio de monto ≥ 2,5.
- Redacción nueva: "Fricción internacional: Cross-border + cambio de moneda + contraparte nueva + ratio ≥ 2,5. La condición de bancos distintos se activa cuando ML entregue esa columna."

**6. Umbrales distintos entre skill y matriz (lista de limites.json).**
- Regla general que aplicamos: manda la matriz, porque dice que actualiza al skill.

| Firma | Skill | Matriz (lo que usamos) | Redacción nueva propuesta |
|---|---|---|---|
| F-behavioural-2 | envíos 7d/30d ≥ 0,80 | ≥ 0,85, con 4 envíos mínimo y contraparte nueva o cambio de moneda | Dejar solo la de la matriz en ambos documentos. |
| F-structuring-1 | monto 8.000–9.999 **y** acumulado ≥ 10.000 | uno **o** el otro | Volver al "y" (ver tabla 2: el "o" disparó con un retiro de 84). |
| F-structuring-2 | par/envíos ≤ 0,25, ≤ 12 h | ≤ 0,20, ≤ 6 h | Dejar la de la matriz. Además, cambiar "pair_cnt_7d = 1" por "pair_cnt_7d ≤ 1": con contraparte nueva el valor es siempre 0, así que "= 1 y contraparte nueva" nunca se cumple a la vez. |
| F-concentration-1 | 5 emisores **o** ratio ≥ 0,70, ≤ 6 h | ambos, ≤ 4 h | Dejar la de la matriz y revisar las 4 h cuando haya 5 casos. |
| F-layering-1 | salida/entrada 0,80–1,20, ≤ 12 h | 0,85–1,15, ≤ 6 h y receptor con 2 reenvíos | Dejar la de la matriz. |
| F-layering-2 | receptor ≤ 6 h | ≤ 4 h | Dejar la de la matriz. |
| F-cash-1 | salida/entrada 0,80–1,15 | ≥ 0,80 sin tope | Dejar la de la matriz. |
| F-cash-2 | retiro con 2 entradas, o depósito con 4 en efectivo y ≤ 24 h | retiro o depósito con 5 en efectivo y (3 entradas o z ≥ 2,5) | Dejar la de la matriz. |

- F-behavioural-1 no choca: la matriz define un caso más estrecho (vaciado) y lo informamos como variante.
- Propuesta de forma: que la matriz sea el único lugar con números y que el skill remita a ella. Así no vuelven a separarse.

---

## 4. Firmas que necesitan columnas nuevas de ML

| Firma | Columna que falta | Cómo cambiaría la regla |
|---|---|---|
| F-structuring-2 (abanico) | Receptores distintos del emisor en 7 y 30 días | Se mide el abanico directamente: muchos receptores distintos en 7 días, frente a lo habitual del mes. Se deja de adivinar con pair_cnt_7d. Hoy esta consulta se pide en 4 de 14 casos. |
| F-layering-2 (mula) | Monto que reenvía el receptor en 7 días, y monto que recibe | Mula = reenvía al menos el 80 % de lo que recibió en poco tiempo. Contar reenvíos no distingue a un comercio de una mula. |
| Desambiguación en review (consulta 4) | Historial de 90 días con la contraparte: envíos y monto promedio del par | Separa los normales (pago único grande, periódico, mutuo) sin pedir consulta extra. Hoy se pide en 4 de 14 casos. |
| F-layering-3 (internacional) | País del banco emisor y del receptor (o un sí/no "bancos en países distintos") | Se activa la condición de la matriz que hoy no se puede evaluar. |
| F-behavioural-2 (dormida) | Antigüedad de la cuenta (días desde su primera operación) | Separa "dormida que despierta" de "cuenta nueva sin historial". Hoy los dos casos se ven iguales. |
| F-cash-2 (efectivo) | Monto en efectivo del emisor en 30 días, contando la operación actual | Un depósito grande en efectivo deja de escaparse por ser el primero. Un caso real de 31.428,9 se escapó así. |
| Ciclo en layering (consulta 3) | Envíos previos del receptor hacia el emisor en 30 días | Detecta la vuelta del dinero sin pedir el subgrafo, que nunca se pidió en 14 casos. |

---

## 5. Cómo se aplican los cambios

1. **El agente de aprendizaje propone.** Revisa los casos y sugiere ajustes de umbral con su motivo y los casos que lo sostienen.
2. **Con límites.** Ninguna propuesta mueve un umbral más de 25 %. Ninguna sale con menos de 5 casos.
3. **Negocio aprueba.** Cada propuesta se aprueba o se descarta una por una. Las redacciones nuevas de la sección 3 también pasan por negocio.
4. **El skill se versiona.** Cada cambio aprobado crea una versión nueva de SKILL.md, matriz.md y limites.json (hoy: binary_v1-limites-1). Cada dictamen guarda con qué versión se hizo.
5. **Nada cambia solo.** Sin aprobación, el agente sigue con la versión vigente.

Lo que más destraba el aprendizaje: que los analistas registren su resolución en cada caso escalado (aprobado, rechazado o reporte). Sin eso no se puede medir si el agente acierta, y los umbrales solo se pueden mover por frecuencia, no por acierto.
