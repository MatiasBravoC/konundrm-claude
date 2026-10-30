# Tasks: Entrega guiada por slices, con particiones en paralelo

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Approved <!-- Draft → Approved → Done -->
- **Check command:** `npm run check`
- **Base commit:** `b8c3142`
- **Pull request budget:** 400 changed lines per slice
- **Checkpoints:** pre-approved <!-- el usuario lo aprobó durante la corrida (2026-10-30): seguir sin pausas entre slices -->

<!-- Rutas relativas a la raíz del repositorio; P = plugins/konundrm-eng.
Verify de una prueba: python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks -k <test_name>
Cada prueba de contrato vive en P/hooks/tests/contract/ y su docstring empieza con los IDs de los
requisitos que protege (por ejemplo "R1.1: ..."), para que una falla nombre el acuerdo roto (R10.2).
Referencia revisada para portar texto y código: la copia de trabajo 0.6.0 (scratchpad/new) y su
parche; las partes de una sola PR por feature no se portan. Al editar, conservar el final de línea
de cada archivo (algunos son CRLF). -->

## Slice S1: modelo y esfuerzo por rol, con la base de la suite de contratos

- [x] **T1** Cada agente existente declara su modelo y esfuerzo acordados · `behavior` · Risk: low · Covers: R1.1, R10.1
  - Test: `P/hooks/tests/contract/test_agents.py::test_each_role_has_its_agreed_model_and_effort` (crea el paquete `contract` con `__init__.py`; tabla: test-writer opus/medium, implementer opus/medium, spec-reviewer sonnet/high, code-reviewer opus/high, security-reviewer opus/xhigh, finding-verifier opus/high)
  - Files: `P/agents/test-writer.md`, `implementer.md`, `spec-reviewer.md`, `code-reviewer.md`, `security-reviewer.md`, `finding-verifier.md` (modify frontmatter)
  - Verify: `... -k test_each_role_has_its_agreed_model_and_effort`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T2** Solo la skill de planificación declara esfuerzo (xhigh) y ninguna skill declara modelo · `behavior` · Risk: low · Covers: R1.5, R1.6
  - Test: `P/hooks/tests/contract/test_skills.py::test_only_the_planning_skill_declares_effort`
  - Files: `P/skills/writing-plans/SKILL.md` (modify frontmatter)
  - Verify: `... -k test_only_the_planning_skill_declares_effort`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T3** develop-feature sobreescribe modelo y esfuerzo solo en arreglos, tareas de riesgo alto y la revisión de spec de toda la feature · `behavior` · Risk: low · Covers: R1.2, R1.3, R1.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_overrides_model_and_effort_where_agreed` (sección `## Model and effort` con las tres filas en `opus`/`high` y la regla de omitir los parámetros en el resto; `reference/dispatch-prompts.md` remite a ella)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/develop-feature/reference/dispatch-prompts.md` (modify)
  - Verify: `... -k test_develop_feature_overrides_model_and_effort_where_agreed`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T4** fix-bug, reviewing-pull-requests y migrate-code aplican las mismas sobreescrituras · `behavior` · Risk: low · Covers: R1.2, R1.3, R1.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_other_flows_override_model_and_effort_where_agreed`
  - Files: `P/skills/fix-bug/SKILL.md`, `P/skills/reviewing-pull-requests/SKILL.md`, `P/skills/migrate-code/SKILL.md` (modify)
  - Verify: `... -k test_other_flows_override_model_and_effort_where_agreed`
  - Depends on: T3
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T5** La revisión de PRs en el CI corre en Opus 5.5 con esfuerzo medium · `behavior` · Risk: low · Covers: R1.7
  - Test: `P/hooks/tests/contract/test_templates.py::test_ci_review_runs_on_opus_at_medium_effort`
  - Files: `P/skills/setup-project/templates/claude-review.yml` (modify)
  - Verify: `... -k test_ci_review_runs_on_opus_at_medium_effort`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S2: replanteo de tareas trabadas

- [x] **T6** El rethinker no puede cambiar archivos · `behavior` · Risk: medium · Covers: R8.5
  - Test: `P/hooks/tests/test_roles.py::test_read_only_roles_may_not_change_anything` (agrega `rethinker` a la lista)
  - Files: `P/hooks/scripts/roles.py` (modify)
  - Invariants: todo rol de solo lectura queda bloqueado para cualquier ruta (propiedad en T7)
  - Verify: `... -k test_read_only_roles_may_not_change_anything`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T7** Todo rol de solo lectura queda bloqueado para cualquier ruta · `property` · Risk: medium · Covers: R8.5
  - Test: `P/hooks/tests/test_roles.py::test_read_only_roles_are_denied_for_any_path`
  - Generator domain: 500 rutas relativas con `random.Random(7)`: 1 a 6 segmentos de `[a-z0-9_.-]`, incluidas carpetas de test, archivos ocultos y documentos `specs/<NNN-slug>/`
  - Invariants: para cada rol de `READ_ONLY_ROLES` y cada ruta, el motivo de rechazo menciona "read-only"
  - Files: `P/hooks/scripts/roles.py` (sin cambios esperados)
  - Verify: `... -k test_read_only_roles_are_denied_for_any_path`
  - Depends on: T6
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T8** Existe el agente rethinker: solo lectura, Opus con esfuerzo max y veredictos NEW APPROACH, ADJUST o PLAN CHANGE · `behavior` · Risk: low · Covers: R8.1
  - Test: `P/hooks/tests/contract/test_agents.py::test_the_rethinker_is_a_read_only_opus_max_agent`
  - Files: `P/agents/rethinker.md` (new)
  - Verify: `... -k test_the_rethinker_is_a_read_only_opus_max_agent`
  - Depends on: T6, T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T9** develop-feature replantea una tarea trabada en vez de seguir arreglándola · `behavior` · Risk: low · Covers: R8.1, R8.2, R8.3, R8.4, R1.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_rethinks_a_stuck_task` (sección `## Rethink`: quinta revisión fallida o tercera de la misma; el intento se guarda con stash y nunca se descarta; PLAN CHANGE espera al usuario; dos fallas más llevan al usuario; la lista de Escalation ya no pregunta a la tercera falla; `dispatch-prompts.md` tiene `## rethinker`)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/develop-feature/reference/dispatch-prompts.md` (modify)
  - Verify: `... -k test_develop_feature_rethinks_a_stuck_task`
  - Depends on: T8, T3
  - Rounds: spec 2 · code 1 · escalations 0

- [x] **T10** fix-bug también replantea un arreglo trabado · `behavior` · Risk: low · Covers: R8.1, R8.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_fix_bug_rethinks_a_stuck_fix`
  - Files: `P/skills/fix-bug/SKILL.md` (modify)
  - Verify: `... -k test_fix_bug_rethinks_a_stuck_fix`
  - Depends on: T9
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S3: slices con particiones en el plan

- [x] **T11** El lector de tasks.md asigna cada tarea a la partición de su slice · `behavior` · Risk: medium · Covers: R3.1
  - Rounds: spec 1 · code 1 · escalations 0
  - Test: `P/hooks/tests/test_tasks_document.py::test_reads_the_partition_of_each_task`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Invariants: cada tarea toma la partición de la primera fila que la lista; una tarea no listada no tiene partición (propiedad en T13)
  - Verify: `... -k test_reads_the_partition_of_each_task`
  - Depends on: —

- [x] **T12** El lector expande rangos de tareas y lee celdas en negrita · `behavior` · Risk: medium · Covers: R3.8
  - Rounds: spec 1 · code 1 · escalations 0
  - Test: `P/hooks/tests/test_tasks_document.py::test_expands_task_ranges_and_reads_bold_cells`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Invariants: un rango `Ta–Tb` cubre exactamente de a a b (propiedad en T13)
  - Verify: `... -k test_expands_task_ranges_and_reads_bold_cells`
  - Depends on: T11

- [x] **T13** Cada tarea toma la primera fila que la lista, y un rango cubre exactamente sus límites · `property` · Risk: medium · Covers: R3.1, R3.8
  - Rounds: spec 1 · code 1 · escalations 0
  - Test: `P/hooks/tests/test_tasks_document.py::test_partitions_follow_the_first_row_and_ranges_cover_their_bounds`
  - Generator domain: 300 tablas con `random.Random(11)`: hasta 5 filas, IDs T1–T60 en listas y rangos con separadores `–`, `—`, `-`, `..` y `to`, con y sin negrita
  - Invariants: la asignación coincide con un cálculo directo de "primera fila que lista la tarea"; un rango con a > b no asigna nada
  - Files: `P/hooks/scripts/tasks_document.py` (sin cambios esperados)
  - Verify: `... -k test_partitions_follow_the_first_row_and_ranges_cover_their_bounds`
  - Depends on: T12

- [x] **T14** El lector lee la línea `Parallel:` del encabezado · `behavior` · Risk: low · Covers: R3.6
  - Rounds: spec 1 · code 1 · escalations 0
  - Test: `P/hooks/tests/test_tasks_document.py::test_reads_whether_partitions_run_in_parallel`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Verify: `... -k test_reads_whether_partitions_run_in_parallel`
  - Depends on: T11

- [x] **T15** La plantilla de tasks.md tiene slices con su tabla de particiones y las líneas Parallel y Checkpoints, y se lee completa · `behavior` · Risk: low · Covers: R2.1, R3.1, R4.5
  - Test: `P/hooks/tests/test_tasks_document.py::test_the_writing_plans_template_parses` (toda tarea tiene slice y partición; `parallel` es falso)
  - Files: `P/skills/writing-plans/templates/tasks.md` (modify)
  - Verify: `... -k test_the_writing_plans_template_parses`
  - Depends on: T11, T14
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T16** writing-plans parte cada slice en particiones y oleadas con reglas comprobables · `behavior` · Risk: low · Covers: R3.1
  - Test: `P/hooks/tests/contract/test_skills.py::test_writing_plans_partitions_each_slice` (a lo sumo tres particiones por oleada; sin dependencias ni archivos compartidos dentro de una oleada salvo tasks.md y evidence; regla de manifiesto y lockfile; IDs de partición únicos en la feature; puntos de autorrevisión)
  - Files: `P/skills/writing-plans/SKILL.md` (modify)
  - Verify: `... -k test_writing_plans_partitions_each_slice`
  - Depends on: T15
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T17** Al iniciar sesión, el hook muestra la siguiente tarea de cada partición durante una oleada en paralelo · `behavior` · Risk: low · Covers: R3.7
  - Rounds: spec 1 · code 1 · escalations 0
  - Test: `P/hooks/tests/test_session_doctor.py::test_names_each_partitions_next_task_when_they_run_in_parallel`
  - Files: `P/hooks/scripts/session_doctor.py` (modify)
  - Verify: `... -k test_names_each_partitions_next_task_when_they_run_in_parallel`
  - Depends on: T14

- [x] **T18** Los commits de una tarea se buscan por ID exacto · `behavior` · Risk: low · Covers: R9.1
  - Test: `P/hooks/tests/contract/test_skills.py::test_task_commits_are_found_by_exact_id` (ninguna skill usa `--grep "Task: T<n>"`; develop-feature y opening-pull-requests usan `-E --grep '^Task: T<n>( |$)'`)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_task_commits_are_found_by_exact_id`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

<!-- T55–T59: agregadas el 2026-10-30 con el visto bueno del usuario, a partir de hallazgos de las
revisiones de código y de las sesiones paralelas. -->
- [x] **T55** Un rango enorme de tareas no cuelga al lector: solo cuenta las tareas del documento que caen en él · `behavior` · Risk: medium · Covers: R3.8
  - Test: `P/hooks/tests/test_tasks_document.py::test_a_huge_task_range_does_not_hang_the_reader` (una fila de particiones con `T1–T10000000000` se lee en menos de 2 segundos y asigna solo las tareas del documento entre esos límites; la prueba va junto a `test_expands_task_ranges_and_reads_bold_cells`, no al final del archivo)
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Invariants: un rango cubre exactamente sus límites (la propiedad de T13 sigue pasando)
  - Verify: `... -k test_a_huge_task_range_does_not_hang_the_reader`
  - Depends on: T12, T13
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S4: construcción en paralelo dentro de un slice

<!-- T56 entró en a798166 y se revirtió en 61cad85: en una sesión de worktree, la auditoría de
subagentes fotografiaba la copia principal en SubagentStart y comparaba y restauraba en el worktree en
SubagentStop. T70 hace que la auditoría use una sola raíz por subagente; T56 vuelve a entrar después.
Agregadas el 2026-10-30 por la sesión principal con el permiso del usuario para decidir. -->
- [x] **T70** La auditoría de subagentes compara y restaura solo en el árbol que fotografió al empezar · `behavior` · Risk: high · Covers: R3.3
  - Test: `P/hooks/tests/test_audit_subagent_changes.py::test_audit_restores_only_in_the_tree_it_snapshotted` (un SubagentStart y un SubagentStop del mismo subagente que resuelven raíces distintas —copia principal y worktree enlazado reales en carpetas temporales— no restauran ni borran nada en ningún árbol; con la misma raíz, todo sigue como hoy)
  - Files: `P/hooks/scripts/audit_subagent_changes.py` (modify: el registro guarda la raíz de SubagentStart y SubagentStop usa esa), `P/hooks/scripts/hook_state.py` (si hace falta)
  - Invariants: para cualquier par de eventos de un subagente, la auditoría compara y restaura solo dentro del árbol que fotografió al empezar (propiedad en el mismo test sobre raíces generadas con `random.Random(23)`)
  - Mutation: `uvx --from mutmut mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/audit_subagent_changes.py` (mutmut no corre en Windows nativo: dejarlo registrado en la evidencia)
  - Security: la auditoría restaura y borra archivos de un árbol de trabajo (Threats: Sesión en un worktree → gates del plugin)
  - Evidence: `specs/001-guided-slice-delivery/evidence/T70.md` con los hooks SubagentStart y SubagentStop corridos sobre un worktree enlazado real (eventos armados a mano) y el árbol sin cambios después
  - Verify: `... -k test_audit_restores_only_in_the_tree_it_snapshotted`
  - Depends on: —
  - Rounds: spec 1 · code 2 · escalations 0

- [x] **T56** Los gates de una sesión que trabaja en un worktree revisan ese worktree, no la copia principal · `behavior` · Risk: medium · Covers: R3.3
  - Test: `P/hooks/tests/test_project_paths.py::test_project_root_is_the_worktree_the_session_works_in` (con un repositorio y un worktree enlazado reales en carpetas temporales: con `CLAUDE_PROJECT_DIR` en la copia principal y el `cwd` del evento dentro del worktree, la raíz es el worktree; con el `cwd` dentro de la copia principal o fuera del repositorio, la raíz sigue siendo `CLAUDE_PROJECT_DIR`)
  - Files: `P/hooks/scripts/project_paths.py` (modify)
  - Invariants: la raíz es el worktree enlazado del mismo repositorio que contiene el `cwd`, y si no hay ninguno, `CLAUDE_PROJECT_DIR` (propiedad en el mismo test: 40 subcarpetas generadas con `random.Random(17)` entre las tres zonas)
  - Verify: `... -k test_project_root_is_the_worktree_the_session_works_in`
  - Depends on: T70
  - Rounds: spec 3 · code 1 · escalations 0

- [x] **T19** Al aprobar el plan, develop-feature pregunta aparte por el paralelo y guarda la respuesta · `behavior` · Risk: low · Covers: R3.2, R3.6
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_asks_about_parallel_partitions_once`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_develop_feature_asks_about_parallel_partitions_once`
  - Depends on: T16
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T20** Una sesión de partición construye solo su partición y deja su informe · `behavior` · Risk: low · Covers: R3.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_a_partition_session_builds_only_its_partition` (`--partition P<n>` en el argument-hint; nunca edita design, requirements ni otras particiones; informe `evidence/P<k>.md`; nunca hace push; PLAN CHANGE la detiene con `BLOCKED:`)
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_a_partition_session_builds_only_its_partition`
  - Depends on: T19
  - Rounds: spec 2 · code 1 · escalations 0

- [x] **T21** develop-feature integra las particiones de una oleada de a una, con el check después de cada una, desde worktrees fuera del proyecto · `behavior` · Risk: low · Covers: R3.3, R9.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_parallel_partitions_integrate_one_at_a_time` (sección `## Parallel partitions`: `git worktree add ../<repo>-worktrees/`, ramas `wave/`, primera partición en la sesión principal, cherry-pick desde el merge-base, check tras cada partición, arreglo de integración revisado con la línea `Task:` y tipo feat o refactor, revisión de código cruzada al final, `git worktree remove` nunca con `--force`, borrar la rama solo con todos los commits de tarea integrados)
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_parallel_partitions_integrate_one_at_a_time`
  - Depends on: T20
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T22** Un conflicto de integración fuera del plan detiene el flujo y espera al usuario · `behavior` · Risk: low · Covers: R3.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_an_integration_conflict_waits_for_the_user`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_an_integration_conflict_waits_for_the_user`
  - Depends on: T21
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T23** Al retomar con una oleada sin terminar, se termina primero, juzgando por los commits de tarea · `behavior` · Risk: low · Covers: R3.5, R3.6
  - Test: `P/hooks/tests/contract/test_flows.py::test_resume_finishes_an_unfinished_wave_first`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_resume_finishes_an_unfinished_wave_first`
  - Depends on: T21
  - Rounds: spec 4 · code 2 · escalations 0

- [x] **T24** Un plan sin tablas de particiones construye sus slices en orden, como antes · `behavior` · Risk: low · Covers: R2.6
  - Test: `P/hooks/tests/contract/test_flows.py::test_plans_without_partitions_run_in_list_order`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_plans_without_partitions_run_in_list_order`
  - Depends on: T21
  - Rounds: spec 2 · code 1 · escalations 0

## Slice S5: pausa por slice, decisiones y resumen de slice

- [x] **T25** El plan propone decisiones de diseño con opciones y recomendación, que se eligen al aprobarlo · `behavior` · Risk: low · Covers: R5.1, R5.4
  - Test: `P/hooks/tests/contract/test_skills.py::test_writing_plans_lists_design_decisions`
  - Files: `P/skills/writing-plans/SKILL.md`, `P/skills/writing-plans/templates/tasks.md` (modify)
  - Verify: `... -k test_writing_plans_lists_design_decisions`
  - Depends on: T16, T15
  - Rounds: spec 2 · code 1 · escalations 0

- [x] **T26** test-writer e implementer devuelven una decisión en vez de elegir entre enfoques no decididos · `behavior` · Risk: low · Covers: R5.2
  - Test: `P/hooks/tests/contract/test_agents.py::test_writers_return_a_decision_instead_of_choosing`
  - Files: `P/agents/test-writer.md`, `P/agents/implementer.md` (modify)
  - Verify: `... -k test_writers_return_a_decision_instead_of_choosing`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T27** develop-feature pausa la tarea y pregunta al usuario por una decisión abierta, y la registra · `behavior` · Risk: low · Covers: R5.2, R5.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_asks_the_user_for_open_decisions`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_develop_feature_asks_the_user_for_open_decisions`
  - Depends on: T26
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T28** La plantilla de resumen de slice tiene todas las secciones que pide la spec · `behavior` · Risk: low · Covers: R6.1
  - Test: `P/hooks/tests/contract/test_templates.py::test_slice_summary_template_has_every_section` (qué cambió y por qué, requisitos cubiertos, tamaño, riesgos y tareas de riesgo alto, decisiones, rondas de revisión y replanteos, orden de lectura con archivos y rangos de líneas)
  - Files: `P/skills/develop-feature/templates/slice-summary.md` (new)
  - Verify: `... -k test_slice_summary_template_has_every_section`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T29** Al terminar un slice, develop-feature escribe su resumen en un commit del slice y espera el visto bueno · `behavior` · Risk: low · Covers: R4.1, R6.1
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_pauses_after_each_slice` (sección `## Slice checkpoint`: `specs/<slug>/summaries/S<k>.md`; commit `docs(...)` con la línea `Task:` de la última tarea del slice; muestra el orden de lectura; espera el visto bueno)
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_develop_feature_pauses_after_each_slice`
  - Depends on: T28, T21
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T30** En la pausa hace dos o tres preguntas y explica las mal respondidas sin bloquear · `behavior` · Risk: low · Covers: R4.2, R4.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_slice_checkpoint_asks_comprehension_questions`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_slice_checkpoint_asks_comprehension_questions`
  - Depends on: T29
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T31** Los cambios pedidos en la pausa se vuelven tareas o un cambio de plan antes del slice siguiente · `behavior` · Risk: low · Covers: R4.4
  - Test: `P/hooks/tests/contract/test_flows.py::test_changes_asked_at_a_checkpoint_become_tasks`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_changes_asked_at_a_checkpoint_become_tasks`
  - Depends on: T29
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T32** Con checkpoints aprobados de antemano, escribe el resumen, toma la opción recomendada y sigue sin preguntar · `behavior` · Risk: low · Covers: R4.5, R5.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_pre_approved_checkpoints_do_not_stop`
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_pre_approved_checkpoints_do_not_stop`
  - Depends on: T29, T27
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T33** La descripción de la PR de cada slice usa su resumen · `behavior` · Risk: low · Covers: R6.2
  - Test: `P/hooks/tests/contract/test_skills.py::test_slice_pull_requests_use_the_slice_summary`
  - Files: `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_slice_pull_requests_use_the_slice_summary`
  - Depends on: T29
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S6: entrega final y resumen de la feature

- [x] **T34** Al terminar, develop-feature ofrece PRs apiladas por slice (por defecto) o una sola · `behavior` · Risk: low · Covers: R2.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_offers_stacked_or_single_delivery`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_develop_feature_offers_stacked_or_single_delivery`
  - Depends on: T33
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T35** Con PRs apiladas, `risk:high` va solo en las de slices con tareas de riesgo alto · `behavior` · Risk: low · Covers: R2.3
  - Test: `P/hooks/tests/contract/test_skills.py::test_stacked_delivery_labels_only_high_risk_slices`
  - Files: `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_stacked_delivery_labels_only_high_risk_slices`
  - Depends on: T34
  - Rounds: spec 3 · code 3 · escalations 0

- [x] **T36** Con una sola PR y tareas de riesgo alto, avisa antes y corre el mutation testing local · `behavior` · Risk: low · Covers: R2.4
  - Test: `P/hooks/tests/contract/test_skills.py::test_single_delivery_warns_about_risk_high`
  - Files: `P/skills/opening-pull-requests/SKILL.md`, `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_single_delivery_warns_about_risk_high`
  - Depends on: T34
  - Rounds: spec 3 · code 3 · escalations 0

- [x] **T37** Cada descripción de PR lista sus commits en orden con el ID de tarea · `behavior` · Risk: low · Covers: R2.5
  - Test: `P/hooks/tests/contract/test_skills.py::test_pull_requests_list_their_task_commits` (sección "Commits, one per task" en la skill y en la plantilla de PR; el ID sale de la línea `Task:` de cada commit)
  - Files: `P/skills/opening-pull-requests/SKILL.md`, `P/skills/setup-project/templates/pull_request_template.md` (modify)
  - Verify: `... -k test_pull_requests_list_their_task_commits`
  - Depends on: T34
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T38** La plantilla de resumen final tiene todas las secciones que pide la spec · `behavior` · Risk: low · Covers: R6.3
  - Test: `P/hooks/tests/contract/test_templates.py::test_feature_summary_template_has_every_section`
  - Files: `P/skills/develop-feature/templates/feature-summary.md` (new)
  - Verify: `... -k test_feature_summary_template_has_every_section`
  - Depends on: T28
  - Rounds: spec 3 · code 1 · escalations 0

- [x] **T39** develop-feature escribe el resumen final y cada PR lo enlaza · `behavior` · Risk: low · Covers: R6.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_writes_the_feature_summary`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_develop_feature_writes_the_feature_summary`
  - Depends on: T38, T34
  - Rounds: spec 4 · code 3 · escalations 0

- [x] **T40** Cada lote de migración y cada tarea de limpieza van en su propia rama y PR · `behavior` · Risk: low · Covers: R9.3
  - Test: `P/hooks/tests/contract/test_skills.py::test_migrations_and_cleanups_use_one_branch_per_pull_request`
  - Files: `P/skills/migrate-code/SKILL.md`, `P/skills/tidy-codebase/SKILL.md` (modify)
  - Verify: `... -k test_migrations_and_cleanups_use_one_branch_per_pull_request`
  - Depends on: T4
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T41** Reescribir la historia de una PR ya subida pide visto bueno y usa `--force-with-lease` · `behavior` · Risk: low · Covers: R9.4
  - Test: `P/hooks/tests/contract/test_skills.py::test_rewriting_pushed_history_needs_a_yes`
  - Files: `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Verify: `... -k test_rewriting_pushed_history_needs_a_yes`
  - Depends on: T34
  - Rounds: spec 2 · code 2 · escalations 0

## Slice S7: notas de mejora del plugin

- [x] **T42** El process-reviewer no puede cambiar archivos · `behavior` · Risk: medium · Covers: R7.1
  - Test: `P/hooks/tests/test_roles.py::test_read_only_roles_may_not_change_anything` (agrega `process-reviewer`)
  - Files: `P/hooks/scripts/roles.py` (modify)
  - Invariants: lo cubre la propiedad de T7, que recorre todos los roles de solo lectura
  - Verify: `... -k test_read_only_roles`
  - Depends on: T7
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T43** Existe el agente process-reviewer: solo lectura, Sonnet high, notas con evidencia y skill o agente afectado, sin código ni datos del proyecto · `behavior` · Risk: low · Covers: R1.1, R7.1, R7.3
  - Test: `P/hooks/tests/contract/test_agents.py::test_the_process_reviewer_is_a_read_only_sonnet_agent`
  - Files: `P/agents/process-reviewer.md` (new)
  - Verify: `... -k test_the_process_reviewer_is_a_read_only_sonnet_agent`
  - Depends on: T42
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T44** improvement_notes agrega notas con fecha, proyecto, feature y alcance al archivo central · `behavior` · Risk: medium · Covers: R7.2
  - Test: `P/hooks/tests/test_improvement_notes.py::test_appends_dated_notes_tagged_with_project_feature_and_scope` (la ruta es siempre `<config>/konundrm-eng/improvements.md`, aunque el proyecto o la feature tengan `/`, `..` o saltos de línea)
  - Files: `P/hooks/scripts/improvement_notes.py` (new)
  - Invariants: agregar nunca borra ni cambia lo anterior (propiedad en T45)
  - Verify: `... -k test_appends_dated_notes_tagged_with_project_feature_and_scope`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T45** Agregar notas nunca borra ni cambia las anteriores · `property` · Risk: medium · Covers: R7.2
  - Test: `P/hooks/tests/test_improvement_notes.py::test_appending_keeps_every_earlier_note`
  - Generator domain: 100 secuencias con `random.Random(13)` de 1 a 8 notas de texto imprimible
  - Invariants: después de cada agregado, el archivo empieza con su contenido anterior completo
  - Files: `P/hooks/scripts/improvement_notes.py` (sin cambios esperados)
  - Verify: `... -k test_appending_keeps_every_earlier_note`
  - Depends on: T44
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T46** Las notas se limpian: sin bloques de código y con secretos y correos tapados · `behavior` · Risk: high · Covers: R7.3
  - Test: `P/hooks/tests/test_improvement_notes.py::test_scrub_drops_code_and_redacts_secrets_and_emails`
  - Files: `P/hooks/scripts/improvement_notes.py` (modify)
  - Invariants: el texto limpio no tiene bloques de código, ni secretos que `find_secrets` detecte, ni correos (propiedad en T47)
  - Mutation: `uvx --from mutmut mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/improvement_notes.py` (mutmut no corre en Windows nativo: dejarlo registrado en la evidencia)
  - Security: contenido del proyecto que pasa al archivo central de notas, compartido entre proyectos (Threats, fila 1); la ruta nunca sale de la entrada (fila 2)
  - Evidence: `specs/001-guided-slice-delivery/evidence/T46.md` con la corrida de la CLI sobre notas que traen una clave AWS de prueba, un correo y un bloque de código, y el archivo central resultante sin ninguno de ellos
  - Verify: `... -k test_scrub_drops_code_and_redacts_secrets_and_emails`
  - Depends on: T44
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T47** Ningún texto limpio conserva un secreto, un bloque de código o un correo · `property` · Risk: high · Covers: R7.3
  - Test: `P/hooks/tests/test_improvement_notes.py::test_scrubbed_notes_never_keep_secrets_code_or_emails`
  - Generator domain: 300 textos con `random.Random(17)` que mezclan prosa, secretos de las formas que reconoce `secret_patterns`, correos y bloques de código
  - Invariants: igual que T46
  - Mutation: igual que T46
  - Security: igual que T46
  - Evidence: la misma de T46
  - Files: `P/hooks/scripts/improvement_notes.py` (sin cambios esperados)
  - Verify: `... -k test_scrubbed_notes_never_keep_secrets_code_or_emails`
  - Depends on: T46
  - Rounds: spec 3 · code 4 · escalations 0

- [x] **T48** Si el archivo central no se puede escribir, las notas quedan con la feature y se avisa · `behavior` · Risk: low · Covers: R7.4
  - Test: `P/hooks/tests/test_improvement_notes.py::test_falls_back_to_the_feature_folder_when_the_central_file_cannot_be_written`
  - Files: `P/hooks/scripts/improvement_notes.py` (modify)
  - Verify: `... -k test_falls_back_to_the_feature_folder_when_the_central_file_cannot_be_written`
  - Depends on: T44
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T49** La CLI recibe las notas por stdin, las limpia y dice dónde quedaron · `behavior` · Risk: low · Covers: R7.2, R7.4
  - Test: `P/hooks/tests/test_improvement_notes.py::test_cli_reads_notes_from_stdin_and_prints_where_they_went`
  - Files: `P/hooks/scripts/improvement_notes.py` (modify)
  - Verify: `... -k test_cli_reads_notes_from_stdin_and_prints_where_they_went`
  - Depends on: T48, T46
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T57** La limpieza trata como código los bloques `~~~` y los que se abren dentro de una viñeta o una cita · `behavior` · Risk: high · Covers: R7.3
  - Test: `P/hooks/tests/test_improvement_notes.py::test_scrub_drops_tilde_and_nested_code_blocks` (bloques con `~~~`, bloques abiertos tras `- `, `1. ` o `> `, y una línea de cierre indentada 4 espacios o más, que no cierra el bloque)
  - Files: `P/hooks/scripts/improvement_notes.py` (modify)
  - Invariants: el texto limpio no conserva ningún bloque de código (extender el generador de la propiedad de T47 con estas formas)
  - Mutation: `uvx --from mutmut mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/improvement_notes.py` (mutmut no corre en Windows nativo: dejarlo registrado en la evidencia)
  - Security: contenido del proyecto que pasa al archivo central de notas, compartido entre proyectos (Threats, fila 1)
  - Evidence: agregar a `specs/001-guided-slice-delivery/evidence/T46.md` una corrida de la CLI con un bloque `~~~` y uno dentro de una viñeta, y el archivo central resultante sin ninguno de los dos
  - Verify: `... -k test_scrub_drops_tilde_and_nested_code_blocks`
  - Depends on: T47
  - Rounds: spec 6 · code 1 · escalations 1

- [x] **T58** La limpieza tapa cualquier clave privada PEM, también las DH · `behavior` · Risk: high · Covers: R7.3
  - Test: `P/hooks/tests/test_improvement_notes.py::test_scrub_removes_every_pem_private_key_block` (`-----BEGIN DH PRIVATE KEY-----` y otras cabeceras `-----BEGIN <tipo> PRIVATE KEY-----` se quitan con todo su cuerpo)
  - Files: `P/hooks/scripts/secret_patterns.py` (modify: la cabecera de clave privada acepta cualquier tipo), `P/hooks/scripts/improvement_notes.py` (si hace falta)
  - Invariants: el texto limpio no conserva ninguna clave privada PEM (extender el generador de la propiedad de T47); el hook que bloquea escrituras con secretos detecta las mismas cabeceras (sus pruebas siguen pasando)
  - Mutation: `uvx --from mutmut mutmut run --paths-to-mutate plugins/konundrm-eng/hooks/scripts/secret_patterns.py` (mutmut no corre en Windows nativo: dejarlo registrado en la evidencia)
  - Security: contenido del proyecto que pasa al archivo central de notas (Threats, fila 1); el mismo detector decide qué escrituras se bloquean por secretos
  - Evidence: agregar a `specs/001-guided-slice-delivery/evidence/T46.md` una corrida de la CLI con una clave DH de prueba y el archivo central resultante sin ella
  - Verify: `... -k test_scrub_removes_every_pem_private_key_block`
  - Depends on: T47
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T59** La búsqueda de correos de la limpieza corre en tiempo lineal · `behavior` · Risk: medium · Covers: R7.3
  - Test: `P/hooks/tests/test_improvement_notes.py::test_scrub_handles_long_word_runs_quickly` (`"A" * 40000`, `"a." * 20000` y textos parecidos se limpian en menos de 2 segundos; hoy tardan unos 8)
  - Files: `P/hooks/scripts/improvement_notes.py` (modify)
  - Invariants: los correos siguen tapados (la propiedad de T47 sigue pasando)
  - Verify: `... -k test_scrub_handles_long_word_runs_quickly`
  - Depends on: T47
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T50** develop-feature pide notas al process-reviewer en cada pausa de slice y al final, y las guarda con el script sin tocar el plugin · `behavior` · Risk: low · Covers: R7.1, R7.5
  - Test: `P/hooks/tests/contract/test_flows.py::test_develop_feature_records_improvement_notes`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/develop-feature/reference/dispatch-prompts.md` (modify)
  - Verify: `... -k test_develop_feature_records_improvement_notes`
  - Depends on: T43, T49, T29
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S8: suite y evaluaciones

- [x] **T51** Toda prueba de contrato nombra en su docstring los requisitos que protege · `behavior` · Risk: low · Covers: R10.2
  - Test: `P/hooks/tests/contract/test_meta.py::test_every_contract_test_names_its_requirements`
  - Files: — (puede pasar al llegar: devolver CHARACTERIZATION)
  - Verify: `... -k test_every_contract_test_names_its_requirements`
  - Depends on: T50
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T52** Hay una evaluación de comportamiento por cada mecanismo nuevo con usuario · `behavior` · Risk: low · Covers: R10.3
  - Test: `P/hooks/tests/contract/test_release.py::test_each_new_mechanism_has_a_behavior_eval` (`behavior-slice-checkpoint`, `behavior-design-decision`, `behavior-slice-summary`, `behavior-feature-summary`, `behavior-improvement-notes`, cada una con `prompt.md` con frontmatter y al menos un grader con `type:`)
  - Files: `P/evals/behavior-*/prompt.md`, `P/evals/behavior-*/graders/*.md` (new)
  - Verify: `... -k test_each_new_mechanism_has_a_behavior_eval`
  - Depends on: T50
  - Rounds: spec 2 · code 2 · escalations 0

## Slice S9: pulido tras las revisiones

<!-- Agregado el 2026-10-30 por la sesión principal, con el permiso del usuario para decidir y su
pedido de ser maximalista: las sugerencias de las revisiones de código que vale la pena aplicar. -->
- [x] **T60** La prueba del rango enorme mide solo la lectura, no el arranque del intérprete · `chore` · Risk: low · Covers: R3.8
  - Files: `P/hooks/tests/test_tasks_document.py` (modify `test_a_huge_task_range_does_not_hang_the_reader`: medir `read_tasks` dentro del proceso hijo y dejar un tope externo más holgado)
  - Verify: `... -k test_a_huge_task_range_does_not_hang_the_reader`
  - Depends on: T55
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T61** Un ID con ceros a la izquierda (`T01`) coincide con `T1` en rangos y en celdas explícitas · `behavior` · Risk: low · Covers: R3.8
  - Test: `P/hooks/tests/test_tasks_document.py::test_zero_padded_ids_match_their_number`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Verify: `... -k test_zero_padded_ids_match_their_number`
  - Depends on: T55
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T62** Una línea `Parallel:` sin llenar, o con las opciones solo dentro de un comentario, se lee como no · `behavior` · Risk: low · Covers: R3.6
  - Test: `P/hooks/tests/test_tasks_document.py::test_an_unfilled_parallel_line_reads_as_no`
  - Files: `P/hooks/scripts/tasks_document.py` (modify)
  - Verify: `... -k test_an_unfilled_parallel_line_reads_as_no`
  - Depends on: T14
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T63** Al iniciar sesión, las particiones se listan por número (P2 antes que P10) y fuera de una oleada en paralelo se muestra una sola tarea · `behavior` · Risk: low · Covers: R3.7
  - Test: `P/hooks/tests/test_session_doctor.py::test_lists_partitions_by_number_and_falls_back_to_one_task`
  - Files: `P/hooks/scripts/session_doctor.py` (modify)
  - Verify: `... -k test_lists_partitions_by_number_and_falls_back_to_one_task`
  - Depends on: T17
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T64** La prueba del rethinker revisa los veredictos en la línea `Verdict:` y cuenta MultiEdit como herramienta de escritura · `chore` · Risk: low · Covers: R8.1
  - Files: `P/hooks/tests/contract/test_agents.py` (modify `test_the_rethinker_is_a_read_only_opus_max_agent`)
  - Verify: `... -k test_the_rethinker_is_a_read_only_opus_max_agent`
  - Depends on: T8
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T65** La prueba de roles de solo lectura confirma el nombre del rol antes de la denegación · `chore` · Risk: low · Covers: R8.5
  - Files: `P/hooks/tests/test_roles.py` (modify `test_read_only_roles_may_not_change_anything` y los nombres de los ayudantes de la propiedad)
  - Verify: `... -k test_read_only_roles`
  - Depends on: T42
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T66** Un intento apartado se recupera nombrando su entrada del stash por el mensaje, nunca por posición · `behavior` · Risk: low · Covers: R8.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_a_set_aside_attempt_is_recovered_by_its_stash_message` (develop-feature y fix-bug: la entrada sale de `git stash list --grep=<mensaje>`; desde T75 se aplica por su SHA (`--format=%H`), que también funciona en PowerShell; ningún `git stash apply` sin la entrada)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/fix-bug/SKILL.md` (modify)
  - Verify: `... -k test_a_set_aside_attempt_is_recovered_by_its_stash_message`
  - Depends on: T10
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T67** fix-bug corre en Opus high todo despacho del test-writer y del implementer después de un replanteo · `behavior` · Risk: low · Covers: R1.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_fix_bug_runs_dispatches_after_a_rethink_on_opus_high`
  - Files: `P/skills/fix-bug/SKILL.md` (modify)
  - Verify: `... -k test_fix_bug_runs_dispatches_after_a_rethink_on_opus_high`
  - Depends on: T10
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T68** La sección Model and effort deja de citar resultados que nada respalda · `chore` · Risk: low · Covers: —
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `npm run check` y que la frase "solved slightly more tasks" ya no esté
  - Depends on: T3
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T69** La plantilla del CI explica que `--model` y `--effort` fijan solo la sesión que orquesta · `chore` · Risk: low · Covers: R1.7
  - Files: `P/skills/setup-project/templates/claude-review.yml` (modify: un comentario YAML arriba de `claude_args:`, nunca dentro del bloque)
  - Verify: `... -k test_ci_review_runs_on_opus_at_medium_effort`
  - Depends on: T5
  - Rounds: spec 1 · code 1 · escalations 0

<!-- Agregadas el 2026-10-30 por la sesión principal (permiso del usuario para decidir): T71 por
una sugerencia de la revisión de código de T29; T72 porque en T27 un nombre de módulo repetido
(`_RECORDS`) reemplazó en silencio la regla de T19 y la dejó sin poder fallar. -->
- [x] **T71** Al retomar, un slice terminado sin el commit de su resumen hace primero su pausa · `behavior` · Risk: low · Covers: R4.1, R6.1
  - Test: `P/hooks/tests/contract/test_flows.py::test_resume_runs_a_missing_slice_checkpoint_first` (Phase 0: si todas las tareas de un slice tienen commit y falta su commit `summarize slice S<k>`, corre el Slice checkpoint antes de la primera tarea del slice siguiente)
  - Files: `P/skills/develop-feature/SKILL.md` (modify)
  - Verify: `... -k test_resume_runs_a_missing_slice_checkpoint_first`
  - Depends on: T29
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T72** Ningún archivo de pruebas de contrato define dos veces un mismo nombre de nivel de módulo · `behavior` · Risk: low · Covers: R10.2
  - Test: `P/hooks/tests/contract/test_meta.py::test_contract_tests_define_each_module_name_once` (una segunda asignación, `def` o `class` del mismo nombre reemplaza en silencio la primera y la prueba que la usaba deja de poder fallar)
  - Files: — (puede pasar al llegar: devolver CHARACTERIZATION)
  - Verify: `... -k test_contract_tests_define_each_module_name_once`
  - Depends on: T51
  - Rounds: spec 2 · code 1 · escalations 0

<!-- Agregadas el 2026-10-30 por la sesión principal con las notas de revisión de las sesiones de
S3 y de agentes (T61, T63, T66 y T68). -->
- [x] **T73** Un ID de tarea o un límite de rango con miles de dígitos no hace caer al lector · `behavior` · Risk: medium · Covers: R3.8
  - Test: `P/hooks/tests/test_tasks_document.py::test_a_task_id_with_thousands_of_digits_does_not_crash_the_reader` (un ID explícito y un límite de rango más allá del tope de 4300 dígitos de `int` en CPython: `read_tasks` no lanza y esa celda no asigna ninguna tarea)
  - Files: `P/hooks/scripts/tasks_document.py` (modify: tope de dígitos en un solo lugar)
  - Invariants: `read_tasks` nunca lanza con ningún texto de celda de partición
  - Verify: `... -k test_a_task_id_with_thousands_of_digits_does_not_crash_the_reader`
  - Depends on: T61
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T74** Al iniciar sesión, solo se listan las particiones de la oleada en curso · `behavior` · Risk: low · Covers: R3.7
  - Test: `P/hooks/tests/test_session_doctor.py::test_lists_only_the_current_wave_partitions` (con tareas pendientes en la oleada 1, las particiones de la oleada 2 no se listan; terminada la oleada 1, sí)
  - Files: `P/hooks/scripts/tasks_document.py`, `P/hooks/scripts/session_doctor.py` (modify)
  - Verify: `... -k test_lists_only_the_current_wave_partitions`
  - Depends on: T63
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T75** Los comandos que recuperan un intento apartado citan la entrada del stash, para que funcionen en PowerShell · `behavior` · Risk: low · Covers: R8.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_a_set_aside_attempt_is_recovered_by_its_stash_message` (se endurece: `git stash apply "<entry>"` con comillas, o por SHA; una entrada `stash@{…}` sin comillas o un `<n>` suelto fallan)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/fix-bug/SKILL.md` (modify)
  - Verify: `... -k test_a_set_aside_attempt_is_recovered_by_its_stash_message`
  - Depends on: T66
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T76** La sección Model and effort no contradice su tabla sobre los primeros intentos · `chore` · Risk: low · Covers: —
  - Files: `P/skills/develop-feature/SKILL.md` (modify: "First attempts on low- and medium-risk tasks run at `medium`…")
  - Verify: `npm run check`
  - Depends on: T68
  - Rounds: spec 1 · code 1 · escalations 0

## Slice S10: versión 0.6.0, README y huecos de la revisión final

<!-- Movido el 2026-10-30 por la sesión principal (permiso del usuario para decidir y su pedido de
paralelizar más): T53 y T54 pasan de S8 a este último slice, para integrar S9 mientras se escriben y
para que el changelog cubra también S9. -->
- [x] **T53** La versión es 0.6.0 y el changelog la describe · `behavior` · Risk: low · Covers: R10.1
  - Test: `P/hooks/tests/contract/test_release.py::test_version_and_changelog_agree` (la versión de plugin.json es la de la primera entrada del changelog, que nombra modelo y esfuerzo por rol, rethinker, particiones, pausas por slice, resúmenes y notas de mejora)
  - Files: `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md` (modify)
  - Verify: `... -k test_version_and_changelog_agree`
  - Depends on: T52
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T54** El README describe el flujo nuevo: agentes, pausas, entregas y notas de mejora · `chore` · Risk: low · Covers: —
  - Files: `README.md` (modify)
  - Verify: `npm run check`
  - Depends on: T53
  - Rounds: spec 2 · code 2 · escalations 0

<!-- Agregadas el 2026-10-30 por la sesión principal (permiso del usuario para decidir) con los dos
huecos que encontró la revisión de spec de toda la feature (Phase 4, paso 2). -->
- [ ] **T77** Aprobar las decisiones de antemano se registra aparte de aprobar las pausas · `behavior` · Risk: low · Covers: R5.2, R5.3
  - Test: `P/hooks/tests/contract/test_flows.py::test_pre_approved_decisions_are_recorded_apart_from_pauses` (Phase 2 registra `- **Decisions:** pre-approved` solo cuando el usuario aprobó de antemano las decisiones, y `- **Decisions:** ask` si no; Phase 3 toma la opción recomendada solo con `Decisions: pre-approved`, y con `Checkpoints: pre-approved` sola sigue pausando la tarea y preguntando; la plantilla de tasks.md trae la línea `Decisions:`; las reglas R5.3 de `test_pre_approved_checkpoints_do_not_stop` pasan a esta prueba)
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/writing-plans/templates/tasks.md`, `P/CHANGELOG.md` (modify; el README lo ajusta la integración si nombra la aprobación de decisiones)
  - Verify: `... -k test_pre_approved_decisions_are_recorded_apart_from_pauses`
  - Depends on: T32, T53

- [x] **T78** Las features en paralelo usan worktrees fuera de la carpeta del proyecto · `behavior` · Risk: low · Covers: R9.2
  - Test: `P/hooks/tests/contract/test_flows.py::test_parallel_features_use_worktrees_outside_the_project` (ningún bloque de develop-feature recomienda `claude --worktree` ni `.claude/worktrees/` como lugar donde construir; la frase sobre construir varias features a la vez dice crear cada worktree fuera de la carpeta del proyecto)
  - Files: `P/skills/develop-feature/SKILL.md` (modify; el README lo ajusta la integración si repite la recomendación)
  - Verify: `... -k test_parallel_features_use_worktrees_outside_the_project`
  - Depends on: T21
  - Rounds: spec 1 · code 2 · escalations 0

<!-- Example of a finished task, as develop-feature leaves it:
- [x] **T1** … · `behavior` · Risk: low · Covers: R1.1
  - Rounds: spec 1 · code 1 · escalations 0
-->
