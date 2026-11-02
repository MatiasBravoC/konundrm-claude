# Tasks: Publicar en GitHub mientras se construye una feature

- **Spec:** [requirements.md](requirements.md) · **Design:** [design.md](design.md)
- **Status:** Approved <!-- Draft → Approved → Done -->
- **Check command:** `npm run check`
- **Base commit:** `c8229a227d2ca0ce8e2bc8904f0dbbc626327285`
- **Pull request budget:** 500 changed lines of code and tests per slice (aim for 300–500; the feature's documents do not count)
- **Parallel:** no <!-- ningún slice tiene una ola de dos o más particiones -->
- **Checkpoints:** pre-approved <!-- el usuario lo aprobó con el plan (2026-11-01) -->
- **Decisions:** ask <!-- el usuario pidió que se le pregunte (2026-11-01) -->
- **Sessions:** per-slice
- **Publish:** local <!-- esta feature se construye en local y se sube solo con el sí del usuario (non-goal) -->

<!-- Rutas relativas a la raíz del repositorio; P = plugins/konundrm-eng.
Verify de una prueba: python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks -k <test_name>
("... -k <test_name>" abajo).
Alcance: las 10 tareas que el usuario aprobó el 2026-11-01 para atacar su pedido, nada más.
Las pruebas de contrato de esta feature viven en P/hooks/tests/contract/, su docstring empieza con
los IDs que protegen seguidos de "003" ("R6.1: 003 ...") y buscan solo las palabras clave de su
regla dentro de su sección, no gramáticas de oraciones. Si una prueba existente fija el texto o el
formato que una tarea cambia (líneas Task:/Covers: en los mensajes, IDs en el texto del PR, el tope
de 400), el test-writer la actualiza o la quita en el paso rojo de esa tarea. Al editar, conservar
el final de línea de cada archivo (algunos son CRLF).
Esta feature se construye con su propio flujo cargado desde el disco: desde el commit de T4, el
orquestador corre `task_ledger.py record` después de cada commit de tarea, y los commits que no
son de una tarea ya no llevan línea Task:. -->

## Slice S1: los commits hablan solo del cambio y el plugin apunta a su repositorio

- [x] **T1** `task_commits` lee la tarea y sus rondas también desde la nota del commit en `refs/notes/konundrm`, además del mensaje · `behavior` · Risk: medium · Covers: R6.2, R6.5
  - Test: `P/hooks/tests/test_task_commits.py::test_a_task_and_its_rounds_come_from_the_flow_note_too` (commit sin líneas en el mensaje y nota `Task: T2 · Covers: R1.1` + `Rounds: spec 1 · code 2 · escalations 0` → T2 con (1, 2, 0); un commit con las líneas en el mensaje se sigue encontrando)
  - Files: `P/hooks/scripts/task_commits.py` (modify: `NOTES_REF`)
  - Invariants: sin notas, el resultado es el mismo que hoy; una sola llamada a `git log`.
  - Verify: `... -k test_a_task_and_its_rounds_come_from_the_flow_note_too`
  - Depends on: —
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T2** El informe de impacto lee también de las notas qué commits son tareas y qué gate se escapó en un fix, y usa 500 líneas como tope por omisión de un PR · `behavior` · Risk: low · Covers: R6.2, R6.5, R7.4
  - Test: `P/hooks/tests/test_metrics_report.py::test_reads_flow_notes_and_defaults_to_a_500_line_budget`
  - Files: `P/hooks/scripts/metrics_report.py` (modify)
  - Verify: `... -k test_reads_flow_notes_and_defaults_to_a_500_line_budget`
  - Depends on: T1
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T3** `task_ledger.py record` pega la nota pendiente al commit recién hecho solo si su asunto es el del mensaje pendiente, y si no, sale con 1 sin cambiar nada · `behavior` · Risk: medium · Covers: R6.2, R6.4
  - Test: `P/hooks/tests/test_task_ledger.py::test_record_attaches_the_pending_note_to_the_commit_made_from_it` (con asunto igual → nota en HEAD y archivos pendientes borrados; sin nota pendiente o con otro asunto → exit 1, ni nota ni archivos cambian)
  - Files: `P/hooks/scripts/task_ledger.py` (modify)
  - Invariants: al negarse no cambia ninguna nota ni archivo pendiente.
  - Verify: `... -k test_record_attaches_the_pending_note_to_the_commit_made_from_it`
  - Depends on: T1
  - Rounds: spec 3 · code 3 · escalations 0

- [x] **T4** `task_ledger.py message` escribe el mensaje solo con el asunto y el cuerpo, y deja `Task:`, `Covers:` y `Rounds:` en la nota pendiente · `behavior` · Risk: medium · Covers: R6.1, R6.2
  - Test: `P/hooks/tests/test_task_ledger.py::test_message_keeps_flow_data_in_the_pending_note`
  - Files: `P/hooks/scripts/task_ledger.py` (modify)
  - Invariants: `message` sigue sin tocar el árbol de trabajo y se niega igual que antes ante una tarea inexistente o ya construida.
  - Verify: `... -k test_message_keeps_flow_data_in_the_pending_note`
  - Depends on: T3
  - Rounds: spec 1 · code 1 · escalations 0

- [x] **T5** develop-feature, committing-changes, fix-bug y reviewing-pull-requests hacen cada commit sin líneas del flujo: la tarea con `message` → `git commit` → `record`, al retomar se corre `record` primero, los resúmenes y demás commits del flujo con un asunto simple y sin línea `Task:` (el resumen se encuentra por su archivo), las particiones copian sus notas con `git notes copy`, el fix-bug guarda `Covers:` y `Escaped-gate:` en su nota, y las búsquedas de `Task:` y `Covers:` usan `--notes=refs/notes/konundrm` · `behavior` · Risk: medium · Covers: R6.1, R6.2, R6.3, R6.4, R9.1
  - Test: `P/hooks/tests/contract/test_flows.py::test_commits_carry_no_flow_lines_and_keep_their_data_in_notes`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/committing-changes/SKILL.md`, `P/skills/fix-bug/SKILL.md`, `P/skills/reviewing-pull-requests/SKILL.md`, `P/skills/opening-pull-requests/SKILL.md`, `P/skills/engineering-standards/SKILL.md` (§6, el trailer `Escaped-gate:`), `P/skills/measure-impact/SKILL.md` y los graders de `P/evals/` que esperan esas líneas o el asunto `summarize slice S1` (modify)
  - Invariants: ninguna instrucción pide una línea `Task:`, `Covers:`, `Rounds:` ni `Escaped-gate:` en el mensaje de un commit.
  - Verify: `... -k test_commits_carry_no_flow_lines_and_keep_their_data_in_notes`
  - Depends on: T4
  - Rounds: spec 2 · code 2 · escalations 0

- [x] **T6** El manifiesto del plugin, el README y las plantillas del marketplace y del workflow de revisión de setup-project apuntan a `MatiasBravoC/konundrm-claude`, y el README dice que el repositorio es privado · `behavior` · Risk: low · Covers: R8.1, R8.2
  - Test: `P/hooks/tests/contract/test_meta.py::test_plugin_addresses_point_to_its_repository` (ningún archivo fuera de `specs/` nombra `konundrm/konundrm-claude` ni `github.com/konundrm`)
  - Files: `P/.claude-plugin/plugin.json`, `README.md`, `P/skills/setup-project/templates/claude-settings.json`, `P/skills/setup-project/templates/claude-review.yml` (modify)
  - Verify: `... -k test_plugin_addresses_point_to_its_repository`
  - Depends on: —
  - Rounds: spec 1 · code 1 · escalations 0

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P1 | T1–T6 | — |

## Slice S2: publicar en vivo, un PR por slice en orden y su texto

- [ ] **T7** writing-plans arma slices de 300 a 500 líneas cambiadas de código y tests sin contar los documentos de la feature, con 500 de tope por omisión, y la pausa de cada slice anota sus líneas (código y tests aparte de los documentos) y avisa cuando pasa del tope, también con pausas preaprobadas · `behavior` · Risk: low · Covers: R7.1, R7.2, R7.3, R7.4, R9.1
  - Test: `P/hooks/tests/contract/test_skills.py::test_slices_aim_at_300_to_500_changed_lines`
  - Files: `P/skills/writing-plans/SKILL.md`, `P/skills/writing-plans/templates/tasks.md`, `P/skills/engineering-standards/SKILL.md`, `P/skills/develop-feature/SKILL.md`, `P/skills/develop-feature/templates/slice-summary.md`, `P/skills/opening-pull-requests/SKILL.md`, `P/skills/measure-impact/SKILL.md` y `README.md` (que todavía dicen 400) (modify)
  - Verify: `... -k test_slices_aim_at_300_to_500_changed_lines`
  - Depends on: —

- [ ] **T8** develop-feature publica en vivo cuando el plan lo dice: al aprobar el plan pregunta aparte si se publica en vivo (solo si hay remoto y `gh` ve el repositorio, si no dice qué falta) y lo registra en `- **Publish:**`; al empezar cada slice crea `feat/<NNN-slug>-s<k>` desde el slice anterior (S1 desde el commit del plan) y la sube; sube cada commit del flujo apenas lo hace; al retomar sube lo pendiente; un push que falla termina en `BLOCKED:`; nunca fuerza, y ni los subagentes ni las sesiones de partición suben · `behavior` · Risk: medium · Covers: R1.1, R1.2, R1.3, R1.4, R2.1, R2.2, R2.3, R3.1, R3.2, R3.3, R3.4, R3.5, R3.6, R9.1
  - Test: `P/hooks/tests/contract/test_flows.py::test_live_publishing_pushes_each_slice_branch_and_commit`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/writing-plans/templates/tasks.md` (línea `Publish:`), `P/agents/implementer.md`, `P/agents/test-writer.md` (modify)
  - Invariants: sin `Publish: live`, nada se sube antes de la pregunta de la Fase 4.
  - Verify: `... -k test_live_publishing_pushes_each_slice_branch_and_commit`
  - Depends on: T5

- [ ] **T9** Al terminar cada slice en vivo se abre su PR apilado sobre el del anterior (o contra la rama por defecto si la anterior ya no está), con `(k/N)` al final del título y `Merge order: k of N. Merge #<n> first.` al empezar la descripción, sin duplicar un PR abierto, con `risk:high` solo si la etiqueta existe y `BLOCKED:` si `gh` falla; la pausa y el final muestran los PR en orden, al retomar se abre el que falte, y la entrega al final de una feature local apila igual · `behavior` · Risk: medium · Covers: R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9, R9.1
  - Test: `P/hooks/tests/contract/test_flows.py::test_slices_end_in_stacked_pull_requests_in_merge_order`
  - Files: `P/skills/develop-feature/SKILL.md`, `P/skills/opening-pull-requests/SKILL.md` (modify)
  - Invariants: en modo local, la Fase 4 sigue preguntando antes de subir.
  - Verify: `... -k test_slices_end_in_stacked_pull_requests_in_merge_order`
  - Depends on: T8

- [ ] **T10** El texto del PR usa la plantilla del repositorio al pie de la letra (`.github/`, raíz o `docs/`) o las cuatro secciones fijas, en inglés, sin IDs del plan, sin la palabra slice y sin líneas del flujo; la plantilla de PR de setup-project tiene esas cuatro secciones; y la versión pasa a 0.8.0 con su changelog y el README · `behavior` · Risk: medium · Covers: R5.1, R5.2, R5.3, R5.4, R9.1, R9.2
  - Test: `P/hooks/tests/contract/test_skills.py::test_pull_request_text_follows_the_template_without_flow_data` (las pruebas que fijan IDs en el texto del PR, como `PullRequestTaskCommitsTest`, se reescriben o se quitan en el paso rojo)
  - Files: `P/skills/opening-pull-requests/SKILL.md`, `P/skills/setup-project/templates/pull_request_template.md`, `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md`, `README.md` (modify)
  - Invariants: `opening-pull-requests` sigue pidiendo un sí antes de cada push de una feature local y nunca fusiona ni aprueba.
  - Verify: `... -k test_pull_request_text_follows_the_template_without_flow_data`
  - Depends on: T9

### Partitions

| Wave | Partition | Tasks | Depends on |
| --- | --- | --- | --- |
| 1 | P2 | T7–T10 | P1 |
