# Design: Publicar en GitHub mientras se construye una feature

- **Spec:** [requirements.md](requirements.md)
- **Status:** Done <!-- Draft → Approved → Done -->

## Overview

Los datos del flujo del commit de cada tarea (tarea, requisitos, rondas) dejan el mensaje y pasan a
una nota de Git en `refs/notes/konundrm`, con las mismas líneas de siempre: `task_commits.py` lee
mensaje y nota con un solo `git log`, así que las features viejas siguen igual.
`task_ledger.py message` escribe el mensaje limpio y una nota pendiente, y `task_ledger.py record`
la pega al commit recién hecho. La publicación en vivo, el PR de cada slice en orden y las reglas
del texto del PR son instrucciones de `develop-feature` y `opening-pull-requests`: Claude corre
`git` y `gh` siguiéndolas (sin script ni hook nuevo, por decisión del usuario).

## Module ownership

`P` = `plugins/konundrm-eng`.

| Responsibility | Owner module | New or extended | Why there | Covers |
| --- | --- | --- | --- | --- |
| Leer la tarea y sus rondas desde el mensaje y desde la nota | `P/hooks/scripts/task_commits.py` | Extended | ya es el único lector de la historia del flujo | R6.2, R6.5 |
| Mensaje limpio con nota pendiente; `record` | `P/hooks/scripts/task_ledger.py` | Extended | ya escribe el mensaje de cada tarea | R6.1, R6.2, R6.4 |
| Informe de impacto desde las notas; tope de 500 | `P/hooks/scripts/metrics_report.py` | Extended | ya lee la historia para el informe | R6.2, R6.5, R7.4 |
| Ningún commit del flujo con líneas del flujo; notas al integrar particiones; `record` al retomar | skills `develop-feature`, `committing-changes`, `fix-bug`, `reviewing-pull-requests` | Extended | cada skill escribe sus commits | R6.1–R6.4 |
| Slices de 300–500 líneas y aviso en la pausa | `writing-plans` (y su plantilla), `engineering-standards`, `develop-feature` (y la plantilla del resumen), `opening-pull-requests` | Extended | donde se planifica, se mide y se entrega | R7.1–R7.4 |
| Publicación en vivo: pregunta, rama del slice, push de cada commit | `develop-feature` (y la plantilla de tasks.md), agentes `implementer` y `test-writer` | Extended | el orquestador es quien commitea | R1.1–R1.4, R2.x, R3.x |
| PR de cada slice, apilado y en orden, y su texto | `develop-feature`, `opening-pull-requests`, plantilla de PR de `setup-project` | Extended | `opening-pull-requests` ya abre los PR apilados | R4.x, R5.x |
| Direcciones y versión | `plugin.json`, `README.md`, plantillas `claude-settings.json` y `claude-review.yml`, `CHANGELOG.md` | Extended | — | R8.1, R8.2, R9.2 |

**Duplicates found:** las skills buscan tareas con `git log --grep '^Task: T<n>( |$)'`, la regla de
`task_commits.py`: siguen así, con `--notes=refs/notes/konundrm` (Git busca también en las notas).

## Interfaces

```text
task_commits.py   NOTES_REF = "refs/notes/konundrm"; task_commits(root, base) lee %B y %N con
                  `git log --notes=refs/notes/konundrm` en una sola llamada (firma igual que hoy)
task_ledger.py message PLAN T<n> --subject S --rounds R [--body B]
                  imprime la ruta del mensaje (asunto y cuerpo, sin líneas del flujo) y deja
                  <git-dir>/KONUNDRM_TASK_NOTE con "Task: T<n> · Covers: …" y "Rounds: …"
task_ledger.py record
                  pega la nota pendiente a HEAD si su asunto es el del mensaje pendiente y borra los
                  dos archivos; si no hay nota pendiente o el asunto no coincide, sale con 1 sin
                  cambiar nada
```

Comandos que las skills piden (los corre Claude):

- Commit de tarea: `msg=$(… message …) && git add -A && git commit -F "$msg" --trailer "…" && sh … task_ledger.py record`.
- fix-bug: `git commit …` seguido de `git notes --ref=refs/notes/konundrm add -m "Covers: B1" -m "Escaped-gate: <gate>" HEAD`.
- Partición integrada: después del cherry-pick, `git notes --ref=refs/notes/konundrm copy <original> <copia>` por commit.
- Resumen de un slice: se encuentra por su archivo, `git log --format=%H -- specs/<NNN-slug>/summaries/S<k>.md`.
- En vivo: `git switch -c feat/<NNN-slug>-s<k> <base>` y `git push -u origin feat/<NNN-slug>-s<k>` al empezar el slice; `git push` después de cada commit; `gh pr create --base <rama del slice anterior o la por defecto> --head feat/<NNN-slug>-s<k> --title "<título> (k/N)" --body-file <archivo>` al terminarlo.

## Data flow

Aprobación del plan → `git remote get-url origin` y `gh repo view` → pregunta → `- **Publish:**
live|local` → por slice (en vivo): rama y push → por tarea: `message` → commit (gate) → `record` →
`git push` → fin del slice: líneas con `git diff --shortstat` → resumen → commit → push →
`gh pr create` → pausa con los PR en orden.

## Dependency rules

Solo cambian scripts de `P/hooks/scripts` (librería estándar) y texto de skills. Ninguna
dependencia nueva entre módulos.

## Alternatives considered

- Dejar las líneas en el mensaje — rechazado por el usuario: cada commit habla solo del cambio.
- Un JSON propio bajo el directorio de Git — rechazado: necesita su propio bloqueo; las notas son
  de Git, `git log --notes --grep` las busca y los worktrees las comparten.
- Un script para publicar y hooks que bloqueen push o texto con jerga — fuera de alcance por
  decisión del usuario (non-goal): las reglas quedan en las skills.

## Threats

Ninguna tarea es de riesgo alto. La frontera nueva es Claude → remoto, y la cuidan instrucciones:

| Boundary | What could go wrong | Control | Covers |
| --- | --- | --- | --- |
| Claude → historial remoto | un push forzado pisa commits del remoto | develop-feature y opening-pull-requests piden `git push` sin fuerza y `BLOCKED:` ante un rechazo (T8) | R3.5, R3.6 |
| subagente → remoto | un subagente sube o abre un PR | los agentes `implementer` y `test-writer` dicen que nunca suben ni abren PR; el gate ya les niega commitear (T8) | R3.6 |

## Delivery

S1 deja el flujo coherente por sí solo: el lector entiende las notas antes de que nadie las
escriba, `record` existe antes de que `message` deje de escribir las líneas, y el texto de las
skills cambia en el mismo slice. S2 agrega la publicación en vivo, que solo se activa con
`Publish: live`; un plan sin esa línea sigue local (R1.3). Para volver atrás se revierte S2 y
luego S1; una feature en curso que ya escribió notas necesita el lector de S1.

## Risks

- Una sesión cortada entre el commit y `record` deja la nota pendiente: la sesión que retoma corre
  `record` antes que nada (R6.4).
- Las notas no viajan en un clon ni con el squash de GitHub: non-goal, lo dice el README.
- La palabra "slice" queda fuera de la prosa de los PR también en proyectos que hablan de slices de
  listas: entre backticks pasa.
- Esta feature se construye con su propio flujo cargado desde el disco: T3 (`record`) va antes que
  T4 (`message` sin líneas), y desde el commit de T4 el orquestador corre `record` después de cada
  commit de tarea.
