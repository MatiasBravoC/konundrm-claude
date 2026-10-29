# Entrega guiada por slices, con particiones en paralelo

- **Spec:** 001-guided-slice-delivery
- **Status:** Approved <!-- Draft → Approved → Done -->
- **Date:** 2026-10-29

## Problem

En IAdrivers, una feature de 61 tareas corrió unos tres días en una sola sesión, con la sesión y
todos los subagentes en Opus 5.5 con esfuerzo max (unos US$1.300 a precio de API). Al final, el
desarrollador tenía miles de líneas que no había seguido y no podía entender de una vez. El
borrador 0.6.0 resolvía parte del costo y la velocidad, pero con una sola pull request por
feature la etiqueta `risk:high` pasaba a cubrir todo el código. Las mejoras al plugin que
aparecen en cada flujo se anotan a mano o se pierden.

## Goals

- Gastar el esfuerzo del modelo donde rinde: cada rol con su modelo y esfuerzo, y más solo para
  arreglos, tareas de riesgo alto y tareas trabadas.
- Bajar el tiempo de una feature construyendo en paralelo las partes independientes de cada slice.
- Que el desarrollador entienda cada slice antes del siguiente: pausa, resumen, preguntas y
  decisiones tomadas con él.
- Revisiones chicas: una pull request apilada por slice, con la opción de juntar todo en una.
- Que el plugin mejore con el tiempo a partir de notas registradas en cada flujo.
- Que cada acuerdo quede protegido por pruebas automáticas.

## Non-goals

- Limitar el mutation testing del CI a los archivos de las tareas de riesgo alto.
- Juntar en `measure-impact` los eventos de los gates de las sesiones paralelas.
- Correr las evaluaciones de comportamiento (con modelo) dentro del check o del CI.
- Editar el plugin automáticamente a partir de las notas de mejora.
- Tareas que escribe el propio desarrollador, bitácora por tarea, recorrido del diff y alertas de
  tamaño aparte del resumen: no se eligieron para esta iteración.
- Publicar el plugin, hacer push o tocar proyectos que usan el plugin.

## User stories and acceptance criteria

### US1. Modelo y esfuerzo por rol

Como autor del plugin, quiero que cada rol corra con un modelo y un esfuerzo acordados, para
mantener la calidad donde importa sin gastar esfuerzo max en todo.

- `R1.1` THE SYSTEM SHALL correr cada rol con este modelo y esfuerzo por defecto, sea cual sea el
  de la sesión: test-writer Opus medium, implementer Opus medium, spec-reviewer Sonnet high,
  code-reviewer Opus high, security-reviewer Opus xhigh, finding-verifier Opus high, rethinker
  Opus max y agente de notas de mejora Sonnet high.
- `R1.2` WHEN una tarea necesita una ronda de arreglo (una revisión fallida, un hallazgo Critical
  que sobrevivió a su verificación, un test que falla por la razón equivocada, una corrida
  inestable o un check en rojo), THE SYSTEM SHALL correr el test-writer o el implementer de esa
  ronda en Opus con esfuerzo high.
- `R1.3` WHEN una tarea es de riesgo alto, THE SYSTEM SHALL correr su test-writer, su implementer
  y su revisión de spec en Opus con esfuerzo high.
- `R1.4` WHEN la revisión de spec cubre una feature completa o una pull request completa, THE
  SYSTEM SHALL correrla en Opus con esfuerzo high.
- `R1.5` WHILE se escribe el plan, THE SYSTEM SHALL usar esfuerzo xhigh y volver al esfuerzo de
  la sesión al terminar.
- `R1.6` THE SYSTEM SHALL declarar modelo o esfuerzo solo en los agentes y en la skill de
  planificación, para no cambiar de modelo ni de esfuerzo a mitad de una sesión larga.
- `R1.7` WHEN corre la revisión automática de pull requests en el CI del proyecto, THE SYSTEM
  SHALL usar Opus 5.5 con esfuerzo medium.

### US2. Slices con pull requests apiladas y opción de una sola

Como desarrollador, quiero la feature cortada en slices, cada uno con su pull request, y poder
juntar todo en una al final, para revisar en partes chicas y que `risk:high` solo cubra lo que
lo necesita.

- `R2.1` THE SYSTEM SHALL agrupar las tareas del plan en slices; cada slice es una pull request
  que se integra sola, deja la rama principal en verde y cabe en el presupuesto de líneas.
- `R2.2` WHEN la feature termina y el usuario aprueba subir los cambios, THE SYSTEM SHALL ofrecer
  dos entregas: una pull request apilada por slice (por defecto) o una sola pull request con
  todos los slices.
- `R2.3` WHERE el usuario elige pull requests apiladas, THE SYSTEM SHALL poner `risk:high` solo en
  las pull requests cuyo slice tiene una tarea de riesgo alto.
- `R2.4` IF el usuario elige una sola pull request y alguna tarea es de riesgo alto, THEN THE
  SYSTEM SHALL avisar antes de abrirla que `risk:high` cubrirá toda la feature, y SHALL correr
  antes en local el mutation testing de todo el código cambiado cuando la herramienta funciona en
  la máquina.
- `R2.5` THE SYSTEM SHALL listar en la descripción de cada pull request sus commits en orden, cada
  uno con el ID de su tarea.
- `R2.6` IF se retoma un plan escrito con una versión anterior (slices sin particiones), THEN THE
  SYSTEM SHALL construir sus slices uno tras otro, como antes.

### US3. Particiones dentro de cada slice, construidas en paralelo

Como desarrollador, quiero que las tareas de cada slice se partan en grupos independientes que
construyen sesiones en paralelo, para que una feature grande no tarde días en una sola sesión.

- `R3.1` THE SYSTEM SHALL partir las tareas de cada slice en particiones (grupos que construye una
  sesión, en orden) y ordenarlas en oleadas: dentro de una oleada, ninguna partición depende de
  otra ni comparte archivos con otra (salvo el plan y la evidencia), y hay a lo sumo tres
  particiones.
- `R3.2` WHEN se aprueba el plan y algún slice tiene una oleada de dos o más particiones, THE
  SYSTEM SHALL preguntar aparte si construirlas en paralelo, y SHALL ofrecerlo solo si los checks y
  las pruebas end-to-end de esas particiones pueden correr a la vez en la máquina; si no, SHALL
  decir por qué.
- `R3.3` WHEN el usuario acepta el paralelo, THE SYSTEM SHALL construir la primera partición de la
  oleada en la sesión principal y cada una de las demás en su propia sesión y worktree de Git
  fuera de la carpeta del proyecto, y SHALL integrarlas de a una en la rama de la feature,
  corriendo el check completo después de cada una.
- `R3.4` IF integrar una partición produce un conflicto fuera de las casillas del plan, THEN THE
  SYSTEM SHALL detenerse, informarlo y esperar al usuario antes de resolverlo.
- `R3.5` IF se retoma una sesión con una oleada sin terminar, THEN THE SYSTEM SHALL terminar esa
  oleada primero, decidir qué está integrado según el commit de cada tarea, reiniciar las
  sesiones de partición que ya no corren y nunca construir en la sesión principal tareas de otra
  partición.
- `R3.6` THE SYSTEM SHALL guardar la respuesta sobre el paralelo con la feature, para que una
  sesión retomada la conserve.
- `R3.7` WHILE corre una oleada en paralelo, THE SYSTEM SHALL mostrar al inicio de cada sesión la
  siguiente tarea de cada partición, en lugar de una sola siguiente tarea.
- `R3.8` THE SYSTEM SHALL aceptar rangos de tareas (por ejemplo `T1–T3`) al asignar tareas a una
  partición.

### US4. Pausa por slice con preguntas de comprensión

Como desarrollador, quiero que el flujo se detenga después de cada slice, me explique qué se
hizo y me haga algunas preguntas, para entender el código antes de que crezca.

- `R4.1` WHEN se commitea (y, con particiones, se integra) la última tarea de un slice, THE SYSTEM
  SHALL detenerse, mostrar el resumen del slice (US6) con qué leer primero y esperar el visto
  bueno del usuario antes de empezar el slice siguiente.
- `R4.2` WHEN se detiene después de un slice, THE SYSTEM SHALL hacer dos o tres preguntas cortas
  sobre el código del slice, cada una respondible con el resumen y los archivos que indica.
- `R4.3` WHEN el usuario responde mal o dice que no sabe, THE SYSTEM SHALL explicar la respuesta
  correcta con el archivo y las líneas que la muestran, sin condicionar el visto bueno a las
  respuestas.
- `R4.4` IF el usuario pide cambios en la pausa, THEN THE SYSTEM SHALL convertirlos en tareas
  nuevas o en un cambio de plan para aprobar antes de empezar el slice siguiente.
- `R4.5` WHERE el usuario aprobó de antemano las pausas (en el pedido o al aprobar el plan), THE
  SYSTEM SHALL escribir el resumen del slice y seguir sin detenerse ni preguntar.

### US5. Decisiones de diseño con el usuario

Como desarrollador, quiero elegir yo entre enfoques razonables, para que el diseño refleje mi
criterio.

- `R5.1` WHEN el plan identifica una tarea con dos o más enfoques razonables, THE SYSTEM SHALL
  mostrarlos al aprobar el plan, con sus ventajas, desventajas y una recomendación, para que el
  usuario elija.
- `R5.2` WHEN, durante la construcción, un subagente encuentra que una tarea admite dos o más
  enfoques razonables que el plan no decidió, THE SYSTEM SHALL pausar esa tarea, mostrar las
  opciones con sus ventajas, desventajas y una recomendación, y esperar la elección del usuario.
- `R5.3` WHERE el usuario aprobó de antemano las decisiones, THE SYSTEM SHALL tomar la opción
  recomendada y dejarla registrada en el resumen del slice.
- `R5.4` THE SYSTEM SHALL registrar cada decisión (opciones, elección y quién eligió) para que los
  resúmenes la citen.

### US6. Resumen por slice y resumen final de la feature

Como desarrollador y como revisor, quiero un resumen por slice y uno final de toda la feature,
para entender el trabajo sin leer miles de líneas de una vez.

- `R6.1` WHEN termina un slice, THE SYSTEM SHALL escribir su resumen: qué cambió y por qué,
  requisitos cubiertos, líneas cambiadas, riesgos y tareas de riesgo alto, decisiones tomadas,
  rondas de revisión y replanteos, y un orden de lectura sugerido con archivos y rangos de líneas.
- `R6.2` WHEN existe el resumen de un slice, THE SYSTEM SHALL usarlo en la descripción de la pull
  request de ese slice.
- `R6.3` WHEN termina la feature, THE SYSTEM SHALL escribir un resumen único que junte la spec, el
  diseño, los resúmenes de slice, las decisiones, la evidencia, los replanteos, los hallazgos
  refutados y las sugerencias no aplicadas, con cómo probar la feature, y SHALL enlazarlo desde
  la descripción de cada pull request.

### US7. Notas de mejora del plugin

Como autor del plugin, quiero un agente que anote posibles mejoras al plugin durante cada flujo,
para mejorarlo con el tiempo.

- `R7.1` WHEN termina un slice y WHEN termina la feature, THE SYSTEM SHALL pedir a un agente de
  solo lectura que revise el registro del flujo (rondas de revisión, escaladas, replanteos,
  subagentes bloqueados, eventos de los gates y correcciones del usuario) y proponga mejoras al
  plugin, cada una con su evidencia y la skill o el agente que toca.
- `R7.2` THE SYSTEM SHALL agregar esas notas, con fecha, proyecto y feature, a un único archivo
  central en la carpeta de configuración de Claude del usuario, compartido por todos sus
  proyectos.
- `R7.3` IF una nota incluiría código fuente, secretos o datos personales del proyecto, THEN THE
  SYSTEM SHALL dejar fuera ese contenido y describir el problema en términos generales.
- `R7.4` IF el archivo central no se puede escribir, THEN THE SYSTEM SHALL guardar las notas con
  los documentos de la feature y avisar al usuario.
- `R7.5` THE SYSTEM SHALL no modificar el plugin a partir de estas notas.

### US8. Replanteo de una tarea trabada

Como desarrollador, quiero que una tarea trabada la replantee un agente más fuerte en vez de
seguir a fuerza bruta, para cortar los ciclos a tiempo.

- `R8.1` WHEN una tarea llega a su quinta revisión fallida, o la misma revisión falla por tercera
  vez, THE SYSTEM SHALL detener las rondas de arreglo y pedir a un rethinker de solo lectura (Opus,
  esfuerzo max) por qué siguen fallando los intentos y qué hacer distinto.
- `R8.2` WHEN el rethinker propone un enfoque nuevo que deja de lado el intento actual, THE SYSTEM
  SHALL conservar ese intento de forma recuperable (nunca descartarlo) y reconstruir la tarea con
  sus instrucciones.
- `R8.3` WHEN el rethinker concluye que el plan, el diseño o la spec deben cambiar, THE SYSTEM
  SHALL proponer ese cambio y esperar al usuario.
- `R8.4` IF la tarea sigue fallando dos revisiones más después del replanteo, THEN THE SYSTEM
  SHALL detenerse y preguntar al usuario.
- `R8.5` IF el rethinker intenta cambiar un archivo, THEN THE SYSTEM SHALL impedirlo y devolverle
  el cambio.

### US9. Arreglos anteriores que deben seguir valiendo

Como autor del plugin, quiero que los arreglos ya revisados sigan valiendo, para no volver a
errores conocidos.

- `R9.1` THE SYSTEM SHALL encontrar el commit de una tarea por coincidencia exacta de su ID, de
  modo que T1 nunca coincida con T10 a T19.
- `R9.2` THE SYSTEM SHALL crear todo worktree de una sesión paralela fuera de la carpeta del
  proyecto.
- `R9.3` THE SYSTEM SHALL poner cada lote de una migración y cada tarea de una limpieza en su propia
  rama, con su propia pull request.
- `R9.4` WHEN una pull request ya subida necesita reescribir su historia (por ejemplo, un rebase
  sobre la rama principal actualizada), THE SYSTEM SHALL pedir el visto bueno del usuario para esa
  reescritura y subirla con `--force-with-lease`.

### US10. Suite de pruebas de los acuerdos

Como autor del plugin, quiero una suite automática que falle cuando un acuerdo deja de cumplirse,
para que cada cambio al plugin los respete.

- `R10.1` THE SYSTEM SHALL incluir pruebas automáticas, corridas por el comando de check del
  repositorio, para cada criterio de esta spec que se pueda comprobar sin correr un modelo: modelos
  y esfuerzos, qué skills declaran modelo o esfuerzo, permisos de cada rol, estructura y lectura
  de la plantilla del plan, el patrón de búsqueda de commits por tarea, la configuración de la
  revisión en el CI, la presencia de cada paso nuevo del flujo en las instrucciones, la versión y
  el changelog.
- `R10.2` IF alguna de esas pruebas falla, THEN THE SYSTEM SHALL hacer fallar el comando de check
  nombrando el acuerdo roto.
- `R10.3` THE SYSTEM SHALL incluir una evaluación de comportamiento para cada mecanismo nuevo con
  usuario (pausa por slice con preguntas, decisión de diseño, resumen de slice, resumen final y
  notas de mejora), corrible con el comando de evaluación del plugin y fuera del check.

## Constraints

- Los hooks usan solo la biblioteca estándar de Python y funcionan con Python 3.10 a 3.13 en
  Windows, macOS y Linux.
- Las personas que usan el plugin no necesitan dependencias nuevas.
- Los planes escritos con la versión 0.5.0 siguen funcionando.
- El comando de check del repositorio termina en menos de 5 minutos en una máquina de desarrollo y
  pasa antes de cada commit.
- Requiere Claude Code 2.1.292 o posterior (esfuerzo por despacho).
- La entrega es la versión 0.6.0 del plugin, con su entrada en el changelog.

## Final verification

1. En la rama de la feature, `npm run check` pasa, incluida la suite nueva, y
   `claude plugin validate ./plugins/konundrm-eng` no reporta errores.
2. En un proyecto de prueba vacío, con el plugin cargado desde esta rama, correr
   `/konundrm-eng:develop-feature` con una feature chica de dos slices cuyo segundo slice tenga dos
   particiones independientes y una tarea con dos enfoques razonables. Ver: el plan con slices,
   particiones y la decisión a elegir; la pregunta sobre el paralelo; la pausa del primer slice con
   su resumen, el orden de lectura y dos o tres preguntas; el segundo slice construido por dos
   sesiones e integrado; al final, la elección entre pull requests apiladas o una sola, con el
   aviso de `risk:high` si corresponde; el resumen final de la feature; y notas nuevas en el
   archivo central de mejoras, sin código ni secretos del proyecto.

## Open questions

<!-- Use [NEEDS CLARIFICATION: …] inline above. This section must be empty before approval. -->
