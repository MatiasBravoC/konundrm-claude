# Flujo más eficiente: una sesión por slice, un check por tarea y revisiones en paralelo

- **Spec:** 002-efficient-feature-flow
- **Status:** Approved <!-- Draft → Approved → Done -->
- **Date:** 2026-10-30

## Problem

La corrida que construyó la 0.6.0 (80 tareas, 5 sesiones, 380 subagentes) muestra dónde se van el
tiempo y los tokens. Los orquestadores gastaron el 57% de los tokens ponderados por precio porque
cada turno relee toda la conversación: la sesión principal releyó una mediana de 382k tokens en
cada uno de sus 1.087 turnos, y unas 300 de sus llamadas fueron consultas a Git. El check completo
corrió 290 veces (5,7 h, ~70 s cada una), sobre todo porque el implementer y el gate lo repiten en
cada tarea, y el test-writer y los revisores lo corrieron 46 veces más. Las 221 revisiones
corrieron una tras otra, cada comando de shell paga ~0,65 s de hooks y no hay forma de medir una
corrida sin scripts hechos a mano.

## Goals

- Que el costo de cada turno del orquestador no crezca con la feature: contexto limpio en cada
  slice y menos turnos de contabilidad.
- Un solo check completo por tarea cuando nada cambió desde que pasó.
- Que la espera por las revisiones de una tarea sea la de la más lenta, no la suma.
- Bajar el costo fijo de los hooks por comando sin debilitar el gate de commit.
- Medir cada corrida (tokens, tiempo, checks y despachos por rol) y entregar un diagnóstico de lo
  ganado frente a la 0.6.0.
- Mantener las garantías de cada tarea: test en rojo, cinco corridas verdes, revisiones de spec y
  de código sobre su código final, check verde y un commit.

## Non-goals

- Tareas más grandes o revisiones por lote (opción 6 del análisis): queda para probar aparte.
- Cambiar el modelo o el esfuerzo de algún rol, recortar las skills precargadas o fusionar
  test-writer e implementer.
- Correr en paralelo los verificadores de hallazgos o a quienes escriben código: siguen de a uno.
- Cambiar qué inspecciona el gate de commit o cómo falla: sigue revisando cada comando y fallando
  cerrado.
- Cambiar el esfuerzo de la sesión automáticamente.
- Nuevas evaluaciones de comportamiento (con modelo).
- Medir lo ganado en una feature real construida con el flujo nuevo: eso pasa en la próxima
  feature, con la medición que agrega esta.
- Publicar el plugin, hacer push o tocar proyectos que lo usan.

## User stories and acceptance criteria

### US1. Una sesión de orquestador por slice

Como desarrollador, quiero que cada slice lo construya una sesión de orquestador con contexto
limpio, para que el costo de cada turno no crezca con la feature.

- `R1.1` WHEN termina la pausa de un slice (resumen commiteado, notas de mejora guardadas y, con
  pausas `ask`, el visto bueno del desarrollador) y queda otro slice o el cierre de la feature,
  THE SYSTEM SHALL seguir la feature en una sesión nueva que retoma desde el plan y el
  repositorio, en vez de seguir en la misma sesión.
- `R1.2` WHERE la sesión corre en la app de escritorio con herramientas para abrir sesiones en una
  carpeta existente, THE SYSTEM SHALL abrir esa sesión nueva en la misma carpeta con el comando
  que retoma la feature, y terminar el trabajo de la sesión actual en la feature.
- `R1.3` WHERE no hay esas herramientas, THE SYSTEM SHALL terminar con el comando exacto que
  retoma la feature en una sesión nueva.
- `R1.4` WHERE las pausas están preaprobadas y la feature corre desde una terminal, THE SYSTEM
  SHALL ofrecer un comando que construye la feature con una sesión no interactiva nueva por
  slice, en orden, hasta que la feature termina, una sesión se detiene con `BLOCKED:` o una sesión
  falla, y que dice cuál de las tres pasó.
- `R1.5` IF una sesión de ese comando termina sin agregar ningún commit, THEN THE SYSTEM SHALL
  detener el comando y decirlo, en vez de abrir otra sesión.
- `R1.6` IF hay cambios sin commitear al momento de pasar a la sesión nueva, THEN THE SYSTEM SHALL
  detenerse con una línea `BLOCKED:` que nombre esos archivos, sin abrir la sesión nueva.
- `R1.7` WHERE el desarrollador pidió construir la feature completa en una sola sesión (al pedirla,
  al aprobar el plan o en una pausa), THE SYSTEM SHALL construir el slice siguiente en la sesión
  actual.
- `R1.8` WHEN una sesión retoma una feature a medias, THE SYSTEM SHALL empezar por la primera tarea
  del plan sin commit, sin construir dos veces ninguna tarea ni saltarse ninguna, aunque las
  casillas de las tareas ya commiteadas sigan sin marcar.
- `R1.9` WHEN empieza una sesión, THE SYSTEM SHALL contar como hechas las tareas que tienen commit
  aunque su casilla siga sin marcar, y nombrar como próxima tarea de cada feature en curso la
  primera sin commit (con particiones en paralelo, la primera sin commit de cada partición de la
  ola en curso).

### US2. Un solo check completo por tarea

Como desarrollador, quiero que el check completo corra una vez por tarea salvo que algo cambie
después de pasar, para que la feature no espere horas por checks repetidos.

- `R2.1` THE SYSTEM SHALL hacer que el test-writer corra solo los tests que escribió o cambió,
  nunca el check completo ni la suite completa del proyecto.
- `R2.2` THE SYSTEM SHALL dar a los revisores de spec, de código y de seguridad la salida de las
  verificaciones que ya corrió el orquestador, y hacer que no corran el check completo ni la suite
  completa; si un hallazgo depende de ejecutar algo, corren solo ese test o una reproducción
  mínima.
- `R2.3` THE SYSTEM SHALL hacer que el verificador de hallazgos corra solo los tests o
  reproducciones que su hallazgo necesita, nunca el check completo.
- `R2.4` THE SYSTEM SHALL hacer que el implementer corra la suite completa solo dentro del check,
  una vez al final de cada despacho; antes, solo el test de la tarea y los tests del código que
  cambia.
- `R2.5` WHEN el último check completo de una tarea pasó sobre exactamente los archivos que se van
  a commitear, THE SYSTEM SHALL commitear la tarea sin volver a correr el check.
- `R2.6` IF algún archivo cambió después del último check que pasó (un test arreglado después del
  implementer, una evidencia, un informe de replanteo), THEN THE SYSTEM SHALL correr el check
  completo antes de commitear la tarea.
- `R2.7` THE SYSTEM SHALL registrar en el mensaje del commit de cada tarea su ID, los requisitos
  que cubre y sus rondas de revisión y escalamientos, y no marcar su casilla ni escribir sus rondas
  en el plan en ese commit.
- `R2.8` WHEN corre la pausa de un slice, THE SYSTEM SHALL marcar en el plan la casilla de cada
  tarea del slice que tiene commit y escribir sus rondas tomadas de ese commit, dentro del commit
  del resumen del slice.
- `R2.9` THE SYSTEM SHALL seguir informando las rondas de revisión por tarea en el informe de
  impacto, tanto en planes que las registran por tarea (escritos antes de este cambio) como en los
  que las registran por slice.

### US3. Revisiones en paralelo

Como desarrollador, quiero que las revisiones de solo lectura de una tarea corran al mismo tiempo,
para esperar solo la más lenta.

- `R3.1` WHEN una tarea termina su verificación (cinco corridas verdes, o la verificación única de
  una tarea `chore`), THE SYSTEM SHALL lanzar al mismo tiempo la revisión de spec y la de código
  y, en una tarea de riesgo alto, también la de seguridad.
- `R3.2` WHEN una o más de esas revisiones reportan hallazgos, THE SYSTEM SHALL enviarlos todos en
  una sola ronda de arreglo antes de revisar de nuevo.
- `R3.3` WHEN una revisión corre de nuevo después de una ronda de arreglo, THE SYSTEM SHALL darle
  sus hallazgos anteriores y los cambios hechos desde que corrió, para que revise eso en vez de
  toda la tarea.
- `R3.4` THE SYSTEM SHALL commitear una tarea solo cuando su revisión de spec y su revisión de
  código (y la de seguridad en riesgo alto) pasaron con su código final.
- `R3.5` WHILE corre algún revisor, THE SYSTEM SHALL no correr ningún test-writer ni implementer
  en el mismo árbol de trabajo.
- `R3.6` IF un revisor cambia un archivo mientras otros revisores corren, THEN THE SYSTEM SHALL
  detectarlo y restaurarlo como hoy, terminen los revisores en el orden que terminen.

### US4. Contabilidad en una sola llamada

Como autor del plugin, quiero que la contabilidad determinista del flujo la hagan comandos del
plugin en una llamada, para que los turnos del orquestador, que releen todo su contexto, se usen en
decisiones y no en consultas a Git.

- `R4.1` THE SYSTEM SHALL ofrecer un comando que muestra en una llamada, para una feature: la
  próxima tarea (o la de cada partición de la ola en curso), qué tareas tienen commit, si el árbol
  de trabajo está limpio y si hay un check que pasó registrado para el árbol actual.
- `R4.2` THE SYSTEM SHALL ofrecer un comando que arma en una llamada el mensaje del commit de una
  tarea con sus líneas de tarea, requisitos y rondas, para commitearla en una sola llamada.
- `R4.3` THE SYSTEM SHALL hacer que todo commit de tarea pase por el gate de commit como cualquier
  otro commit.
- `R4.4` IF la tarea no existe en el plan o ya tiene commit, THEN THE SYSTEM SHALL rechazar armar
  su mensaje, con el motivo y sin cambiar nada.
- `R4.5` THE SYSTEM SHALL ofrecer un comando que hace en una llamada la contabilidad de la pausa de
  un slice descrita en `R2.8`.
- `R4.6` IF el plan no existe o no se puede leer, THEN THE SYSTEM SHALL decir qué archivo y qué
  línea fallaron y terminar con error sin cambiar nada.
- `R4.7` WHEN el orquestador necesita el estado de la feature entre tareas, o commitear una tarea,
  THE SYSTEM SHALL usar esos comandos en vez de llamadas separadas a Git.

### US5. Hooks más baratos por comando

Como desarrollador, quiero que los hooks que corren en cada comando cuesten menos, sin perder
controles.

- `R5.1` WHEN termina un comando de shell que no es el check del proyecto, THE SYSTEM SHALL no
  arrancar el intérprete de Python para el hook que registra los resultados del check.
- `R5.2` WHEN el check del proyecto termina bien, THE SYSTEM SHALL registrar su resultado como
  hoy, también cuando el check es un comando propio configurado por variable de entorno.
- `R5.3` IF el hook no puede saber si el comando es el check, THEN THE SYSTEM SHALL correr el
  registro completo, nunca saltarlo.
- `R5.4` THE SYSTEM SHALL mantener sin cambios lo que el gate de commit y el guard de dependencias
  inspeccionan en cada comando, y que el gate siga fallando cerrado.

### US6. Medir una corrida

Como autor del plugin, quiero medir una corrida desde sus transcripciones, para comparar el flujo
antes y después de cada cambio con datos y no con impresiones.

- `R6.1` THE SYSTEM SHALL ofrecer un comando que, para una o más carpetas de transcripciones de
  sesión, informa por rol (orquestador y cada tipo de subagente): despachos, turnos, tokens de
  entrada, de escritura y de lectura de caché y de salida, tokens equivalentes de entrada (pesos 1;
  1,25; 0,1 y 5), su parte del total, minutos activos (mediana y total, sin contar pausas de más de
  5 minutos), corridas del check completo con su tiempo total, corridas de tests y mensajes con dos
  o más despachos en paralelo.
- `R6.2` THE SYSTEM SHALL informar, para la sesión de orquestador con más turnos, sus turnos y su
  contexto por turno: el primero, la mediana, el percentil 90 y el máximo.
- `R6.3` THE SYSTEM SHALL mostrar solo conteos, tiempos y totales de tokens, nunca el contenido de
  mensajes, comandos ni resultados.
- `R6.4` IF una línea de una transcripción no es JSON válido o le faltan campos, THEN THE SYSTEM
  SHALL saltarla y contar las saltadas en el informe.
- `R6.5` THE SYSTEM SHALL leer transcripciones cuya ruta supera los 260 caracteres en Windows.
- `R6.6` WHEN se pide el informe de impacto de un proyecto indicando dónde están sus
  transcripciones, THE SYSTEM SHALL incluir este informe junto al de entrega.

### US7. Acuerdos protegidos y documentados

Como autor del plugin, quiero que cada acuerdo nuevo quede protegido por pruebas y documentado,
para que no se pierda en la próxima versión.

- `R7.1` THE SYSTEM SHALL comprobar dentro del check del proyecto cada acuerdo de esta feature que
  se puede comprobar sin un modelo: las instrucciones de cada rol, cada paso nuevo del flujo, los
  comandos nuevos y el hook.
- `R7.2` THE SYSTEM SHALL publicar estos cambios como versión 0.7.0, con su changelog y con el
  README describiendo el flujo nuevo, cómo encadenar sesiones y cómo medir una corrida.

## Constraints

- Los hooks y los comandos nuevos usan solo la librería estándar de Python 3.10+ y corren en
  Windows, macOS y Linux; el lanzador de hooks usa solo builtins de shell en su camino rápido.
- Los planes escritos con la 0.6.0 (casillas y rondas por tarea) siguen funcionando: la
  reanudación, el arranque de sesión y el informe de impacto leen los dos formatos.
- El comando de estado responde en menos de 2 s con un plan de 100 tareas en esta máquina
  (Windows 11).
- Para un comando que no es el check, el hook que registra checks tarda en promedio menos de la
  mitad que hoy (305 ms medidos el 2026-10-30 en esta máquina).
- La medición procesa una transcripción de 40 MB en menos de 30 s.
- Ningún rol cambia de modelo ni de esfuerzo.

## Final verification

1. `npm run check` pasa con los tests nuevos y `claude plugin validate ./plugins/konundrm-eng`
   pasa.
2. En un repositorio de prueba con un plan de dos slices: el comando de estado nombra la próxima
   tarea correcta con tareas commiteadas y casillas sin marcar; el comando de mensaje rechaza una
   tarea inexistente o ya commiteada; la contabilidad de la pausa marca las casillas y escribe las
   rondas tomadas de los commits; y el comando que encadena sesiones, con un `claude` de prueba, se
   detiene al terminar, ante un `BLOCKED:`, ante una falla y ante una sesión sin commits.
3. El hook que registra checks, corrido 20 veces sobre un comando que no es el check, tarda en
   promedio menos de la mitad que en la 0.6.0, y sobre `npm run check` sigue registrando el
   resultado.
4. La medición, sobre las transcripciones de la corrida de la 0.6.0, reproduce la línea base:
   orquestadores ~57% de los tokens ponderados, 290 checks completos y ~5,7 h de check.
5. El diagnóstico (`specs/002-efficient-feature-flow/evidence/diagnosis.md`) compara la 0.6.0 con
   el flujo nuevo: lo medido (hooks), lo prescrito por tarea (checks completos, despachos,
   revisiones en serie o en paralelo, llamadas de contabilidad) y una estimación de la corrida de
   la 0.6.0 con las reglas nuevas, y dice qué se confirmará con la medición en la próxima feature.
6. En la próxima feature (fuera de esta corrida): con pausas preaprobadas y dos slices, el segundo
   slice corre en una sesión nueva, cada commit de tarea lleva sus rondas, el commit del resumen
   marca las casillas y la medición muestra revisiones en paralelo y un check completo por tarea.

## Open questions

<!-- Use [NEEDS CLARIFICATION: …] inline above. This section must be empty before approval. -->
