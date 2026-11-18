# Design: Tareas del tamaño justo y revisiones proporcionales al cambio

- **Spec:** [requirements.md](requirements.md)
- **Status:** Approved <!-- Draft → Approved → Done -->

## Overview

Tres cambios, los tres de texto.

1. `writing-plans` lista primero un comportamiento por línea y después consolida: junta en una
   tarea las líneas de riesgo bajo que tienen un mismo dueño, forman un solo cambio lógico y caben
   en el límite. La tarea consolidada es una tarea normal del plan (un ID, un commit, una nota)
   con una lista `Tests:` de un test por comportamiento, así que `task_ledger.py`,
   `session_doctor.py`, `run_slices.py` y `metrics_report.py` no cambian. El usuario mueve el
   criterio con la línea `Consolidation:` del encabezado del plan.
2. `develop-feature` construye esa tarea en un solo ciclo: un `test-writer` escribe todos sus
   tests, un `implementer` los hace pasar de a uno, viendo fallar cada uno antes de su código, y
   las revisiones corren una vez. Las pruebas de propiedad de los invariantes se escriben en ese
   mismo paso rojo, para que la verificación por riesgo no fuerce otra ronda.
3. Una regla nueva, `## Reviews after a change`, decide desde el diff del cambio qué revisiones se
   repiten. La usan las rondas de arreglo, la verificación por riesgo, el arreglo de un check en
   rojo, `fix-bug` y los ajustes: los cambios chicos que el usuario pide sobre lo ya construido,
   que ahora se hacen en el momento (`## Adjustments` y `reference/adjustments.md`).

## Module ownership

`P` = `plugins/konundrm-eng`.

| Responsibility | Owner module | New or extended | Why there | Covers |
| --- | --- | --- | --- | --- |
| Listar un comportamiento por línea, consolidar y mostrar los totales al aprobar | `P/skills/writing-plans/SKILL.md` y su plantilla `templates/tasks.md` | Extended | ya es dueña del tamaño de las tareas y de la revisión del plan | R1.1–R1.9 |
| Construir una tarea con varios tests en un ciclo | `P/skills/develop-feature/SKILL.md` (pasos 1 y 2) y `reference/dispatch-prompts.md` | Extended | el orquestador despacha y verifica | R2.1–R2.3, R3.9 |
| Escribir varios tests en un despacho, un informe por test | `P/agents/test-writer.md`, `P/skills/test-driven-development/SKILL.md` | Extended | el agente precarga la skill y devuelve su formato | R2.1, R2.2, R2.4 |
| Hacer pasar los tests de a uno, viendo fallar cada uno | `P/agents/implementer.md` | Extended | ya es dueño del paso verde | R2.3 |
| Revisar cada comportamiento de la lista contra su test | `P/agents/spec-reviewer.md` | Extended | ya comprueba que cada criterio tenga un test que fallaría | R2.6 |
| Dividir una tarea consolidada trabada | `P/agents/rethinker.md` y `## Rethink` de `develop-feature` | Extended | ya nombra "la tarea son dos comportamientos" | R2.5 |
| Qué revisiones se repiten después de un cambio | `P/skills/develop-feature/SKILL.md`, sección nueva `## Reviews after a change` | New section | las rondas de arreglo viven ahí y `fix-bug` ya enlaza esa skill | R3.1–R3.5, R3.7, R3.8 |
| La misma regla en el arreglo de un bug | `P/skills/fix-bug/SKILL.md` (paso 6) | Extended | enlaza la sección, no la repite | R3.6 |
| Ajustes: qué cuenta como uno, quién lo hace y cuándo | `P/skills/develop-feature/SKILL.md`, sección nueva `## Adjustments`, con punteros en las fases 0, 3 y 4 y en el paso 7 de `## Slice checkpoint` | New section | el orquestador recibe el pedido | R4.1, R4.2, R4.10, R4.11 |
| Ajustes: el procedimiento | `P/skills/develop-feature/reference/adjustments.md` y tres prompts nuevos | New file | `SKILL.md` ya pasa de 700 líneas; el detalle se lee solo al hacer un ajuste | R4.3–R4.9 |
| Commit de un ajuste con su nota | `P/skills/committing-changes/SKILL.md` (`### Inside develop-feature`) | Extended | ya es dueña de los commits del flujo | R4.6 |
| Dónde queda anotado cada ajuste y cada revisión que no se repitió | `P/skills/develop-feature/templates/slice-summary.md` y `feature-summary.md` | Extended | los resúmenes ya juntan lo que una persona revisa | R3.8, R4.8 |
| El principio, para todos los roles | `P/skills/engineering-standards/SKILL.md` (§2, §7, §10) | Extended | fuente única que las skills citan; la tabla tiene un solo dueño y aquí solo se enlaza | R1.2, R1.3, R3.1, R3.2 |
| Aviso de comparabilidad | `P/skills/measure-impact/SKILL.md` | Extended | ahí se interpreta el informe | R5.4 |
| Pruebas de contrato, evals, versión, changelog y README | `P/hooks/tests/contract/`, `P/evals/`, `plugin.json`, `CHANGELOG.md`, `README.md` | Extended | — | R5.1–R5.3 |

**Duplicates found:** la regla "qué revisiones corren" existía en tres formas (paso 4 de
`develop-feature`: todas otra vez; `fix-bug` paso 6: "review again"; `tidy-codebase`: solo
`code-reviewer`). `fix-bug` pasa a enlazar la sección nueva; `tidy-codebase` no cambia, porque su
cambio es por definición sin comportamiento nuevo y ya corre solo la revisión de código. Los
estándares enlazan la sección en vez de repetir la tabla.

## Interfaces

Encabezado del plan, que guarda el criterio del usuario y los totales:

```text
- **Consolidation:** low · <n> behaviors in <m> tasks
```

`low` por omisión; `low and medium` junta además los casos de una misma regla de riesgo medio (la
misma función o clase y el mismo archivo de tests, a lo más tres por tarea); `none` deja una tarea
por línea. El riesgo alto nunca se consolida.

Tarea consolidada en `tasks.md` (ningún script lee los campos indentados; `Covers` sigue cerrando
la línea de la tarea):

```text
- [ ] **T2** <What the task delivers, in one statement> · `behavior` · Risk: low · Covers: R1.2, R1.3, R1.4
  - Tests:
    - `tests/<path>/test_<module>.py::test_<behavior a>`: <behavior a> (R1.2)
    - `tests/<path>/test_<module>.py::test_<behavior b>`: <behavior b> (R1.3)
    - `tests/<path>/test_<module>.py::test_<behavior c>`: <behavior c> (R1.4)
  - Files: `src/<path>/<module>.py` (modify)
  - Verify: `<command that runs only these tests>`
  - Depends on: T1
```

Condiciones para consolidar (todas): riesgo bajo en cada línea; un dueño (una fila de la tabla de
responsabilidades del diseño, o una misma regla aplicada a varios dueños, con un solo comando de
verificación); un cambio lógico (un título sin "and" que una cosas que se revisarían aparte);
dentro del límite (a lo más cinco comportamientos y unas 300 líneas cambiadas de código y tests,
sin pasar del tope del pull request). Las líneas no necesitan estar seguidas. Nunca: `property`,
una línea con una decisión abierta o una que agrega una dependencia. Ante la duda, separadas.

Informe del `test-writer` para una tarea con varios tests: un bloque `RED:` o `CHARACTERIZATION:`
por test, en el orden de la tarea, con el formato de siempre. Informe del `implementer`: una línea
por test que dice si lo vio en rojo antes de escribir su código.

Qué revisiones se repiten después de un cambio (`## Reviews after a change`). Se decide desde el
diff del cambio: dentro de una tarea el árbol ya tiene el trabajo sin commitear, así que antes del
cambio se marca con `git add -A && git write-tree` y después se mira `git diff --stat <sha>` y los
archivos nuevos de `git status --porcelain`.

```text
it fixed a finding of a review                              → that review, always
it added tests and changed nothing else                     → spec review
it changed a test that was there, or what the code does
  for some input (a value the code decides with included)   → spec review and code review
it changed how the code is built without changing what it
  does, added a silencer or a skip, or touched what
  configures a gate                                         → code review
it changed only text that nothing reads                     → no review: verify and the check
anything, on a high task                                    → every review of step 3
the fix of a red check                                      → the code review, always
in doubt, or when the user asks for a review                → run it (both when in doubt)
```

Un archivo que el producto, una herramienta o un test lee es código, sea cual sea su extensión.

Pedido del usuario sobre algo ya construido (`## Adjustments`): se clasifica antes de tocar nada.
Es un cambio de plan si agrega o quita un criterio o un comportamiento sin criterio, cambia el
diseño, toca un archivo que lista una tarea de riesgo alto o algo que los estándares llaman
riesgo alto, cambia código de un archivo que ninguna tarea lista, o se espera que pase de unas 50
líneas; ante la duda, también. Lo demás es un ajuste: criterio primero → `test-writer` (rojo) si
cambia lo que el código hace → `implementer` → verificación → revisiones según su diff → check →
commit propio con nota → entrada en el próximo resumen. Un pedido sobre la tarea en curso se hace
dentro de esa tarea y queda anotado en ella como `- Change: <pedido> (user)`.

Comandos que las skills piden (los corre Claude):

- Marca antes de un cambio dentro de una tarea: `git add -A && git write-tree`.
- Commit de un ajuste, con su nota en el mismo comando:
  `git add -A && git commit -m "<type>(<scope>): <summary>" --trailer "Co-Authored-By: …" && git notes --ref=refs/notes/konundrm add -m "Adjusts: T<n>" -m "Reviews: <spec, code | spec | code | none> (<why the others were not needed>)" -m "Asked: <the request, in one line>" HEAD`.
  Tipo según lo que cambia; `fix` solo si el pedido informa un defecto, y entonces la nota lleva
  además `Escaped-gate:`.
- Ajustes hechos desde el resumen del slice anterior:
  `git log --notes=refs/notes/konundrm --format='%h %s%n%N' --grep '^Adjusts:' <from>..HEAD`.
- Qué tareas cambiaron un archivo, aunque el plan no lo liste:
  `git log --notes=refs/notes/konundrm --format=%N <base>..HEAD -- <file>`.
- Apartar un ajuste que resultó ser un cambio de plan:
  `git stash push --include-untracked -m "<NNN-slug> adjustment set aside: <request>"`.

Prompts nuevos en `reference/dispatch-prompts.md`: `test-writer (adjustment)`,
`implementer (adjustment)` y `adjustment review`. Los prompts del `test-writer`, del `implementer`
y de la ronda de arreglo pasan a hablar de "the task's tests", y el de re-revisión lleva los
informes de cada ronda desde la última vez que corrió esa revisión.

## Data flow

Plan: comportamientos, uno por línea → consolidación → tareas → slices → particiones → revisión
del plan contra la primera lista → aprobación con los totales.

Tarea consolidada: `test-writer` (todos los tests, un informe por test) → comprobación test por
test → `implementer` (de a uno, cada uno visto en rojo) → cinco corridas → revisiones una vez →
marca → ronda de arreglo → solo las revisiones que el diff de la ronda pide → verificación por
riesgo → check → commit con `task_ledger.py message` y `record`.

Ajuste: pedido → clasificación → criterio en `requirements.md` → (`test-writer` → rojo) →
`implementer` → verificación → revisiones según el diff → `task_ledger.py status` → check si no
está verde → commit + nota → (en vivo) `git push` → entrada en el próximo resumen, leída de la
nota.

## Dependency rules

Solo cambia texto de skills, agentes y plantillas, y las pruebas de contrato. Ningún script ni
hook cambia, y no hay dependencias nuevas entre módulos: `fix-bug` ya enlaza `develop-feature`.
`engineering-standards` enlaza la sección de `develop-feature` sin repetir su tabla.

## Alternatives considered

- Dejar las tareas atómicas en `tasks.md` y agruparlas en lotes de revisión — rechazado: una
  versión anterior del plugin lee una sola línea `Task:` por commit y volvería a construir las
  demás tareas del lote, las rondas compartidas se sumarían una vez por tarea en el informe, y el
  lote ahorra solo las revisiones de un ciclo que cuesta lo mismo sea cual sea su tamaño.
- Construir cada tarea atómica con su `test-writer` y su `implementer` y revisar por lote —
  rechazado: ahorra solo las revisiones (8 despachos en vez de 12 para tres tareas; la tarea
  consolidada usa 4) y deja varios commits sin revisar hasta el final del lote.
- Consolidar el riesgo medio por omisión — rechazado por ahora: en los planes 001 y 002 habría
  juntado 2 tareas de 79 y ninguna de 44, y es donde los tests escritos en lote protegen menos.
  Queda como opción por plan (`low and medium`) y se revisa con el primer plan medido con la
  0.9.0.
- Consolidar solo tareas consecutivas del mismo archivo, hasta 200 líneas (el primer borrador) —
  rechazado: repitiendo los planes 001 y 002 con el tamaño real de sus commits dejaba 75 de 79 y
  42 de 44 tareas, porque una tarea de un comportamiento ya cambia unas 100 líneas contando sus
  tests. Con las condiciones de ahora la misma repetición deja 62 y 36.
- Un script que clasifique el diff y diga qué revisiones corren — rechazado: el único clasificador
  del plugin trata todo archivo `.md` como documentación, que en este repositorio es el producto,
  y saber si cambió un comportamiento pide leer el diff. La tabla decide desde el diff del cambio.
- Comparar contra el índice de Git en vez de contra una marca con identificador — rechazado: un
  `implementer` que hace `git add` mueve el índice y el cambio se vería vacío, que es el error en
  la dirección insegura.
- Registrar las revisiones en la línea `Rounds:` — rechazado: `close-slice` la reescribe con sus
  tres contadores y el informe la suma; un ajuste no es una ronda de su tarea.
- Editar el resumen del slice en el mismo commit del ajuste — rechazado: cambia el árbol después
  del check, así que el gate del commit lo corre de nuevo, y un resumen ya publicado en su pull
  request cambiaría. El próximo resumen lo lista desde su nota.
- Seguir convirtiendo cada cambio pedido en una tarea nueva y solo acelerar ese ciclo — rechazado:
  el costo que el usuario describe es el ciclo completo más la aprobación de la tarea.

## Threats

Ninguna: no cambia ninguna frontera de confianza y ninguna tarea es de riesgo alto. El riesgo
propio de la feature es de proceso (una revisión que no corre cuando debía), y lo acotan `R3.2`,
`R3.3`, `R3.7`, `R4.2` y `R4.5`, más el check obligatorio en cada commit.

## Delivery

Un solo slice: la versión 0.9.0. Las reglas se activan cuando alguien actualiza el plugin; un
plan ya escrito se construye igual. Para volver atrás se revierte el commit de la versión: no hay
datos que migrar, y los planes consolidados siguen siendo planes válidos para la 0.8.0, que
construiría cada tarea con un solo test (por eso conviene no bajar de versión a mitad de una
feature planificada con la 0.9.0).

## Risks

- Un orquestador clasifica como ajuste lo que era un cambio de plan, o se salta una revisión que
  hacía falta — la regla se decide desde el diff y no desde el informe de quien lo hizo, la duda
  lleva a las dos revisiones o al cambio de plan, el riesgo alto queda fuera y cada revisión que
  no se repitió queda anotada; el check, la revisión de spec de la feature completa, la CI y la
  persona que aprueba el pull request siguen detrás.
- Una tarea consolidada falla una revisión por un solo comportamiento y arrastra a los demás — el
  límite de cinco comportamientos y 300 líneas lo acota, la ronda de arreglo es una sola, la
  repetición es proporcional y el replanteo puede dividirla sin renumerar.
- Los tests escritos en un despacho se verían fallar solo contra el código vacío — por eso el
  `implementer` los hace pasar de a uno y ve cada uno en rojo, y la revisión de spec comprueba
  cada comportamiento de la lista contra su propio test.
- Ninguna regla de estas la hace cumplir un hook: son instrucciones, sostenidas por pruebas de
  contrato sobre el texto y por dos evals. Lo que queda escrito (la nota del ajuste, los
  resúmenes) permite auditarlas después.
- Las métricas dejan de compararse entre versiones — `measure-impact` lo avisa.
- El eval del ajuste necesita Git y no corre en Windows — queda escrito y su estructura se
  comprueba en el check; correrlo queda para Linux o macOS.
