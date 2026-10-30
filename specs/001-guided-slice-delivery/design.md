# Design: Entrega guiada por slices, con particiones en paralelo

- **Spec:** [requirements.md](requirements.md)
- **Status:** Approved <!-- Draft → Approved → Done -->

## Overview

El comportamiento del plugin vive en tres capas: definiciones de agentes (`agents/*.md`:
frontmatter e instrucciones), instrucciones de skills (`skills/*/SKILL.md`, sus plantillas y sus
prompts de despacho) y scripts de hooks (`hooks/scripts/*.py`, solo biblioteca estándar) con sus
tests. La feature toca las tres: el frontmatter fija modelo y esfuerzo por rol; `develop-feature`
gana las secciones Model and effort, Rethink, Parallel partitions y Slice checkpoint, y el resumen
final; `writing-plans` planifica slices con una tabla de particiones por slice y decisiones de
diseño; `opening-pull-requests` ofrece entrega apilada o única; hay dos agentes nuevos de solo
lectura (`rethinker` y `process-reviewer`); los hooks leen particiones, muestran el avance por
partición y guardan notas de mejora limpias. Una suite de contratos en `hooks/tests/contract/`
protege cada acuerdo y corre con `npm run check`. La copia de trabajo 0.6.0 revisada (una PR por
feature) aporta casi todo el texto de modelo y esfuerzo, rethinker, particiones y arreglos de
revisión; las partes de slices se rehacen.

## Module ownership

| Responsibility | Owner module | New or extended | Why there | Covers |
| --- | --- | --- | --- | --- |
| Modelo y esfuerzo de cada rol | `agents/*.md` (frontmatter) | Extended | Claude Code los lee de ahí y ganan al esfuerzo de la sesión | R1.1 |
| Sobreescritura por despacho | `skills/develop-feature/SKILL.md`; `fix-bug`, `reviewing-pull-requests`, `migrate-code` | Extended | los orquestadores despachan | R1.2–R1.4 |
| Esfuerzo al planificar | frontmatter de `skills/writing-plans/SKILL.md` | Extended | única skill que sube su esfuerzo | R1.5, R1.6 |
| Revisión de PRs en CI | `skills/setup-project/templates/claude-review.yml` | Extended | la plantilla fija los argumentos | R1.7 |
| Replanteo de tareas trabadas | `agents/rethinker.md`; secciones en `develop-feature`, `fix-bug`, `reference/dispatch-prompts.md` | New / Extended | rol propio, de solo lectura | R8.1–R8.4 |
| Roles de solo lectura | `hooks/scripts/roles.py` | Extended | registro único de roles | R8.5, R7.1 |
| Slices, particiones y decisiones en el plan | `skills/writing-plans/SKILL.md`, `templates/tasks.md` | Extended | dueño del formato del plan | R2.1, R3.1, R5.1 |
| Lectura de particiones, rangos y `Parallel:` | `hooks/scripts/tasks_document.py` | Extended | el único lector de `tasks.md` | R3.6, R3.8 |
| Avance por partición al iniciar sesión | `hooks/scripts/session_doctor.py` | Extended | ya arma ese contexto | R3.7 |
| Paralelo, sesiones de partición, integración y retoma | `develop-feature` (Phase 0, Phase 2, Parallel partitions) | Extended | orquestador | R2.6, R3.2–R3.5, R9.2 |
| Decisiones durante la construcción | `agents/test-writer.md`, `agents/implementer.md`, `develop-feature` | Extended | quien la detecta la devuelve; el orquestador pregunta | R5.2–R5.4 |
| Pausa, preguntas y resumen de slice | `develop-feature` (Slice checkpoint), `templates/slice-summary.md` | Extended / New | orquestador; la plantilla fija las secciones | R4.1–R4.5, R6.1 |
| Resumen final | `develop-feature` (Phase 4), `templates/feature-summary.md` | Extended / New | | R6.3 |
| Entrega de PRs | `skills/opening-pull-requests/SKILL.md`, `setup-project/templates/pull_request_template.md` | Extended | dueño de abrir PRs | R2.2–R2.5, R6.2, R9.4 |
| Búsqueda exacta de commits por tarea | `develop-feature`, `opening-pull-requests` | Extended | | R9.1 |
| Una rama por PR en migraciones y limpiezas | `migrate-code`, `tidy-codebase` | Extended | | R9.3 |
| Revisión del flujo para mejorar el plugin | `agents/process-reviewer.md` | New | revisor de solo lectura del registro | R7.1 |
| Guardar notas limpias en el archivo central | `hooks/scripts/improvement_notes.py` | New | determinista y testeable; reusa `secret_patterns` | R7.2–R7.4 |
| Detección de claves privadas PEM de cualquier tipo | `hooks/scripts/secret_patterns.py` | Extended | detector único de secretos; también lo usa el hook que bloquea escrituras | R7.3 |
| Raíz del proyecto para los gates de una sesión en worktree | `hooks/scripts/project_paths.py` | Extended | todos los hooks la usan para saber qué árbol revisar | R3.3 |
| Una sola raíz por subagente en la auditoría | `hooks/scripts/audit_subagent_changes.py` | Extended | el registro de SubagentStart ya guarda la foto; guarda también su raíz | R3.3 |
| Pedir y guardar notas en el flujo | `develop-feature` (Slice checkpoint, Phase 4) | Extended | | R7.1, R7.5 |
| Suite de acuerdos | `hooks/tests/contract/` | New | entra en el `unittest discover` actual y en el CI | R10.1, R10.2 |
| Evaluaciones de comportamiento | `evals/behavior-*` (cinco nuevas) | New | formato de evals del plugin | R10.3 |
| Versión y changelog | `.claude-plugin/plugin.json`, `CHANGELOG.md` | Extended | | R10.1 |
| Documentación del flujo para quien instala el plugin | `README.md` (raíz del repo) | Extended | ya describe skills, agentes y uso | — |

**Duplicates found:** la detección de secretos ya existe en `secret_patterns.find_secrets`; la
ubicación de la configuración de Claude ya existe en `session_doctor.claude_config_directory`. Ambas
se reusan; no se escribe un detector ni una resolución de rutas nuevos.

## Interfaces

```python
# hooks/scripts/tasks_document.py (extended)
class Task:            # + partition: str | None = None   (fila de la tabla de particiones)
class TasksDocument:   # + parallel: bool = False          (línea "- **Parallel:** yes")
def read_tasks(path: Path) -> TasksDocument

# hooks/scripts/session_doctor.py (extended)
def next_step(document: TasksDocument) -> str   # "next per partition: P1 T3, P2 T2" en paralelo

# hooks/scripts/project_paths.py (extended)
def project_root(event: dict[str, Any]) -> Path  # el worktree enlazado que contiene el cwd; si no, CLAUDE_PROJECT_DIR

# hooks/scripts/improvement_notes.py (new; CLI: --project --feature --scope, notas por stdin)
NOTES_FILE = Path("konundrm-eng") / "improvements.md"            # dentro de la config de Claude
def scrub(notes: str) -> str        # quita bloques ``` y tapa secretos y correos
def append_notes(notes: str, *, project: str, feature: str, scope: str, today: date,
                 config_dir: Path, fallback_dir: Path) -> tuple[Path, bool]   # (ruta, usó respaldo)
def main(argv: list[str] | None = None) -> int
```

Contratos en Markdown:

- Encabezado de `tasks.md`: `- **Parallel:** yes | no` y `- **Checkpoints:** ask | pre-approved`.
- Cada slice termina con `### Partitions`: `| Wave | Partition | Tasks | Depends on |`; IDs de
  partición únicos en toda la feature (`P1`, `P2`…), rangos `T1–T3` permitidos.
- Campo de tarea `- Decision:` con opciones, ventajas, desventajas y recomendación; tras elegir,
  `- Decision: <opción> (user | recommended)`, con las opciones conservadas debajo para que los
  resúmenes las citen (R5.4).
- `test-writer` e `implementer` pueden devolver `Status: DECISION` con las opciones.
- Informes: `RETHINK:` del rethinker; `IMPROVEMENT NOTES:` del process-reviewer (título,
  evidencia, skill o agente afectado, cambio sugerido; nunca código ni datos del proyecto).
- Archivos: `specs/<slug>/summaries/S<k>.md`, `specs/<slug>/summary.md`,
  `specs/<slug>/evidence/P<k>.md` y `T<n>-rethink.md`; notas en
  `<config de Claude>/konundrm-eng/improvements.md` (respaldo `specs/<slug>/improvement-notes.md`).
- El resumen de un slice va en un commit `docs(<scope>): summarize slice S<k>` con la línea
  `Task:` de la última tarea del slice, para que quede dentro de la PR del slice.

## Data flow

1. Por slice: oleadas (con `Parallel: yes`, sesiones de partición; si no, en orden de lista).
2. Por tarea: red → green (Opus medium; arreglos en Opus high) → revisiones → rethink a la quinta
   revisión fallida o tercera de la misma → commit.
3. Fin de slice: integrar particiones → commit del resumen → `process-reviewer` →
   `improvement_notes.py` → pausa con orden de lectura y 2–3 preguntas (salvo `Checkpoints:
   pre-approved`) → cambios pedidos → siguiente slice.
4. Phase 4: revisión de spec de toda la feature (Opus high) → verificación final → resumen final →
   `process-reviewer` de la feature → `Status: Done` → elegir entrega apilada (por defecto) o única
   → `opening-pull-requests`.

## Dependency rules

Los scripts de hooks se importan entre sí como módulos de primer nivel (`mypy_path`).
`improvement_notes` importa `secret_patterns` y `session_doctor`; ningún hook importa
`improvement_notes`. Las pruebas de contrato leen archivos del plugin por ruta y solo importan
`tasks_document` para leer la plantilla.

## Alternatives considered

- Una PR por feature (borrador 0.6.0): descartada, `risk:high` cubriría toda la feature y la
  revisión sería enorme; queda como opción al final.
- Integrar particiones con merge commits: descartada, las PRs apiladas necesitan los commits de cada
  slice juntos; cherry-pick deja la historia lineal.
- Un agente aparte para los resúmenes: descartado, el orquestador ya tiene los registros.
- Notas en el repo del plugin o como issues de GitHub: descartado por el usuario (archivo central).
- `hypothesis` para las propiedades: no disponible (los tests de hooks usan solo la biblioteca
  estándar); se generan casos con `random` y semilla fija.
- Evals dentro del check: descartado, corren un modelo; la estructura la cubren los contratos.

## Threats

| Boundary | What could go wrong (spoofing, tampering, disclosure, denial of service, elevation) | Control | Covers |
| --- | --- | --- | --- |
| Proyecto → archivo central de notas (compartido entre proyectos) | Disclosure: secretos, código fuente o datos personales de un proyecto copiados a un archivo común | `improvement_notes.scrub` conserva las notas solo hasta la primera línea que podría abrir código (una cerca ```` ``` ```` o `~~~` tras cualquier sangría, viñeta o cita; un posible bloque HTML; código sangrado; un tab antes del contenido) y cambia el resto por `[rest omitted: it may contain code]`; tapa secretos (`find_secrets`, con claves privadas PEM de cualquier tipo) y correos, en tiempo lineal; el `process-reviewer` tiene prohibido citarlos; tests T46, T47, T57, T58 y T59 | R7.3 |
| `tasks.md` → hook de inicio de sesión | Denial of service: un rango de tareas enorme cuelga el lector al abrir la sesión | el rango solo cuenta las tareas que el documento tiene; test T55 | R3.8 |
| Sesión en un worktree → gates del plugin | Tampering: los gates revisan la copia principal, dejan pasar un commit en rojo del worktree o lo frenan por el rojo de otra sesión | `project_paths.project_root` usa el worktree enlazado que contiene el `cwd` del evento; la auditoría compara y restaura solo en la raíz que fotografió al empezar el subagente; tests T56 y T70 | R3.3 |
| Ruta del archivo de notas | Tampering: un nombre de proyecto o de feature que escriba fuera de la carpeta de configuración | Ruta fija; proyecto y feature solo van al contenido, en una línea; test T44 | R7.2 |
| Subagente → repositorio | Elevation: el rethinker o el process-reviewer cambian archivos | `READ_ONLY_ROLES` y la auditoría de subagentes; tests T6, T7 y T42 | R8.5, R7.1 |

## Delivery

Diez slices (S1–S10) como PRs apiladas sobre `main`, o una sola si el usuario lo elige. El plugin se
instala desde este directorio: cada slice integrado queda activo al recargar, así que cada uno deja
el flujo coherente. S1–S3 no cambian pasos visibles salvo modelo y esfuerzo; S4 solo actúa con
`Parallel: yes` (por defecto `no`); S5 trae la pausa junto con su plantilla de resumen; S6 la
entrega; S7 las notas; S8 la suite y los evals; S9 el pulido tras las revisiones; S10 la versión
0.6.0, el changelog y el README. Para volver atrás se revierte la PR del slice: no hay migraciones
de datos.

## Risks

- Los pasos nuevos de las instrucciones se verifican por estructura, no por comportamiento: lo
  cubren los cinco evals nuevos y la verificación final.
- Más interacción frena las corridas desatendidas: `Checkpoints: pre-approved` las mantiene en
  marcha (y deja correr los evals).
- El `process-reviewer` agrega un despacho por slice: Sonnet high, con registros y no con código.
- Finales de línea mixtos en Windows: los tests leen con saltos de línea universales y las
  ediciones conservan el final de línea de cada archivo.
- `mutmut` no corre en Windows nativo: las tareas de riesgo alto lo registran en su evidencia; el CI
  de este repo no tiene paso de mutación.
