# Tasks: Flujo más eficiente

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Approved <!-- Draft → Approved → Done -->
- **Check command:** `npm run check`
- **Base commit:** `79dbbaedcab693f354418995a117fb422ae95f50`
- **Pull request budget:** 400 changed lines per slice
- **Parallel:** no <!-- ningún slice tiene una ola de dos o más particiones -->
- **Checkpoints:** pre-approved <!-- el usuario lo aprobó con el plan (2026-10-30) -->
- **Decisions:** pre-approved <!-- el usuario lo aprobó con el plan (2026-10-30), aparte de las pausas -->

- **Sessions:** per-slice <!-- esta corrida ya aplica R1.1: cada pausa sigue en una sesión nueva con /konundrm-eng:develop-feature specs/002-efficient-feature-flow -->

<!-- Rutas relativas a la raíz del repositorio; P = plugins/konundrm-eng.
Verify de una prueba: python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks -k <test_name>
Las pruebas de contrato de esta feature viven en P/hooks/tests/contract/ y su docstring empieza con
los IDs que protegen seguidos de "002" ("R2.1: 002 ..."), para no confundirlos con los de la 001.
Cada una busca solo las palabras clave de su regla dentro de su sección, no gramáticas de oraciones,
para que los slices quepan en el presupuesto. Al editar, conservar el final de línea de cada archivo
(algunos son CRLF). Si una prueba existente fija el texto que una tarea cambia, el test-writer la
actualiza en el paso rojo de esa tarea. -->

## Slice S1: el hook que registra checks no arranca Python para comandos que no son el check

- [x] **T1** `run.sh` no arranca Python para registrar un comando que no es el check · `behavior` · Risk: medium · Covers: R5.1
  - Test: `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_skips_python_for_a_command_that_is_not_the_check` (`CLAUDE_PLUGIN_DATA` temporal con `python-path` apuntando a un Python falso que deja un marcador; evento PostToolUse con `ls -la` y una salida de 200 KB → sin marcador)
  - Files: `P/hooks/run.sh` (modify)
  - Invariants: todo comando que contiene el texto del check arranca Python; el camino rápido nunca se salta un check real.
  - Verify: `... -k test_run_sh_skips_python_for_a_command_that_is_not_the_check`
  - Depends on: —
  - Decision: Option B (user) — cómo lee `run.sh` el evento antes de decidir
    - Option A: bucle `read` de builtins sobre todo stdin · pros: ningún proceso extra · cons: sh lee los pipes byte a byte, lento con salidas grandes
    - Option B: `head -c 8192` para el comienzo, decidir con `case` y vaciar el resto con `cat >/dev/null` · pros: costo fijo sea cual sea la salida · cons: dos procesos cortos; si el comando no cabe en 8 KB no decide y corre Python (R5.3)
    - Recommendation: B, confirmada midiendo ambas en esta máquina con un evento chico y uno de 200 KB.
  - Rounds: spec 2 · code 3 · escalations 0

- [x] **T2** `run.sh` arranca Python para el check del proyecto y para un check propio configurado · `behavior` · Risk: medium · Covers: R5.2
  - Test: `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_runs_python_for_the_check_and_a_custom_check` (`npm run check` → marcador y evento intacto; con `KONUNDRM_CHECK_CMD=make verify`, `make verify` → marcador)
  - Files: `P/hooks/run.sh` (modify)
  - Invariants: el evento que recibe Python es byte a byte el que llegó a `run.sh`.
  - Verify: `... -k test_run_sh_runs_python_for_the_check_and_a_custom_check`
  - Depends on: T1
  - Rounds: spec 1 · code 2 · escalations 0

- [x] **T3** Si no puede leer el comando, `run.sh` corre el registro completo · `behavior` · Risk: medium · Covers: R5.3
  - Test: `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_runs_python_when_it_cannot_tell_the_command` (comillas escapadas dentro del comando, campo `command` después de los primeros 8 KB, evento sin `command` → marcador)
  - Files: `P/hooks/run.sh` (modify)
  - Invariants: ante la duda, Python corre.
  - Verify: `... -k test_run_sh_runs_python_when_it_cannot_tell_the_command`
  - Depends on: T2
  - Rounds: spec 1 · code 2 · escalations 0

- [x] **T4** El gate de commit y el guard reciben el evento intacto y el gate sigue fallando cerrado · `behavior` · Risk: high · Covers: R5.4
  - Test: `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_passes_the_event_intact_to_the_gate_and_the_guard` (para `gate_git_commit.py` y `guard_new_dependencies.py` el Python falso recibe el mismo evento, también con `ls`; sin Python, un evento con `git commit` sigue denegado)
  - Files: `P/hooks/run.sh` (modify only if the test fails)
  - Invariants: ningún script distinto de `record_check_result.py` toma el camino rápido.
  - Mutation: no hay herramienta para sh; los casos por script del test la reemplazan (se registra en la evidencia).
  - Security: frontera `run.sh` → gate y guard (Threats, fila 1).
  - Evidence: en un repo de prueba con el check en rojo, el gate real deniega `git commit` pasando por `run.sh`; comandos y salida en `evidence/T4.md`.
  - Verify: `... -k test_run_sh_passes_the_event_intact_to_the_gate_and_the_guard`
  - Depends on: T3
  - Rounds: spec 1 · code 3 · escalations 0

<!-- T42 se agregó el 2026-10-30, después del resumen de S1 y con el visto bueno del usuario. En las
transcripciones de la 0.6.0, solo 86 de 5.016 comandos de shell (1,7%) habrían tomado el camino
rápido: casi todos llevan comillas (la ruta del repo tiene un espacio), y la regla de T1–T3 manda a
Python todo comando con un escape JSON, camino que ahora cuesta ~100 ms más. Con T42 serían ~77%. El
caso de comillas escapadas de la prueba de T3 y el generador `_escaped_case` de su prueba de
propiedad fijan la regla vieja; el test-writer los actualiza en el paso rojo. La prueba de propiedad
de T1 descarta hoy los comandos con `\` o `"`; para el invariante de T42 se amplía a ellos. -->
- [x] **T42** `run.sh` decide también cuando el comando lleva comillas o barras escapadas: busca la palabra del check en el texto escapado, hasta la primera comilla sin escapar · `behavior` · Risk: medium · Covers: R5.1, R5.3
  - Test: `P/hooks/tests/integration/test_hook_scripts.py::test_run_sh_skips_python_for_a_quoted_command_that_is_not_the_check` (`ls "my dir"`, `git commit -m "x"` y un comando que termina en `\` → sin marcador; `cd "<raíz con un espacio>" && npm run check` → marcador y evento intacto; con un override cuya palabra lleva `"`, `\` o `/`, un comando con escapes → marcador)
  - Files: `P/hooks/run.sh` (modify)
  - Invariants: todo comando que corre el check arranca Python, también con comillas, barras o `cd "<raíz>" &&`; el valor del comando termina en la primera comilla no escapada.
  - Verify: `... -k test_run_sh_skips_python_for_a_quoted_command_that_is_not_the_check`
  - Depends on: T4
  - Rounds: spec 3 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P1 | T1–T4, T42 | — |

## Slice S2: commits de tarea por rango y huella del check junto al repositorio

- [x] **T5** El lector del plan entrega el Base commit y los requisitos de cada tarea · `behavior` · Risk: low · Covers: R1.8, R4.2
  - Test: `P/hooks/tests/test_tasks_document.py::test_reads_the_base_commit_and_each_tasks_covers`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Verify: `... -k test_reads_the_base_commit_and_each_tasks_covers`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T6** Los commits de tarea se buscan solo en `<base>..HEAD`, con sus rondas · `behavior` · Risk: medium · Covers: R1.8, R1.9
  - Test: `P/hooks/tests/test_task_commits.py::test_finds_task_commits_only_after_the_base_with_their_rounds` (repo temporal: `Task: T1` antes de la base y T1, T2 después, uno con `Rounds:`; T01 cuenta como T1; T1 no calza con T10)
  - Files: `P/hooks/scripts/task_commits.py` (new), `P/hooks/scripts/working_tree.py` (expose its Git runner), `P/hooks/scripts/metrics_report.py` (import the `Task:` trailer pattern from `task_commits`)
  - Invariants: un commit cuenta para una tarea solo si su línea `Task:` nombra ese número y está en el rango.
  - Verify: `... -k test_finds_task_commits_only_after_the_base_with_their_rounds`
  - Depends on: T5
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T7** Un check que pasa, corrido por Claude o por el gate, deja su huella junto al repositorio · `behavior` · Risk: low · Covers: R4.1
  - Test: `P/hooks/tests/test_record_check_result.py::test_a_passing_check_remembers_its_tree_beside_the_repository` (`quality_check.green_tree` devuelve la huella tras `record_check_result` y tras `run_check`; un check fallido no la escribe)
  - Files: `P/hooks/scripts/quality_check.py`, `P/hooks/scripts/record_check_result.py` (modify)
  - Verify: `... -k test_a_passing_check_remembers_its_tree_beside_the_repository`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P2 | T5–T7 | — |

## Slice S3: `task_ledger.py status`, el estado de la feature en una llamada

- [x] **T8** `status` muestra la próxima tarea, las tareas con commit, el árbol y el check en una llamada · `behavior` · Risk: low · Covers: R4.1, R1.8
  - Test: `P/hooks/tests/test_task_ledger.py::test_status_shows_next_task_built_tasks_tree_and_check` (plan de 3 tareas, T1 commiteada con su casilla sin marcar → próxima T2; árbol limpio; check verde tras recordar la huella)
  - Files: `P/hooks/scripts/task_ledger.py` (new)
  - Verify: `... -k test_status_shows_next_task_built_tasks_tree_and_check`
  - Depends on: T6, T7
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T9** `status` nombra la próxima tarea de cada partición de la ola en curso · `behavior` · Risk: low · Covers: R4.1
  - Test: `P/hooks/tests/test_task_ledger.py::test_status_names_the_next_task_of_each_partition_in_the_current_wave`
  - Files: `P/hooks/scripts/task_ledger.py`, `P/hooks/scripts/tasks_document.py` (receives the wave and partition logic now in `session_doctor.py`, as `next_tasks(document, built)`), `P/hooks/scripts/session_doctor.py` (uses it)
  - Verify: `... -k test_status_names_the_next_task_of_each_partition_in_the_current_wave`
  - Depends on: T8
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T10** Con un plan ilegible, `status` dice el archivo y la línea y sale con error sin cambiar nada · `behavior` · Risk: low · Covers: R4.6
  - Test: `P/hooks/tests/test_task_ledger.py::test_status_names_the_file_and_line_when_the_plan_cannot_be_read` (plan inexistente → exit 2 con la ruta; sin `Base commit` → exit 2 con `archivo:línea`)
  - Files: `P/hooks/scripts/task_ledger.py`
  - Verify: `... -k test_status_names_the_file_and_line_when_the_plan_cannot_be_read`
  - Depends on: T8
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P3 | T8–T10 | — |

## Slice S4: mensaje del commit de tarea, contabilidad de la pausa y arranque de sesión por commits

- [x] **T11** `message` arma el mensaje con el asunto, `Task: T<n> · Covers: …` del plan y `Rounds:`, lo escribe bajo el directorio de Git e imprime su ruta · `behavior` · Risk: low · Covers: R4.2, R2.7
  - Test: `P/hooks/tests/test_task_ledger.py::test_message_builds_the_task_commit_message_from_the_plan`
  - Files: `P/hooks/scripts/task_ledger.py`
  - Verify: `... -k test_message_builds_the_task_commit_message_from_the_plan`
  - Depends on: T8
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T12** `message` rechaza una tarea que no existe o que ya tiene commit, sin escribir nada · `behavior` · Risk: low · Covers: R4.4
  - Test: `P/hooks/tests/test_task_ledger.py::test_message_refuses_an_unknown_or_already_committed_task`
  - Files: `P/hooks/scripts/task_ledger.py`
  - Verify: `... -k test_message_refuses_an_unknown_or_already_committed_task`
  - Depends on: T11
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T13** `close-slice` marca las casillas y escribe las rondas de las tareas commiteadas del slice, conservando los finales de línea · `behavior` · Risk: medium · Covers: R2.8, R4.5
  - Test: `P/hooks/tests/test_task_ledger.py::test_close_slice_checks_boxes_and_writes_rounds_from_the_commits` (CRLF y LF; una tarea sin commit queda sin marcar y se informa; una línea `Rounds:` existente se reemplaza)
  - Files: `P/hooks/scripts/task_ledger.py`
  - Invariants: correrlo dos veces deja el mismo archivo; solo cambian casillas y líneas `Rounds:` del slice.
  - Verify: `... -k test_close_slice_checks_boxes_and_writes_rounds_from_the_commits`
  - Depends on: T11
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T14** Al iniciar sesión, las tareas con commit cuentan como hechas aunque su casilla siga sin marcar · `behavior` · Risk: low · Covers: R1.9
  - Test: `P/hooks/tests/test_session_doctor.py::test_counts_committed_tasks_as_done_and_names_the_first_without_a_commit`
  - Files: `P/hooks/scripts/session_doctor.py` (modify)
  - Verify: `... -k test_counts_committed_tasks_as_done_and_names_the_first_without_a_commit`
  - Depends on: T9
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T15** El informe de impacto lee las rondas escritas por `close-slice` igual que las escritas por tarea · `behavior` · Risk: low · Covers: R2.9
  - Test: `P/hooks/tests/test_metrics_report.py::test_reads_rounds_written_by_close_slice_and_per_task_alike`
  - Files: `P/hooks/scripts/metrics_report.py` (modify only if the test fails)
  - Verify: `... -k test_reads_rounds_written_by_close_slice_and_per_task_alike`
  - Depends on: T13
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P4 | T11–T15 | — |

## Slice S5: cada rol corre solo lo que necesita

- [x] **T16** El test-writer corre solo los tests que escribió o cambió, nunca el check ni la suite completa · `behavior` · Risk: low · Covers: R2.1
  - Test: `P/hooks/tests/contract/test_agents.py::test_test_writer_runs_only_its_own_tests`
  - Files: `P/agents/test-writer.md` (modify)
  - Verify: `... -k test_test_writer_runs_only_its_own_tests`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T17** Los revisores de spec, código y seguridad usan la salida que les da el orquestador y no corren el check ni la suite completa · `behavior` · Risk: low · Covers: R2.2
  - Test: `P/hooks/tests/contract/test_agents.py::test_reviewers_rely_on_the_orchestrators_verification_output` (los tres agentes lo dicen; sus prompts en `reference/dispatch-prompts.md` traen un campo con esa salida)
  - Files: `P/agents/spec-reviewer.md`, `code-reviewer.md`, `security-reviewer.md`, `P/skills/develop-feature/reference/dispatch-prompts.md` (modify)
  - Verify: `... -k test_reviewers_rely_on_the_orchestrators_verification_output`
  - Depends on: T16
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T18** El verificador de hallazgos corre solo los tests o reproducciones que su hallazgo necesita · `behavior` · Risk: low · Covers: R2.3
  - Test: `P/hooks/tests/contract/test_agents.py::test_finding_verifier_runs_only_what_its_finding_needs`
  - Files: `P/agents/finding-verifier.md` (modify)
  - Verify: `... -k test_finding_verifier_runs_only_what_its_finding_needs`
  - Depends on: T16
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T19** El implementer corre la suite completa solo dentro del check, una vez al final de cada despacho · `behavior` · Risk: low · Covers: R2.4
  - Test: `P/hooks/tests/contract/test_agents.py::test_implementer_runs_the_full_suite_only_in_the_final_check`
  - Files: `P/agents/implementer.md` (modify)
  - Verify: `... -k test_implementer_runs_the_full_suite_only_in_the_final_check`
  - Depends on: T16
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P5 | T16–T19 | — |

## Slice S6: revisiones en paralelo

- [x] **T20** Tras la verificación, las revisiones de spec y de código (y la de seguridad en riesgo alto) se lanzan a la vez, sin ningún escritor corriendo · `behavior` · Risk: low · Covers: R3.1, R3.5
  - Test: `P/hooks/tests/contract/test_flows.py::test_reviews_launch_at_once_with_no_writer_running`
  - Files: `P/skills/develop-feature/SKILL.md` (Phase 3 steps 3–4 and the "one at a time" paragraph), `P/hooks/scripts/audit_subagent_changes.py` (docstring: one writer at a time)
  - Verify: `... -k test_reviews_launch_at_once_with_no_writer_running`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T21** Todos los hallazgos van a una sola ronda de arreglo, y la re-revisión recibe sus hallazgos previos y lo que cambió · `behavior` · Risk: low · Covers: R3.2, R3.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_findings_share_one_fix_round_and_re_reviews_get_what_changed`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/develop-feature/reference/dispatch-prompts.md` (re-review prompt)
  - Verify: `... -k test_findings_share_one_fix_round_and_re_reviews_get_what_changed`
  - Depends on: T20
  - Decision: Option A (user) — qué recibe una re-revisión como "lo que cambió"
    - Option A: sus hallazgos previos y el informe de la ronda de arreglo (archivos y qué cambió en cada uno), y relee esos archivos · pros: simple, sin herramientas nuevas · cons: depende de que el informe nombre todo lo cambiado
    - Option B: sus hallazgos previos y un `git diff` contra una huella del árbol tomada antes del arreglo · pros: exacto aunque el informe omita algo · cons: el orquestador debe tomar y guardar la huella, y los archivos nuevos exigen `git add -N`
    - Recommendation: A; la revisión de spec de toda la feature (Phase 4) atrapa lo que se escape.
  - Rounds: spec 2 · code 1 · escalations 0

- [x] **T22** Una tarea se commitea solo cuando sus revisiones pasaron con su código final · `behavior` · Risk: low · Covers: R3.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_task_commits_only_after_its_reviews_pass_on_its_final_code`
  - Files: `P/skills/develop-feature/SKILL.md`
  - Verify: `... -k test_task_commits_only_after_its_reviews_pass_on_its_final_code`
  - Depends on: T21
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T23** La auditoría restaura el cambio de un revisor con otros revisores corriendo, terminen en el orden que terminen · `behavior` · Risk: medium · Covers: R3.6
  - Test: `P/hooks/tests/test_audit_subagent_changes.py::test_restores_a_reviewers_change_whatever_order_concurrent_reviewers_stop`
  - Files: `P/hooks/scripts/audit_subagent_changes.py` (modify only if the test fails)
  - Invariants: con dos revisores iniciados antes del cambio, el archivo vuelve a su estado inicial en los dos órdenes de término.
  - Verify: `... -k test_restores_a_reviewers_change_whatever_order_concurrent_reviewers_stop`
  - Depends on: T20
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P6 | T20–T23 | — |

## Slice S7: gate y commit sin check repetido, y reanudación por rango

- [x] **T24** En el gate, el orquestador corre el check solo si `status` no lo muestra verde para el árbol actual · `behavior` · Risk: low · Covers: R2.5, R2.6, R4.7
  - Test: `P/hooks/tests/contract/test_flows.py::test_gate_runs_the_check_only_when_status_is_not_green`
  - Files: `P/skills/develop-feature/SKILL.md` (Phase 3 step 6)
  - Verify: `... -k test_gate_runs_the_check_only_when_status_is_not_green`
  - Depends on: T8
  - Rounds: spec 1 · code 1 · escalations 0

- [ ] **T25** El commit de cada tarea usa `message` y un `git commit -F` normal, sin tocar casillas ni rondas del plan · `behavior` · Risk: high · Covers: R2.7, R4.2, R4.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_task_commit_goes_through_the_gate_with_its_message` (develop-feature paso 7 y la sesión de partición; el modo develop-feature de committing-changes)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/committing-changes/SKILL.md` (modify)
  - Invariants: ningún paso del flujo commitea fuera de un `git commit` visible en la línea de comandos.
  - Mutation: no aplica a prosa; la evidencia lo reemplaza.
  - Security: frontera orquestador → `git commit` (Threats, fila 2).
  - Evidence: en un repo de prueba, la línea `msg=$(… message …) && git add -A && git commit -F "$msg"` pasa por el gate real: con el check en rojo, denegada; en verde y con la huella del implementer, commitea sin volver a correr el check; en `evidence/T25.md`.
  - Verify: `... -k test_task_commit_goes_through_the_gate_with_its_message`
  - Depends on: T11, T24

- [ ] **T26** La reanudación usa `status`, que solo busca commits en `<base>..HEAD` · `behavior` · Risk: low · Covers: R1.8, R4.7
  - Test: `P/hooks/tests/contract/test_flows.py::test_resume_uses_status_and_the_base_range` (actualiza la prueba de `test_skills.py` que exige la búsqueda exacta si fija el texto viejo de develop-feature)
  - Files: `P/skills/develop-feature/SKILL.md` (Phase 0)
  - Verify: `... -k test_resume_uses_status_and_the_base_range`
  - Depends on: T8

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P7 | T24–T26 | — |

## Slice S8: la pausa cierra el slice y la feature sigue en una sesión nueva

- [ ] **T27** La pausa del slice corre `close-slice` y lleva su resultado en el commit del resumen · `behavior` · Risk: low · Covers: R2.8, R4.5
  - Test: `P/hooks/tests/contract/test_flows.py::test_slice_checkpoint_closes_the_slice_in_the_summary_commit`
  - Files: `P/skills/develop-feature/SKILL.md` (Slice checkpoint)
  - Verify: `... -k test_slice_checkpoint_closes_the_slice_in_the_summary_commit`
  - Depends on: T13

- [ ] **T28** Al terminar la pausa, la feature sigue en una sesión nueva: la app la abre; si no, queda el comando exacto · `behavior` · Risk: low · Covers: R1.1, R1.2, R1.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_feature_continues_in_a_new_session_after_each_slice`
  - Files: `P/skills/develop-feature/SKILL.md` (Slice checkpoint, Phase 4 handoff)
  - Verify: `... -k test_feature_continues_in_a_new_session_after_each_slice`
  - Depends on: T27

- [ ] **T29** Con cambios sin commitear, la pausa se detiene con `BLOCKED:` nombrando los archivos, sin abrir la sesión nueva · `behavior` · Risk: low · Covers: R1.6
  - Test: `P/hooks/tests/contract/test_flows.py::test_handoff_stops_on_uncommitted_changes`
  - Files: `P/skills/develop-feature/SKILL.md`
  - Verify: `... -k test_handoff_stops_on_uncommitted_changes`
  - Depends on: T28

- [ ] **T30** Con `Sessions: single` la feature sigue en la misma sesión, y la plantilla del plan trae esa línea · `behavior` · Risk: low · Covers: R1.7
  - Test: `P/hooks/tests/contract/test_flows.py::test_sessions_single_keeps_the_feature_in_one_session`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/writing-plans/templates/tasks.md` (modify)
  - Verify: `... -k test_sessions_single_keeps_the_feature_in_one_session`
  - Depends on: T28

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P8 | T27–T30 | — |

## Slice S9: `run_slices.py`, sesiones encadenadas desde la terminal

- [ ] **T31** `run_slices.py` corre una sesión headless por slice hasta que la feature termina, una sesión se bloquea o falla, y dice cuál pasó · `behavior` · Risk: high · Covers: R1.4
  - Test: `P/hooks/tests/test_run_slices.py::test_runs_one_session_per_slice_until_done_blocked_or_failed` (un `claude` falso por `--claude`: commitea y termina; imprime `BLOCKED:`; sale con 3; marca el plan `Done`)
  - Files: `P/hooks/scripts/run_slices.py` (new), `P/skills/develop-feature/SKILL.md` (una línea: cuándo usarlo)
  - Invariants: los argumentos que recibe `claude` son el prompt de reanudación y los que el usuario pasó tras `--`, nada más.
  - Mutation: `mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/run_slices.py` (no corre en Windows; se registra en la evidencia).
  - Security: frontera `run_slices.py` → sesiones headless (Threats, fila 3).
  - Evidence: corrida con el `claude` falso en un repo de prueba de dos slices, salida en `evidence/T31.md`.
  - Verify: `... -k test_runs_one_session_per_slice_until_done_blocked_or_failed`
  - Depends on: T28

- [ ] **T32** `run_slices.py` se detiene cuando una sesión termina sin agregar commits · `behavior` · Risk: medium · Covers: R1.5
  - Test: `P/hooks/tests/test_run_slices.py::test_stops_when_a_session_adds_no_commit`
  - Files: `P/hooks/scripts/run_slices.py`
  - Invariants: nunca abre más sesiones que slices pendientes más una.
  - Verify: `... -k test_stops_when_a_session_adds_no_commit`
  - Depends on: T31

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P9 | T31–T32 | — |

## Slice S10: `session_costs.py`, tokens y tiempo por rol

- [ ] **T33** `session_costs.py` informa por rol despachos, turnos, tokens por tipo, tokens ponderados, su parte y minutos activos · `behavior` · Risk: low · Covers: R6.1
  - Test: `P/hooks/tests/test_session_costs.py::test_reports_tokens_weights_shares_and_active_time_per_role` (transcripciones sintéticas: una sesión y dos subagentes con `meta.json`; mensajes repetidos por bloque cuentan una vez; pausas de más de 5 min no cuentan)
  - Files: `P/hooks/scripts/session_costs.py` (new)
  - Verify: `... -k test_reports_tokens_weights_shares_and_active_time_per_role`
  - Depends on: —

- [ ] **T34** `session_costs.py` cuenta corridas del check con su tiempo, corridas de tests y mensajes con despachos en paralelo · `behavior` · Risk: low · Covers: R6.1
  - Test: `P/hooks/tests/test_session_costs.py::test_counts_check_runs_test_runs_and_parallel_dispatches`
  - Files: `P/hooks/scripts/session_costs.py`
  - Verify: `... -k test_counts_check_runs_test_runs_and_parallel_dispatches`
  - Depends on: T33

- [ ] **T35** `session_costs.py` informa el contexto por turno del orquestador con más turnos · `behavior` · Risk: low · Covers: R6.2
  - Test: `P/hooks/tests/test_session_costs.py::test_reports_the_busiest_orchestrators_context_per_turn`
  - Files: `P/hooks/scripts/session_costs.py`
  - Verify: `... -k test_reports_the_busiest_orchestrators_context_per_turn`
  - Depends on: T33

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P10 | T33–T35 | — |

## Slice S11: la medición no filtra contenido y se ofrece desde el informe de impacto

- [ ] **T36** `session_costs.py` nunca imprime contenido de mensajes, comandos ni resultados · `behavior` · Risk: high · Covers: R6.3
  - Test: `P/hooks/tests/test_session_costs.py::test_never_prints_message_command_or_result_content` (transcripciones con un correo, una clave con forma real y código en mensajes, comandos y resultados; ninguno aparece en la salida ni en stderr)
  - Files: `P/hooks/scripts/session_costs.py`
  - Invariants: toda línea de salida es un encabezado fijo, un nombre de rol o de modelo, o números.
  - Mutation: `mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/session_costs.py` (no corre en Windows; se registra en la evidencia).
  - Security: frontera transcripciones → informe (Threats, fila 4).
  - Evidence: corrida sobre las transcripciones de la 0.6.0, con la comprobación de que una muestra de textos de esas transcripciones no aparece en la salida; en `evidence/T36.md`, sin copiar contenido.
  - Verify: `... -k test_never_prints_message_command_or_result_content`
  - Depends on: T35

- [ ] **T37** `session_costs.py` salta las líneas inválidas y las cuenta · `behavior` · Risk: low · Covers: R6.4
  - Test: `P/hooks/tests/test_session_costs.py::test_skips_and_counts_invalid_lines`
  - Files: `P/hooks/scripts/session_costs.py`
  - Verify: `... -k test_skips_and_counts_invalid_lines`
  - Depends on: T36

- [ ] **T38** `session_costs.py` lee transcripciones con rutas de más de 260 caracteres en Windows · `behavior` · Risk: low · Covers: R6.5
  - Test: `P/hooks/tests/test_session_costs.py::test_reads_transcripts_past_the_windows_path_limit`
  - Files: `P/hooks/scripts/session_costs.py`
  - Verify: `... -k test_reads_transcripts_past_the_windows_path_limit`
  - Depends on: T36

- [ ] **T39** El informe de impacto incluye el de costos cuando se le indican las transcripciones · `behavior` · Risk: low · Covers: R6.6
  - Test: `P/hooks/tests/contract/test_skills.py::test_measure_impact_adds_session_costs_when_given_transcripts`
  - Files: `P/skills/measure-impact/SKILL.md` (modify)
  - Verify: `... -k test_measure_impact_adds_session_costs_when_given_transcripts`
  - Depends on: T36

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P11 | T36–T39 | — |

## Slice S12: versión 0.7.0

- [ ] **T40** `plugin.json` dice 0.7.0 y el changelog de 0.7.0 nombra cada mecanismo nuevo · `behavior` · Risk: low · Covers: R7.1, R7.2
  - Test: `P/hooks/tests/contract/test_release.py::test_0_7_0_changelog_names_each_mechanism` (sesión por slice, un check por tarea, revisiones en paralelo, `task_ledger.py`, camino rápido de `run.sh`, `run_slices.py`, `session_costs.py`)
  - Files: `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md` (modify)
  - Verify: `... -k test_0_7_0_changelog_names_each_mechanism`
  - Depends on: T39

- [ ] **T41** El README describe el flujo nuevo, cómo encadenar sesiones y cómo medir una corrida · `behavior` · Risk: low · Covers: R7.2
  - Test: `P/hooks/tests/contract/test_release.py::test_readme_describes_sessions_per_slice_and_measuring_a_run`
  - Files: `README.md` (modify)
  - Verify: `... -k test_readme_describes_sessions_per_slice_and_measuring_a_run`
  - Depends on: T40

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P12 | T40–T41 | — |
