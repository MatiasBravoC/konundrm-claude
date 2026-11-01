# Design: Flujo más eficiente

- **Spec:** [requirements.md](requirements.md)
- **Status:** Approved <!-- Draft → Approved → Done -->

Rutas relativas a la raíz del repositorio; `P` = `plugins/konundrm-eng`.

## Overview

Lo determinista sale de los turnos del orquestador y pasa a comandos del plugin: `task_ledger.py`
(estado de la feature, mensaje del commit de una tarea y contabilidad de la pausa) sobre un lector
nuevo de commits de tarea, `task_commits.py`, que solo mira `<base>..HEAD`. El commit de cada tarea
deja de tocar `tasks.md`: sus rondas viajan en el mensaje y la pausa del slice las pasa al plan, así
que el árbol que se commitea es el mismo que el implementer dejó en verde y el gate reutiliza ese
check (ya lo hace por contenido y por sesión; los subagentes comparten el `session_id`). Los
revisores corren en paralelo, sin check ni suite completa; cada slice termina en una sesión nueva
(app de escritorio, comando, o `run_slices.py` en la terminal); `run.sh` deja de arrancar Python
para registrar checks que no lo son; y `session_costs.py` mide una corrida desde sus transcripciones.

## Module ownership

| Responsibility | Owner module | New or extended | Why there | Covers |
| --- | --- | --- | --- | --- |
| Leer Base commit y `Covers:` de cada tarea | `P/hooks/scripts/tasks_document.py` | Extended | único lector de `tasks.md` | R1.8, R4.2 |
| Commits de tarea en `<base>..HEAD` y su trailer `Rounds:` | `P/hooks/scripts/task_commits.py` | New | `tasks_document` es un parser puro, sin Git | R1.8, R1.9, R2.8 |
| Recordar el árbol del último check verde junto al repo | `P/hooks/scripts/quality_check.py` (+ `record_check_result.py`) | Extended | dueño de "el check" y su resultado | R4.1 |
| Estado, mensaje de commit y contabilidad de la pausa | `P/hooks/scripts/task_ledger.py` | New | un comando por llamada del orquestador | R4.1–R4.6, R2.7, R2.8 |
| Próxima tarea al iniciar sesión, por commits | `P/hooks/scripts/session_doctor.py` | Extended | ya nombra la próxima tarea | R1.9 |
| Runner de Git compartido | `P/hooks/scripts/working_tree.py` | Extended | ya corre Git con timeout | R1.8 |
| Rondas por tarea en el informe de impacto | `P/hooks/scripts/metrics_report.py` | Extended | dueño del informe | R2.9 |
| Auditoría con varios revisores a la vez | `P/hooks/scripts/audit_subagent_changes.py` | Extended | dueño de la auditoría | R3.5, R3.6 |
| Encadenar sesiones headless por slice | `P/hooks/scripts/run_slices.py` | New | herramienta aparte, como `metrics_report.py` | R1.4, R1.5 |
| Reconocer la línea con que una sesión se detiene a propósito (`RED:`, `BLOCKED:`, con formato Markdown) | `P/hooks/scripts/deliberate_stops.py` | New (sale de `quality_gate.py`) | el stop gate y `run_slices` deben leerla igual (revisiones de T31) | R1.4 |
| Leer `Checkpoints:` de la cabecera del plan | `P/hooks/scripts/tasks_document.py` | Extended | único lector de `tasks.md` | R1.4 |
| Camino rápido del hook que registra checks | `P/hooks/run.sh` | Extended | el lanzador decide antes de arrancar Python | R5.1–R5.4 |
| Medir una corrida desde sus transcripciones | `P/hooks/scripts/session_costs.py` | New | no es del informe de entrega (Git/GitHub) | R6.1–R6.5 |
| Qué corre cada rol | `P/agents/{test-writer,implementer,spec-reviewer,code-reviewer,security-reviewer,finding-verifier}.md` | Extended | cada rol se define en su agente | R2.1–R2.4 |
| Flujo: revisiones en paralelo, gate, commit, pausa, sesión nueva | `P/skills/develop-feature/SKILL.md`, `reference/dispatch-prompts.md` | Extended | dueño del flujo | R1.1–R1.3, R1.6–R1.8, R2.5–R2.8, R3.1–R3.5, R4.7 |
| Línea `Sessions:` del plan | `P/skills/writing-plans/templates/tasks.md` | Extended | dueño de la cabecera del plan | R1.7 |
| Commit de tarea con el mensaje armado | `P/skills/committing-changes/SKILL.md` | Extended | dueño del modo develop-feature | R4.2, R4.3 |
| Informe de costos dentro del de impacto | `P/skills/measure-impact/SKILL.md` | Extended | dueño del informe de impacto | R6.6 |
| Versión, changelog y README | `P/.claude-plugin/plugin.json`, `P/CHANGELOG.md`, `README.md` | Extended | — | R7.2 |

**Duplicates found:** `metrics_report.py` tiene su propia regex del trailer `Task:`; pasa a importarla
de `task_commits.py` (T6). La búsqueda de commits de Phase 0 de develop-feature, sin rango, se
reemplaza por `task_ledger.py status` (T26).

## Interfaces

```python
# tasks_document.py: Task gana `covers: tuple[str, ...]`; TasksDocument gana `base_commit: str | None`.

# task_commits.py
@dataclass(frozen=True)
class TaskCommit:
    task_id: str                              # "T5" (T05 == T5, por número)
    sha: str
    rounds: tuple[int, int, int] | None       # "Rounds: spec <n> · code <n> · escalations <n>"
def task_commits(root: Path, base: str) -> dict[str, TaskCommit]  # una sola llamada a git log; GitError si falla

# quality_check.py
def remember_green_tree(root: Path, tree: str | None) -> None   # escribe <git-path konundrm-eng-green>
def green_tree(root: Path) -> str | None

# task_ledger.py (CLI: sh run.sh task_ledger.py <subcomando> ...)
#   status <tasks.md>                       → feature, plan, base; tareas con commit; próxima (o por partición);
#                                             árbol limpio/sucio; "check: green for this tree" | "not recorded"
#   message <tasks.md> T<n> --subject S --rounds "spec <n> · code <n> · escalations <n>" [--body B]
#                                           → escribe el mensaje en <git-path KONUNDRM_TASK_MSG> e imprime la ruta
#   close-slice <tasks.md> S<k>            → marca casillas y escribe Rounds desde los commits; conserva CRLF/LF
#   salida: 0 ok · 1 rechazado (tarea desconocida o ya commiteada) · 2 plan ilegible (archivo:línea en stderr)

# run_slices.py: run_slices.py specs/<NNN-slug> [--claude PATH] [--max-sessions N] [-- ARGS...]
#   corre `claude -p "/konundrm-eng:develop-feature specs/<NNN-slug>" ARGS` en bucle; última línea:
#   DONE | BLOCKED: <línea> | RED: <línea> | FAILED: exit <n> | STALLED: session <k> added no commit
#   (RED: una sesión espera la decisión de una persona). Antes de la primera sesión se niega (sale
#   con 2, sin abrir ninguna) si el plan no se lee, no está Approved o sus pausas no son pre-approved.

# session_costs.py: session_costs.py <carpeta>... [--check-pattern REGEX]
#   tabla por rol + bloque del orquestador más largo + "skipped lines: <n>"
```

Commit de una tarea (una llamada, visible para el gate):
`msg=$(sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" task_ledger.py message specs/<slug>/tasks.md T<n> --subject "..." --rounds "...") && git add -A && git commit -F "$msg"`.

## Data flow

1. `status` → próxima tarea. 2. test-writer (solo su test) → el orquestador ve el rojo.
3. implementer (test de la tarea; al final el check una vez → `record_check_result` guarda la huella
en la sesión y junto al repo). 4. El orquestador corre la verificación 5 veces en un comando.
5. spec ∥ código (∥ seguridad en riesgo alto), con la salida de las verificaciones; hallazgos → una
ronda de arreglo → re-revisiones en paralelo con hallazgos previos y lo que cambió. 6. Verificación por
riesgo. 7. `status`: si el check no está verde para este árbol, el orquestador lo corre. 8. `message` +
`git commit -F`: el gate reutiliza el verde. 9. Pausa: resumen + `close-slice` + commit (un check por
slice) → process-reviewer → preguntas (con `ask`) → sesión nueva.

## Dependency rules

`tasks_document` sigue sin Git. `task_commits` usa el runner de Git de `working_tree`;
`task_ledger`, `session_doctor` y `run_slices` dependen de `tasks_document` y `task_commits`, nunca al
revés. `quality_gate` y `run_slices` dependen de `deliberate_stops`, que solo usa `re`. Solo
librería estándar.

## Alternatives considered

- Excluir `tasks.md` de la huella del check — rechazada: un check que lintea Markdown pasaría en falso.
- Que el comando haga el commit por dentro — rechazada: el gate no ve un `git commit` dentro de un
  script (R4.3).
- Buscar el check verde en el estado de sesión del plugin — rechazada: los comandos de shell no
  reciben `CLAUDE_PLUGIN_DATA`; un archivo bajo el directorio de Git funciona desde cualquier shell.
- Volver a lanzar la sesión desde un comando de shell dentro de la sesión — rechazada: sesiones
  anidadas; en la terminal lo hace `run_slices.py` desde afuera.
- `python -S` para todos los hooks — fuera de alcance; anotada para el diagnóstico.

## Threats

| Boundary | What could go wrong | Control | Covers |
| --- | --- | --- | --- |
| `run.sh` → gate de commit y guard | el camino rápido salta el gate o el guard, o les cambia la entrada | solo aplica a `record_check_result.py`; los demás reciben stdin intacto (T4) | R5.4 |
| orquestador → `git commit` | un commit de tarea escapa al gate | `message` solo escribe el mensaje; el commit es un `git commit -F` normal (T25) | R4.3 |
| `run_slices.py` → sesiones headless | amplía permisos o sigue tras un `BLOCKED:` y entra código sin una persona | no agrega flags de permisos propios; corre solo un plan Approved con pausas pre-approved; se detiene ante BLOCKED, una decisión pendiente (`RED:`), falla o sesión sin commits, leyendo esas líneas como el stop gate (T31, T32) | R1.4, R1.5 |
| transcripciones → informe | el informe filtra prompts, código, secretos o datos personales | solo imprime conteos, tiempos y tokens; test con secretos plantados (T36) | R6.3 |

## Delivery

S1 (hooks) se puede integrar sola. S2–S3 agregan comandos que el flujo aún no usa. S4 cambia qué
corre cada rol. S5–S6 cambian el flujo y requieren S2–S3 integradas. S7 agrega la medición y S8
publica la 0.7.0. El plugin se carga desde esta copia, así que cada sesión nueva usa lo ya
integrado. Para revertir un slice se revierten sus commits; los planes viejos siguen leyéndose.

## Risks

- **Tests de contrato grandes.** En la 0.6.0, las reglas de prosa inflaron los slices. Aquí cada
  test busca solo las palabras clave de su regla en su sección.
- **Construir con el mismo plugin que se cambia.** Las sesiones posteriores a S5–S6 construyen con
  el flujo nuevo. Es una ventaja (lo prueba temprano) y un riesgo: si se rompe, se vuelve a la
  sesión única con `Sessions: single`.
- **Pipes en Windows.** El camino rápido de `run.sh` depende de cómo lee stdin. Lo decide T1, y se
  mide antes y después.
- **Comandos con comillas.** Mandar a Python todo comando con un escape JSON dejaba el camino
  rápido en el 1,7% de los comandos de la 0.6.0, porque casi todos llevan comillas. T42 decide sobre
  el texto escapado cuando la palabra del check no tiene `"`, `\` ni `/` (JSON nunca escapa letras,
  dígitos ni el resto de la puntuación), cortando el valor en la primera comilla sin escapar; si la
  tiene, cualquier escape sigue mandando a Python.
- **Fuera de alcance.** fix-bug conserva su revisión en serie. `opening-pull-requests` ya busca con
  rango.
