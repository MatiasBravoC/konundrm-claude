# Publicar en GitHub mientras se construye una feature

- **Spec:** 003-live-github-publishing
- **Status:** Done <!-- Draft → Approved → Done -->
- **Date:** 2026-11-01

## Problem

Hoy `develop-feature` construye toda la feature en local y solo al final, con el sí del usuario,
sube las ramas y abre los pull requests apilados. El usuario no puede seguir el trabajo en GitHub
mientras avanza: lo ve todo de golpe, con varios slices ya encima. Además, cada commit de tarea
termina con líneas del flujo (`Task: T3 · Covers: R1.2`, `Rounds: …`) y la descripción de cada PR
trae IDs de requisitos y tareas y la palabra slice: otro developer que revisa el código no conoce
el flujo y no entiende nada de eso. Por último, el manifiesto del plugin, el README y dos
plantillas de setup-project apuntan a la org `konundrm` de GitHub, que no existe.

## Goals

- Que el usuario pueda seguir cada feature en GitHub en tiempo real: la rama de cada slice desde
  que empieza, cada tarea como un commit atómico apenas pasa sus revisiones y el check, y cada
  slice terminado como un pull request apilado sobre el anterior.
- Que cualquier developer entienda cada commit y cada pull request sin conocer el flujo: hablan
  solo del cambio.
- Pull requests de un tamaño que se revisa bien: unas 300 a 500 líneas cambiadas por slice.
- Que publicar nunca ponga en riesgo el historial: nada se reescribe y solo la sesión principal
  publica.
- Que el plugin apunte a su repositorio real.

## Non-goals

- Fusionar, aprobar o pedir revisores en los pull requests, o cambiar la configuración del
  repositorio en GitHub (protección de ramas, auto-merge, borrar ramas al fusionar).
- Rehacer el apilado cuando el usuario fusiona con squash un PR anterior mientras la feature se
  sigue construyendo: la construcción nunca reescribe lo que subió; `opening-pull-requests` sigue
  ofreciendo ese rebase después, con un sí explícito.
- Abrir el PR antes de que termine su slice (borradores que crecen mientras se construye).
- Cambiar de modo (local o en vivo) a mitad de una feature: se elige al aprobar el plan.
- Subir los datos del flujo o las ramas de las particiones, o retomar una feature desde otro clon
  u otra máquina.
- Reescribir el historial de las features ya construidas (001 y 002 conservan sus líneas).
- Otras plataformas que no sean GitHub, y elegir entre varias plantillas de una carpeta
  `PULL_REQUEST_TEMPLATE/`.
- Editar la descripción de un PR ya abierto (por ejemplo, para enlazar el resumen de la feature
  cuando exista).
- Quitar los IDs de los documentos de la feature (`requirements.md`, `design.md`, `tasks.md`,
  resúmenes y evidencia): son del flujo y los siguen usando.
- Publicar en vivo la construcción de esta misma feature: se construye en local y se sube solo con
  el sí del usuario.
- Controles automáticos que bloqueen un push, un PR con datos del flujo o un mensaje de commit con
  líneas del flujo, y un script propio para publicar: las reglas viven en las instrucciones de las
  skills y Claude corre `git` y `gh` siguiéndolas. <!-- 2026-11-01: el usuario redujo el alcance a
  las 10 tareas que atacan su pedido; se sacaron los criterios que exigían esos controles. -->

## User stories and acceptance criteria

### US1. Elegir la publicación en vivo al aprobar el plan

Como desarrollador, quiero elegir para cada feature si se publica en GitHub mientras se construye,
para seguirla en tiempo real solo cuando me sirve.

- `R1.1` WHEN el usuario aprueba el plan, el repositorio tiene un remoto y `gh`, con la sesión
  iniciada, ve ese repositorio en GitHub, THE SYSTEM SHALL preguntarle, en una pregunta aparte, si
  quiere publicar la feature en GitHub mientras se construye, y registrar en el plan la
  publicación en vivo solo con un sí explícito o cuando el usuario la pidió en su pedido.
- `R1.2` IF al aprobar el plan falta el remoto, `gh`, su sesión iniciada o su acceso a ese
  repositorio, THEN THE SYSTEM SHALL decir en una línea qué falta, no ofrecer la publicación en
  vivo y registrar la feature como local.
- `R1.3` WHILE el plan no registra la publicación en vivo (incluidos los planes escritos antes de
  esta versión), THE SYSTEM SHALL construir todo en local y preguntar antes de cualquier push al
  terminar la feature, como hoy.
- `R1.4` WHEN una sesión retoma la feature, THE SYSTEM SHALL seguir la elección registrada sin
  volver a preguntar.

### US2. La rama de cada slice en GitHub desde que empieza

Como desarrollador, quiero que la rama de cada slice aparezca en GitHub apenas el slice empieza,
para ver dónde va a llegar cada cambio.

- `R2.1` WHERE la feature se publica en vivo, WHEN empieza el primer slice, THE SYSTEM SHALL crear
  la rama `feat/<NNN-slug>-s1` desde el commit que agrega el spec y el plan, cambiarse a ella y
  subirla al remoto antes de empezar la primera tarea.
- `R2.2` WHERE la feature se publica en vivo, WHEN empieza el slice k (k > 1), THE SYSTEM SHALL
  crear la rama `feat/<NNN-slug>-s<k>` desde la punta de la rama del slice anterior, cambiarse a
  ella y subirla antes de empezar su primera tarea.
- `R2.3` IF la rama del slice ya existe (una sesión que retoma), THEN THE SYSTEM SHALL cambiarse a
  ella y seguir ahí, sin crearla de nuevo.

### US3. Cada commit en GitHub apenas se hace

Como desarrollador, quiero que cada commit se suba apenas se hace, para ver los cambios en GitHub
tarea por tarea.

- `R3.1` WHERE la feature se publica en vivo, WHEN el commit de una tarea pasa el gate de commit,
  THE SYSTEM SHALL subirlo a la rama del slice antes de empezar la tarea siguiente.
- `R3.2` WHERE la feature se publica en vivo, THE SYSTEM SHALL subir del mismo modo, apenas los
  hace, los demás commits del flujo en la rama del slice: el resumen del slice, los cambios de
  plan, la integración de particiones y el cierre de la feature.
- `R3.3` WHERE la feature se publica en vivo, WHEN el flujo integra una partición construida en
  paralelo, THE SYSTEM SHALL subir los commits integrados después de que el check pasa sobre
  ellos, y nunca subir las ramas de las particiones.
- `R3.4` WHEN una sesión retoma una feature que se publica en vivo, THE SYSTEM SHALL subir primero
  los commits de la rama del slice que todavía no están en el remoto.
- `R3.5` IF el repositorio no tiene remoto, o un push es rechazado o falla, THEN THE SYSTEM SHALL
  detenerse con una línea `BLOCKED:` que cite el error de Git, con el commit a salvo en local, sin
  forzar el push ni traer cambios del remoto.
- `R3.6` THE SYSTEM SHALL publicar solo desde la sesión principal y sin forzar nunca un push: los
  subagentes y las sesiones de partición nunca suben commits ni abren pull requests.

### US4. Un pull request por slice al terminarlo

Como desarrollador, quiero que cada slice terminado quede como un pull request apilado sobre el
anterior, con un orden explícito para aceptarlos, para revisar la feature por partes del tamaño de
un PR y saber cuál acepto primero.

- `R4.1` WHERE la feature se publica en vivo, WHEN el commit del resumen de un slice está en el
  remoto, THE SYSTEM SHALL abrir el pull request del slice, listo para revisar (no como borrador):
  el del primer slice contra la rama por defecto y el de cada slice siguiente contra la rama del
  slice anterior.
- `R4.2` IF la rama del slice anterior ya no está en el remoto (su PR se fusionó y se borró),
  THEN THE SYSTEM SHALL abrir el PR contra la rama por defecto.
- `R4.3` WHEN el plugin abre los PR apilados de una feature (en vivo o al terminarla), THE SYSTEM
  SHALL dejar explícito el orden en que se aceptan: el título de cada PR termina con su posición y
  el total de slices que tiene el plan cuando se abre, como `(2/5)`, y su descripción empieza,
  antes de cualquier sección, con una línea que dice esa posición y qué PR se fusiona antes
  (`Merge order: 2 of 5. Merge #11 first.`; el primero, `Merge order: 1 of 5. Merge this one
  first.`).
- `R4.4` WHEN un slice tiene una tarea de riesgo alto, THE SYSTEM SHALL ponerle a su PR la
  etiqueta `risk:high` si el repositorio la tiene; IF no la tiene, THEN THE SYSTEM SHALL abrir el
  PR sin ella y decirlo en la pausa del slice, sin crear la etiqueta.
- `R4.5` IF la rama del slice ya tiene un PR abierto, THEN THE SYSTEM SHALL no abrir otro.
- `R4.6` WHEN una sesión retoma una feature que se publica en vivo y un slice terminado no tiene PR,
  THE SYSTEM SHALL abrirlo antes de seguir.
- `R4.7` IF `gh` no puede abrir el PR, THEN THE SYSTEM SHALL detenerse con una línea `BLOCKED:` que
  cite el error, con la rama ya subida.
- `R4.8` WHEN se abre el PR de un slice, THE SYSTEM SHALL mostrar en la pausa del slice, o en el
  mensaje de la sesión cuando las pausas están preaprobadas, las URL de los PR de la feature
  abiertos hasta ahí, en el orden en que se aceptan.
- `R4.9` WHERE la feature se publica en vivo, WHEN termina la feature, THE SYSTEM SHALL subir el
  commit final a la rama del último slice y listar las URL de todos los PR de la feature en el
  orden en que se aceptan, en vez de preguntar si sube las ramas.

### US5. Un texto de PR que cualquier developer entiende

Como developer que revisa un PR sin conocer el flujo, quiero que su texto hable solo del cambio,
para entender qué revisar sin aprender la jerga del plugin.

- `R5.1` WHEN el plugin escribe el texto de un PR (en vivo, al terminar una feature o en un
  fix-bug), THE SYSTEM SHALL usar la plantilla de PR del repositorio cuando existe
  (`pull_request_template.md`, con cualquier combinación de mayúsculas, en `.github/`, en la raíz
  o en `docs/`, buscada en ese orden): sus secciones en el mismo orden, con sus títulos y su texto
  fijo tal cual, cada una llena con lo que pide en lugar de sus comentarios de ayuda, "None" en
  una sección sin contenido y sus casillas marcadas solo cuando lo que dicen se verificó.
- `R5.2` IF el repositorio no tiene esa plantilla (aunque tenga una carpeta con varias), THEN THE
  SYSTEM SHALL usar las secciones fijas del plugin, en este orden: "What and why"; "Where to look
  first", con el riesgo de cada cambio en palabras simples y, para lo de riesgo alto, los archivos
  y líneas que se leen primero y qué protegen; "How it was verified", con el resultado del check,
  cada comportamiento con su test y la evidencia de punta a punta; y "Not in this pull request".
- `R5.3` THE SYSTEM SHALL escribir el título del PR (el encabezado Conventional Commits de su
  cambio principal, de hasta 72 caracteres) y su descripción en inglés y en lenguaje simple.
- `R5.4` THE SYSTEM SHALL dejar fuera del título y de la descripción de cada PR los datos del
  flujo: los IDs de requisitos, criterios de bug, tareas, slices y particiones del plan; la
  palabra "slice"; las líneas `Task:`, `Covers:`, `Rounds:` y `Escaped-gate:`; las rondas de
  revisión y los nombres de los roles del plugin. Quedan fuera de esta regla el código y las rutas
  entre backticks, los bloques de código y los destinos de los enlaces.

### US6. Commits que hablan solo del cambio

Como developer que lee el historial, quiero que cada commit diga solo de qué trata, para
entenderlo sin conocer el flujo con que se hizo.

- `R6.1` THE SYSTEM SHALL escribir cada mensaje de commit que hace el plugin (tareas, spec y plan,
  resúmenes, cambios de plan, informes e integración de particiones, cierre de la feature y
  fix-bug) con solo lo que cambia: sin IDs de requisitos, criterios de bug, tareas, slices ni
  particiones, sin nombrar los slices, particiones ni rondas del flujo, y sin líneas `Task:`,
  `Covers:`, `Rounds:` ni `Escaped-gate:`; se mantienen `Fixes: <issue>` y la atribución que
  configura la sesión.
- `R6.2` THE SYSTEM SHALL guardar los datos del flujo del commit de cada tarea (la tarea, los
  requisitos que cubre y sus rondas) y, en un fix-bug, los del fix (el criterio y el gate que se
  escapó) fuera del mensaje, en el repositorio local y en el mismo paso que el commit, y usarlos
  para retomar, cerrar cada slice y medir el impacto.
- `R6.3` WHEN el flujo integra una partición construida en paralelo, THE SYSTEM SHALL llevar los
  datos del flujo de cada commit a su copia integrada.
- `R6.4` WHEN una sesión retoma una feature, THE SYSTEM SHALL guardar primero los datos que una
  sesión cortada dejó pendientes entre su commit y su registro, para no construir esa tarea dos
  veces.
- `R6.5` WHEN el historial tiene commits con esas líneas en el mensaje (features empezadas antes
  de esta versión), THE SYSTEM SHALL seguir leyéndolos como hoy, también en una feature que mezcla
  los dos formatos.

### US7. Slices de 300 a 500 líneas

Como desarrollador, quiero que cada slice cambie unas 300 a 500 líneas, para que cada PR se revise
bien.

- `R7.1` WHEN escribe el plan, THE SYSTEM SHALL armar cada slice para unas 300 a 500 líneas
  cambiadas (agregadas más quitadas) de código y tests, sin contar los documentos de la feature;
  uno más chico solo cuando la feature entera es más chica o cuando separar el trabajo de riesgo
  alto lo exige.
- `R7.2` WHEN termina un slice, THE SYSTEM SHALL anotar en su resumen las líneas cambiadas de
  código y tests (agregadas y quitadas) y, aparte, las de los documentos de la feature.
- `R7.3` IF las líneas cambiadas de código y tests de un slice pasan del tope del plan, THEN THE
  SYSTEM SHALL avisarlo en la pausa del slice con la cifra y cuánto se pasó; con las pausas
  preaprobadas, el aviso queda en el resumen y en el mensaje de la sesión.
- `R7.4` THE SYSTEM SHALL usar 500 líneas cambiadas como tope por omisión de cada slice y de cada
  PR, en vez de 400.

### US8. El plugin apunta a su repositorio

Como persona que instala el plugin, quiero que sus direcciones lleven a su repositorio real, para
poder instalarlo.

- `R8.1` THE SYSTEM SHALL apuntar el repositorio del manifiesto del plugin, los comandos de
  instalación del README y las dos plantillas que setup-project copia (el registro del
  marketplace y el workflow de revisión) a `MatiasBravoC/konundrm-claude`, sin que ningún archivo
  fuera de `specs/` nombre la org `konundrm` de GitHub.
- `R8.2` THE SYSTEM SHALL decir en el README que el repositorio es privado: quien instala el
  plugin y el CI de cada proyecto que lo usa necesitan acceso a él.

### US9. Acuerdos protegidos y documentados

Como autor del plugin, quiero que cada acuerdo nuevo quede protegido por pruebas y documentado,
para que no se pierda en la próxima versión.

- `R9.1` THE SYSTEM SHALL comprobar dentro del check del proyecto cada acuerdo de esta feature que
  se puede comprobar sin un modelo: las instrucciones de las skills y los comandos.
- `R9.2` THE SYSTEM SHALL publicar estos cambios como versión 0.8.0, con su changelog y con el
  README describiendo la publicación en vivo y dónde quedan los datos del flujo.

## Constraints

- Los comandos que cambian usan solo la librería estándar de Python 3.10+ y corren en Windows,
  macOS y Linux. Publicar usa Git y, para los PR, la CLI `gh`.
- Los planes y los historiales de antes de esta versión siguen funcionando (`R1.3`, `R6.5`).
- El comando de estado sigue respondiendo en menos de 2 s con un plan de 100 tareas en esta
  máquina (Windows 11), ahora leyendo los datos del flujo desde fuera de los mensajes.
- En vivo, cada tarea agrega un solo push y ninguna llamada a `gh`; `gh` se usa al aprobar el
  plan, al terminar cada slice y al retomar.
- Nunca se reescribe lo que ya está en el remoto, y ni los subagentes ni las sesiones de partición
  suben nada.
- Nada más cambia en GitHub: ni configuración ni etiquetas; solo ramas, commits y pull requests.
- Los datos del flujo quedan solo en el repositorio local.
- Se mantienen la línea `Co-Authored-By` de los commits y la línea de atribución de los PR que
  configura la sesión.

## Final verification

1. `npm run check` pasa con los tests nuevos y `claude plugin validate ./plugins/konundrm-eng`
   pasa.
2. En un repositorio de prueba, `message` + `git commit` + `record` dejan un commit cuyo mensaje
   no trae líneas del flujo y cuya nota sí; el estado y el cierre de slices lo leen como la tarea
   construida, con sus rondas.
3. Sobre el historial de este repositorio (features 001 y 002), el estado, el cierre de slices y
   el informe de impacto dan lo mismo que con la 0.7.0.
4. La entrega de esta feature, con el sí del usuario: sus PR apilados en GitHub llevan `(1/2)` y
   `(2/2)` en el título, la línea `Merge order:` al empezar y las cuatro secciones fijas en inglés,
   sin datos del flujo.
5. La publicación en vivo se prueba en la próxima feature que se construya con `Publish: live`
   (fuera de esta corrida): la rama de cada slice aparece en GitHub al empezar, cada commit apenas
   termina su tarea y el PR de cada slice al terminarlo.
6. La medición de esta construcción con `session_costs.py` registra en la evidencia lo que la 002
   dejó por confirmar (sección 5 de su diagnóstico): que la segunda sesión de slice tenga un
   contexto chico, un solo check por tarea corrido tal cual con un `git commit` que tarda segundos,
   y las revisiones en un solo mensaje.

## Open questions

<!-- Use [NEEDS CLARIFICATION: …] inline above. This section must be empty before approval. -->
