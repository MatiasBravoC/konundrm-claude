# Tareas del tamaño justo y revisiones proporcionales al cambio

- **Spec:** 004-right-sized-flow
- **Status:** Approved <!-- Draft → Approved → Done · 2026-11-17: el usuario delegó los criterios ("ese criterio defínelo tú") y cedió el control del proyecto para construirla sin pausas ("te cedo control absoluto en este proyecto") -->
- **Date:** 2026-11-17

## Problem

Hoy `writing-plans` parte cualquier feature, por chica que sea, en tareas de un solo
comportamiento ("One behavior, one test, one commit"), y `develop-feature` le da a cada una su
propio ciclo: `test-writer`, `implementer`, revisión de spec, revisión de código, cinco corridas,
check y commit. El costo es por ciclo, no por línea: en la medición de la 002, una tarea de 30
líneas y una de 110 tardaron lo mismo, 12,4 minutos. Las tres features de este repositorio tienen
79, 44 y 12 tareas; en las dos primeras, tres de cada cuatro son de riesgo bajo, y en la 003 el
usuario ya redujo el plan a mano.

Además, cuando el usuario pide un cambio chico sobre algo ya construido, el flujo lo convierte en
una tarea nueva, espera su aprobación y le corre el ciclo completo; si lo pide sobre la tarea en
curso, no hay regla y se repite todo. Y dentro de una tarea, después de cada ronda de arreglo se
repiten todas las revisiones aunque el arreglo no toque lo que una de ellas mira, y la
verificación por riesgo agrega tests cuando la tarea ya pasó sus revisiones, lo que fuerza otra
ronda.

La 002 dejó esto fuera a propósito ("Tareas más grandes o revisiones por lote", non-goal) para
probarlo aparte. Esta feature es esa prueba.

## Goals

- Menos ciclos por feature sin perder trazabilidad: los comportamientos afines de riesgo bajo se
  construyen y se revisan juntos, cada uno con su test y su criterio.
- Que un cambio chico pedido por el usuario se haga en el momento, sea sobre la tarea en curso o
  sobre algo ya commiteado, y pase solo por las revisiones que ese cambio necesita.
- Que después de un cambio se repitan solo las revisiones a las que ese cambio afecta, y que la
  verificación por riesgo no fuerce una ronda extra.
- Un criterio explícito y conservador: nada de esto se aplica al riesgo alto y, ante la duda, se
  deja la tarea separada y se corre la revisión.
- Que quede a la vista qué se consolidó, qué revisiones no se repitieron y por qué.
- Que el usuario pueda mover el criterio al aprobar el plan, sin editar el plugin.

## Non-goals

- Consolidar tareas de riesgo alto, o mezclar niveles de riesgo en una tarea.
- Consolidar el riesgo medio por omisión: solo cuando el usuario lo pide para ese plan (`R1.8`).
- Quitar el test en rojo antes del código, las cinco corridas en verde, el check antes de cada
  commit o la separación de roles (quien escribe tests no toca producción y al revés).
- Saltarse revisiones en el primer ciclo de una tarea: la primera vez siempre corren la de spec y
  la de código, y la de seguridad en riesgo alto.
- Hooks o scripts que decidan qué revisiones corren o que impidan una clasificación equivocada: la
  regla vive en las skills, como las demás reglas de revisión, y la sostienen pruebas de contrato.
- Medir el ahorro por tarea: `measure-impact` con transcripciones ya compara despachos por rol.
- Cambiar o volver a consolidar los planes ya escritos: se construyen como están.
- Los cambios que el usuario pide fuera de una sesión de `develop-feature`.
- Correr en esta máquina (Windows) los evals nuevos que necesitan Git: se validan en Linux o macOS.

## User stories and acceptance criteria

### US1. Un plan con tareas del tamaño justo

Como desarrollador, quiero que el plan junte en una sola tarea los comportamientos afines de
riesgo bajo, para que una feature chica no pase por decenas de ciclos de revisión.

- `R1.1` WHEN escribe el plan, THE SYSTEM SHALL listar primero cada comportamiento por separado,
  una línea cada uno, y después consolidar en una sola tarea los que cumplen todas las condiciones
  de `R1.2`, estén o no seguidos en la lista, antes de escribir las tareas y armar los slices.
- `R1.2` THE SYSTEM SHALL consolidar comportamientos solo cuando todos son de riesgo bajo; tienen
  un mismo dueño en el diseño (una fila de su tabla de responsabilidades) o aplican una misma
  regla a varios dueños, con un solo comando de verificación para sus tests; forman un solo
  cambio lógico (un título que no une con "y" cosas que se revisarían por separado); y la tarea
  que resulta no pasa de cinco comportamientos ni de unas 300 líneas cambiadas de código y tests,
  ni del tope del pull request.
- `R1.3` THE SYSTEM SHALL dejar como tarea propia todo comportamiento de riesgo medio o alto, toda
  prueba de propiedad (`property`), todo comportamiento con una decisión abierta y todo el que
  agrega una dependencia; IF duda de alguna condición de `R1.2`, THEN THE SYSTEM SHALL dejarlos
  separados.
- `R1.4` THE SYSTEM SHALL escribir cada tarea consolidada como una sola tarea del plan: un ID, un
  riesgo, los criterios de todos sus comportamientos en `Covers`, un test por comportamiento con
  el criterio que afirma y un comando de verificación que corre todos esos tests.
- `R1.5` THE SYSTEM SHALL juntar entre sí las líneas sin test (`chore`) que un mismo título
  describe (los pasos de una misma preparación o ediciones chicas de un mismo tipo), o dentro de
  la tarea de riesgo bajo que preparan cuando cambian uno de sus archivos.
- `R1.6` WHEN revisa el plan antes de mostrarlo, THE SYSTEM SHALL comprobar contra la lista inicial
  que cada comportamiento de una tarea consolidada conserva su test y que ninguna tarea
  consolidada rompe `R1.2` ni `R1.3`.
- `R1.7` WHEN muestra el plan para aprobarlo, THE SYSTEM SHALL decir cuántos comportamientos reúne
  cada tarea consolidada, el total de comportamientos y de tareas, y por qué quedaron separadas
  las que no se juntaron, y dejar ese total en el encabezado del plan.
- `R1.8` WHERE el usuario lo pide para ese plan (en su pedido o al aprobarlo), THE SYSTEM SHALL
  consolidar también comportamientos de riesgo medio que son casos de una misma regla (la misma
  función o clase y el mismo archivo de tests), a lo más tres por tarea y conservando sus
  invariantes; WHERE pide no consolidar, THE SYSTEM SHALL dejar un comportamiento por tarea; y
  WHEN el usuario cambia ese criterio al revisar el plan, THE SYSTEM SHALL volver a consolidar y
  mostrar el plan de nuevo.
- `R1.9` WHEN agrega tareas a un plan ya aprobado (un cambio de plan, o los vacíos que encuentra
  la revisión de la feature completa), THE SYSTEM SHALL consolidarlas con las mismas reglas, solo
  entre ellas, sin renumerar ni cambiar las tareas que ya tienen su commit.

### US2. Una tarea consolidada se construye en un solo ciclo

Como desarrollador, quiero que una tarea consolidada pase por un solo ciclo de test,
implementación, revisiones, check y commit, para ahorrar los ciclos sin que ningún comportamiento
se quede sin su test en rojo.

- `R2.1` WHEN construye una tarea que lista varios tests, THE SYSTEM SHALL despachar un solo
  `test-writer` que los escribe todos, uno por comportamiento, antes de que exista el código de
  producción de la tarea, y que informa de cada test por separado.
- `R2.2` WHEN ese `test-writer` termina, THE SYSTEM SHALL comprobar cada test contra su informe:
  falla por la razón que informó, o ya pasa porque el comportamiento existía y afirma su criterio;
  IF un test no cumple, THEN THE SYSTEM SHALL devolver solo ese test a otro `test-writer`,
  nombrando los que no debe tocar; IF todos ya pasan así, THEN THE SYSTEM SHALL saltarse la
  implementación.
- `R2.3` THE SYSTEM SHALL construir la tarea con un solo `implementer`, que hace pasar los tests de
  a uno, en el orden de la tarea, viendo fallar cada uno antes de escribir su código, y después
  exigir cinco corridas seguidas en verde y pasarla una sola vez por el ciclo de revisiones, check
  y commit; después de un cambio se repiten las revisiones de `R3.1`.
- `R2.4` WHILE la skill `test-driven-development` trabaja con una persona, o la tarea tiene un solo
  test, THE SYSTEM SHALL seguir escribiendo un test por vez y deteniéndose en rojo.
- `R2.5` WHEN el replanteo de una tarea consolidada concluye que reúne comportamientos que no van
  juntos, THE SYSTEM SHALL proponer dividirla como un cambio de plan que aprueba el usuario,
  conservando su ID para la primera parte y sin renumerar ninguna otra tarea.
- `R2.6` WHEN revisa contra la spec una tarea que lista varios tests, THE SYSTEM SHALL comprobar
  cada comportamiento de la lista contra su propio test, no una vez por criterio.

### US3. Después de un cambio, solo las revisiones que hacen falta

Como desarrollador, quiero que después de una ronda de arreglo se repitan solo las revisiones a
las que ese arreglo afecta, para no pagar revisiones que no pueden encontrar nada.

- `R3.1` WHEN una tarea de riesgo bajo o medio cambia después de sus primeras revisiones y antes de
  su commit (una ronda de arreglo, la verificación por riesgo o el arreglo de un check en rojo),
  THE SYSTEM SHALL repetir solo: cada revisión que levantó un hallazgo que ese cambio corrige;
  solo la de spec cuando el cambio agregó tests y nada más; las revisiones de spec y de código
  cuando el cambio tocó un test que ya existía o lo que el código hace para alguna entrada; solo
  la de código cuando cambió cómo está construido el código sin cambiar lo que hace, o tocó algo
  que dobla un gate (un silenciador, un test saltado, la configuración del check, de los tests,
  del linter, de los tipos, de la cobertura, de la mutación, de los hooks o de la CI); siempre la
  de código después de arreglar un check en rojo; y ninguna cuando cambió solo texto que nada lee.
- `R3.2` WHERE la tarea es de riesgo alto, THE SYSTEM SHALL repetir todas sus revisiones después de
  cualquier cambio, como hoy.
- `R3.3` IF no está claro en qué caso cae un cambio, THEN THE SYSTEM SHALL correr las dos
  revisiones; y WHEN el usuario pide una revisión que la regla no pedía, THE SYSTEM SHALL correrla.
- `R3.4` THE SYSTEM SHALL commitear una tarea solo cuando cada una de sus revisiones pasó y,
  después de pasar, ningún cambio tocó lo que esa revisión mira.
- `R3.5` WHEN el código o los tests cambian después de la verificación, THE SYSTEM SHALL volver a
  correr el comando de verificación antes de repetir revisiones, y el check completo sigue siendo
  obligatorio antes del commit.
- `R3.6` WHEN `fix-bug` repite revisiones después de una ronda de arreglo, THE SYSTEM SHALL seguir
  la misma regla.
- `R3.7` THE SYSTEM SHALL decidir qué revisiones se repiten desde el diff del cambio y no desde el
  informe de quien lo hizo: dentro de una tarea, marca el árbol antes del cambio y guarda su
  identificador, para que el diff contra esa marca muestre solo ese cambio aunque alguien mueva el
  índice de Git; IF pierde la marca, THEN THE SYSTEM SHALL correr las dos revisiones.
- `R3.8` THE SYSTEM SHALL anotar cada revisión que no se repitió después de un cambio y por qué, y
  llevarla al resumen del slice y al registro que lee el `process-reviewer`.
- `R3.9` WHEN construye una tarea de riesgo medio o alto que lista invariantes, THE SYSTEM SHALL
  escribir sus tests de propiedad junto con el test de la tarea, antes de las primeras revisiones,
  y WHEN la verificación por riesgo cambia algo, THE SYSTEM SHALL repetir las revisiones una sola
  vez, cuando ese paso termina.

### US4. Un ajuste chico se hace en el momento

Como desarrollador, quiero pedir un cambio chico sobre algo ya construido y que se haga en el
momento, verificado en proporción a lo que toca, para iterar sin que cada ajuste recorra el flujo
completo.

- `R4.1` WHEN el usuario pide un cambio sobre algo que la feature ya construyó (durante la
  construcción, en la pausa de un slice, al terminar la feature o al retomarla ya terminada), THE
  SYSTEM SHALL clasificarlo antes de tocar nada: un ajuste o un cambio de plan.
- `R4.2` THE SYSTEM SHALL tratar como cambio de plan (tareas nuevas o una edición del plan, que el
  usuario aprueba y que después se construyen en el ciclo de tareas) todo pedido que agrega o
  quita un criterio de aceptación o un comportamiento que ningún criterio cubre; cambia el diseño
  (el dueño de una responsabilidad, una interfaz pública o una dependencia); toca un archivo que
  lista una tarea de riesgo alto, o algo que los estándares llaman riesgo alto; cambia código de
  un archivo que ninguna tarea de la feature lista; o se espera que pase de unas 50 líneas
  cambiadas de código y tests. IF no está claro cuál de los dos es, THEN es un cambio de plan; y
  WHEN el cambio de plan llega sobre una feature ya terminada, THE SYSTEM SHALL reabrirla con el
  sí del usuario.
- `R4.3` WHEN el pedido es un ajuste, THE SYSTEM SHALL hacerlo en el momento con los mismos roles
  (el `test-writer` cambia los tests y el `implementer` el resto; si cambia lo que el código hace,
  primero su test en rojo), sin tareas nuevas ni otra aprobación; el orquestador solo edita él
  mismo los documentos de la feature y la prosa que nada carga, ejecuta ni prueba.
- `R4.4` WHEN el ajuste está hecho, THE SYSTEM SHALL correr cinco veces los tests que cambió o
  agregó y una vez el comando de verificación de las tareas cuyo comportamiento ajusta, decidir
  desde su diff las revisiones que `R3.1` indica, y pasar el check antes del commit.
- `R4.5` IF el diff del ajuste muestra un cambio de plan (`R4.2`), mirando también qué tareas
  cambiaron cada archivo aunque el plan no lo liste, THEN THE SYSTEM SHALL apartarlo sin
  commitearlo, de modo que se pueda recuperar, y proponer el cambio de plan; IF solo creció más de
  lo esperado, THEN THE SYSTEM
  SHALL conservarlo, correrle las dos revisiones y decirlo; y IF una revisión sigue fallando
  después de una ronda de arreglo, THEN deja de ser un ajuste y pasa a ser un cambio de plan.
- `R4.6` THE SYSTEM SHALL dejar cada ajuste en un commit propio, con el tipo de lo que cambia, y
  guardar fuera del mensaje qué tareas ajusta, qué revisiones corrieron y por qué no las demás, y
  lo que pidió el usuario; IF el pedido informa que lo construido no cumple un criterio aprobado,
  THEN es un defecto: el commit es `fix` y guarda el gate que se escapó, para que el informe de
  impacto lo cuente.
- `R4.7` WHEN un ajuste cambia un detalle que un criterio de aceptación dice (un texto, un valor,
  un límite), THE SYSTEM SHALL actualizar ese criterio antes de despachar a quien lo construye,
  dejarlo en el mismo commit y decirle al usuario qué criterio cambió, con el texto anterior y el
  nuevo; y WHEN agrega, renombra o quita un test, THE SYSTEM SHALL actualizar las líneas de esa
  tarea en el plan.
- `R4.8` THE SYSTEM SHALL anotar cada ajuste en el próximo resumen que se escribe (el del slice o
  el de la feature), a partir de lo guardado con su commit, con lo pedido, las revisiones que
  corrieron, las que no hicieron falta y el criterio que cambió; WHERE la feature ya terminó, THE
  SYSTEM SHALL agregarlo al resumen de la feature.
- `R4.9` WHERE la feature se publica en vivo, THE SYSTEM SHALL subir el commit de cada ajuste como
  los demás commits del flujo, y el ajuste pedido en la pausa de un slice va a la rama del slice
  siguiente; WHERE se construye en local y sus pull requests ya están abiertos, THE SYSTEM SHALL
  preguntar antes de subirlo.
- `R4.10` WHEN el usuario pide un cambio sobre la tarea en curso, antes de su commit, THE SYSTEM
  SHALL clasificarlo como en `R4.2`, hacerlo dentro de esa tarea (primero el criterio que cambie,
  después el pedido anotado en la tarea del plan para que lo lean quienes la construyen y la
  revisan, y su test en rojo antes del código cuando cambia lo que el código hace) y repetir solo
  las revisiones que `R3.1` indica, sin contarlo como una revisión fallida.
- `R4.11` THE SYSTEM SHALL hacer los ajustes solo en la sesión principal de la feature, en el
  próximo punto limpio entre tareas y antes de pasar la feature a otra sesión; WHILE una ola en
  paralelo está en construcción, THE SYSTEM SHALL esperar a que se integre; una sesión de
  partición no hace ajustes y se detiene con `BLOCKED:`, y una sesión que ya pasó la feature a
  otra le dice al usuario que lo pida en la que la está construyendo; y WHEN retoma una feature
  ya terminada, THE SYSTEM SHALL atender el cambio pedido sin volver a correr el cierre de la
  feature.

### US5. Acuerdos protegidos y documentados

Como autor del plugin, quiero que cada acuerdo nuevo quede protegido por pruebas y documentado,
para que no se pierda en la próxima versión.

- `R5.1` THE SYSTEM SHALL comprobar dentro del check del proyecto cada acuerdo de esta feature que
  se puede comprobar sin un modelo: las instrucciones de las skills, los agentes y las plantillas.
- `R5.2` THE SYSTEM SHALL tener un eval de comportamiento por mecanismo nuevo que el usuario ve: el
  plan con tareas consolidadas y el ajuste verificado en proporción.
- `R5.3` THE SYSTEM SHALL publicar estos cambios como versión 0.9.0, con su changelog y con el
  README describiendo las tareas consolidadas, los ajustes y la revisión proporcional.
- `R5.4` THE SYSTEM SHALL avisar, donde se interpreta el informe de impacto, que desde esta versión
  una tarea puede reunir varios comportamientos, un cambio ya no repite todas las revisiones y los
  ajustes son commits que no son tareas, así que las tareas hechas, las rondas por tarea y los
  fixes por feature no se comparan con los de features planificadas antes.

## Constraints

- Solo cambia texto: skills, agentes, plantillas, evals, documentación y pruebas de contrato.
  Ningún hook ni script del flujo cambia, y un plan consolidado usa el formato que ya leen
  `task_ledger.py`, `session_doctor.py`, `run_slices.py` y `metrics_report.py`: una tarea
  consolidada es una tarea, con un ID, un commit y una nota.
- Los planes y los historiales de antes de esta versión siguen funcionando igual.
- Cada comportamiento conserva su test y su criterio; cada commit sigue necesitando el check en
  verde para ese árbol exacto.
- El riesgo alto conserva todas sus verificaciones: ni consolidación, ni revisiones
  proporcionales, ni ajustes en el momento.
- Qué revisiones corren se decide desde el diff del cambio, no desde lo chico que suena el pedido
  ni desde el informe de quien lo hizo.
- Un archivo que el producto, una herramienta o un test lee es código, sea cual sea su extensión:
  en este repositorio, las skills, los agentes y las plantillas.
- Los datos del flujo siguen fuera de los mensajes de commit y del texto de los pull requests.

## Final verification

1. `npm run check` pasa con las pruebas de contrato nuevas y `claude plugin validate
   ./plugins/konundrm-eng` pasa.
2. El eval `behavior-plan-consolidates-related-tasks`, que no necesita Git, corre en esta máquina
   y su plan junta los comportamientos afines de riesgo bajo, deja sola la tarea de riesgo medio y
   lista un test por comportamiento.
3. Fuera de esta corrida: el eval `behavior-adjustment-runs-needed-reviews` en Linux o macOS, y la
   próxima feature que se construya con la 0.9.0, medida con `/konundrm-eng:measure-impact` y sus
   transcripciones como despachos por comportamiento, contra los 4,7 despachos por tarea de las
   features 001 a 003.

## Open questions

<!-- Use [NEEDS CLARIFICATION: …] inline above. This section must be empty before approval. -->
