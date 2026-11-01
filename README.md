# konundrm-claude

Marketplace de plugins de Claude Code de Konundrm. Contiene un plugin, **`konundrm-eng`**, que
convierte las skills de ingeniería en un flujo fijo: especificar → planificar en entregas del
tamaño de un pull request → por cada tarea, test en rojo → implementación en verde → refactor →
revisiones → verificación según el riesgo → commit → al cerrar cada entrega, su resumen y una
pausa para que entiendas el código antes de seguir → pull requests revisados por una persona, uno
apilado por entrega o uno solo. Las partes independientes de cada entrega se pueden construir en
paralelo, una tarea trabada se replantea en vez de reintentarse y las decisiones de diseño las
tomas tú, salvo que las apruebes de antemano y el flujo tome la opción recomendada. Cada rol corre
en un subagente distinto, con el modelo y el esfuerzo que su trabajo pide, y los controles medibles
los imponen hooks, no instrucciones que el modelo pueda olvidar.
La barrera final es la misma de cualquier equipo: el hook de pre-commit, la CI y la protección de
rama corren el mismo `check` (ver [Límites conocidos](#límites-conocidos)).

Las prácticas vienen de lo que publican las empresas que programan con IA a escala (ver
[De dónde salen las prácticas](#de-dónde-salen-las-prácticas)).

## Contenido

```
konundrm-claude/
├── .claude-plugin/marketplace.json        catálogo "konundrm"
├── .github/                               CI del plugin (lint, tipos, tests en 3 SO, validate) y Dependabot
├── pyproject.toml, requirements-dev.txt   ruff y mypy para el Python del propio plugin
└── plugins/konundrm-eng/
    ├── .claude-plugin/plugin.json         nombre y versión
    ├── CHANGELOG.md
    ├── skills/                            17 skills (ver tabla)
    ├── agents/                            8 subagentes (ver tabla)
    ├── hooks/hooks.json                   controles automáticos (ver tabla)
    ├── hooks/run.sh                       lanzador: encuentra Python 3.10+ y corre el script pedido (sin Python si el comando no puede ser el check)
    ├── hooks/scripts/                     hooks y herramientas en Python (solo librería estándar), un módulo por responsabilidad
    ├── hooks/tests/                       tests unitarios, de integración y de los scripts de las plantillas
    └── evals/                             evals de activación, de no activación y de comportamiento
```

### Skills

Los nombres siguen la convención de las [buenas prácticas de Agent Skills de Anthropic](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):
forma de gerundio para las capacidades que Claude activa solo (`writing-plans`, igual que en
[Superpowers](https://github.com/obra/superpowers)), verbo imperativo para los comandos que solo
invoca una persona (`develop-feature`, como `/init` o `/speckit.plan`) y sustantivo de rol para los
subagentes (`code-reviewer`, como en la documentación de subagentes).

| Skill | Quién la invoca | Qué hace |
| --- | --- | --- |
| `engineering-standards` | Claude y los subagentes | Fuente única: SOLID, Definition of Done, tests (propiedades, tests inestables, regresión), nombres, docs, Git y pull requests pequeños, severidad de revisión, errores, seguridad, verificación según riesgo e integridad de los gates |
| `writing-specs` | Claude o `/konundrm-eng:writing-specs` | Entrevista y escribe `requirements.md` con criterios EARS y IDs trazables |
| `writing-plans` | Claude o `/konundrm-eng:writing-plans` | Escribe `design.md` (con amenazas si hay riesgo alto) y `tasks.md`: tareas de 2–5 minutos con su riesgo, agrupadas en entregas del tamaño de un pull request y, dentro de cada una, en particiones que se pueden construir en paralelo. Deja los enfoques abiertos como decisiones, con pros, contras y una recomendación. Sube su propio esfuerzo a `xhigh` |
| `test-driven-development` | Claude y el `test-writer` | Escribe un test en rojo (de ejemplo o de propiedad) y se detiene; exige cinco corridas verdes |
| `designing-modules` | Claude y el `implementer` | Decide qué módulo es dueño de cada responsabilidad y busca duplicados con `find_duplicates.py` |
| `adding-test-coverage` | Claude | Cubre código existente con tests de ejemplo y de propiedades; agrega mutation testing |
| `documenting-code` | Claude y el `implementer` | Doc-comments estilo Google y el encabezado de cada módulo |
| `naming-identifiers` | Claude y el `implementer` | Auditoría de nombres y renombrado seguro |
| `committing-changes` | Claude | Commits atómicos en Conventional Commits, sin emojis, solo con el check en verde |
| `opening-pull-requests` | Claude | Hace push (con permiso) y abre un pull request apilado por entrega, o uno solo con todas. Arma cada descripción desde el resumen de la entrega, con la tabla requisito → test → evidencia, el riesgo y los commits de cada tarea, y enlaza el resumen de la feature |
| `reviewing-pull-requests` | Claude, o la CI con `claude-review.yml` | Revisa un PR con los revisores del plugin y publica solo hallazgos verificados; nunca aprueba |
| `develop-feature` | Solo `/konundrm-eng:develop-feature` | Orquestador de features: encadena todo, construye en paralelo si lo apruebas, replantea las tareas trabadas, se detiene tras cada entrega con su resumen, verifica según el riesgo, escribe el resumen de la feature y termina en pull requests (ver [Cómo avanza una feature](#cómo-avanza-una-feature)) |
| `fix-bug` | Solo `/konundrm-eng:fix-bug` | Orquestador de bugs: reproduce, test de regresión en rojo, causa raíz, arreglo mínimo, revisiones (con replanteo si el arreglo se traba) y un commit `fix` con `Escaped-gate:` |
| `migrate-code` | Solo `/konundrm-eng:migrate-code` | Migraciones grandes: inventario determinista, receta aprobada, codemods primero, cada archivo con su gate y lotes del tamaño de un PR, cada uno en su rama y con su pull request |
| `tidy-codebase` | Solo `/konundrm-eng:tidy-codebase` | Limpieza periódica: duplicados, silenciadores viejos, código sin uso e instrucciones desactualizadas, en cambios pequeños, cada uno en su rama y con su pull request |
| `setup-project` | Solo `/konundrm-eng:setup-project` | Prepara un repo: `check`, pre-commit con secretos, CI con Semgrep y mutación, revisión con IA, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` y protección de rama |
| `measure-impact` | Solo `/konundrm-eng:measure-impact` | Reporta si el flujo mejora la entrega: defectos escapados y de qué gate escaparon, retrabajo, gates y pull requests |

Las seis skills de cuenta que este plugin reemplazó cambiaron de nombre: `tdd` →
`test-driven-development`, `engineer` → `designing-modules`, `tester` → `adding-test-coverage`,
`documentator` → `documenting-code`, `mapper` → `naming-identifiers` y `deployer` →
`committing-changes` (el nombre anterior sugería despliegue, y la skill nunca despliega).

Todas comparten un formato: descripción en tercera persona con qué hace y cuándo usarla, una
sección **Contract** (recibe / entrega), un flujo con checklist copiable, reglas y un ejemplo. Los
detalles largos viven en archivos de referencia a un nivel de distancia.

### Subagentes

| Agente | Modelo / esfuerzo | Precarga | Puede editar |
| --- | --- | --- | --- |
| `test-writer` | `opus` / `medium` | standards, test-driven-development | Solo archivos de test |
| `implementer` | `opus` / `medium` | standards, designing-modules, naming-identifiers, documenting-code | Todo menos tests y los documentos de la feature (`requirements`, `design`, `tasks`) |
| `spec-reviewer` | `sonnet` / `high` | standards | Nada (solo lectura) |
| `code-reviewer` | `opus` / `high` | standards | Nada (solo lectura) |
| `security-reviewer` | `opus` / `xhigh` | standards | Nada (solo lectura): revisa como atacante las tareas de riesgo alto, contra las amenazas de `design.md` |
| `finding-verifier` | `opus` / `high` | standards | Nada (solo lectura): intenta refutar cada hallazgo Critical antes de que se corrija |
| `rethinker` | `opus` / `max` | standards, designing-modules | Nada (solo lectura): busca por qué una tarea trabada sigue fallando y dice qué hacer distinto |
| `process-reviewer` | `sonnet` / `high` | standards | Nada (solo lectura): propone mejoras al plugin desde el registro del flujo |

Cada agente fija su modelo y su esfuerzo en su frontmatter, en vez de heredar los de la sesión, para
gastar esfuerzo donde rinde. Los orquestadores suben el `test-writer` y el `implementer` a
`opus`/`high` en las rondas de arreglo, en las tareas de riesgo alto y después de un replanteo, y
corren en `opus`/`high` la revisión de spec de la feature completa (y la de cada tarea de riesgo
alto). La revisión de spec de cada tarea de riesgo bajo o medio corre en Sonnet, un modelo
distinto al de quienes escribieron el código, lo que reduce los puntos ciegos compartidos.
`writing-plans` sube su propio esfuerzo a `xhigh` mientras planifica; ninguna otra skill cambia el
modelo ni el esfuerzo de la sesión.

Para que esos valores se respeten, deja sin definir `CLAUDE_CODE_EFFORT_LEVEL` y
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE`. La primera pasa por encima del `effort` de cada agente y del
que fija cada despacho; con la segunda en `1`, todos los subagentes usan un solo modelo, sin
importar su `model` ni el del despacho. `CLAUDE_CODE_SUBAGENT_MODEL` es solo un valor por defecto
que el `model` de cada agente reemplaza. El esfuerzo de la sesión rige solo para la sesión
principal, la del orquestador, no para los agentes. Para cambiar el modelo o el esfuerzo de un
rol, edita el frontmatter de su agente.

### Cómo avanza una feature

- **Particiones en paralelo.** `writing-plans` cierra cada entrega con una tabla `### Partitions`
  que agrupa sus tareas en particiones (tareas que una sesión construye en orden) y olas
  (particiones sin dependencias entre sí ni archivos compartidos, salvo `tasks.md` y `evidence/`;
  como máximo tres). Después de aprobar el plan, `develop-feature` pregunta aparte si construir en
  paralelo, y lo ofrece solo si los checks y los tests end-to-end de las particiones pueden correr
  a la vez en tu máquina. Con un sí, construye la primera partición de cada ola y abre (o te da
  para abrir) una sesión por cada otra
  (`/konundrm-eng:develop-feature specs/<NNN-slug> --partition P<k>`), con su propio worktree de
  Git fuera de la carpeta del proyecto. Integra las particiones de a una, con el check después de
  cada una, se detiene ante un conflicto que no sean las casillas del plan y cierra la ola con una
  revisión de código sobre toda ella. Un plan sin esa tabla se construye en orden, como antes.
- **Replanteo.** Una tarea que falla cinco revisiones, o tres veces la misma, no se reintenta: se
  replantea. El `rethinker` explica por qué los intentos fallan y propone un enfoque nuevo, un
  ajuste o un cambio de plan; un cambio de plan espera tu aprobación. Si el intento actual se
  aparta, queda en `git stash` con un mensaje que nombra la tarea y se recupera por su SHA, nunca
  se descarta. El informe queda en `specs/<NNN-slug>/evidence/T<n>-rethink.md`. Si la tarea sigue
  fallando dos revisiones más, te pregunta. `fix-bug` hace lo mismo con un bug.
- **Decisiones de diseño contigo.** Cuando una tarea admite dos o más enfoques razonables, el plan
  te los muestra al aprobarlo, con pros, contras y una recomendación, y tú eliges. Si un subagente
  encuentra durante la construcción un enfoque que el plan dejó abierto, esa tarea se pausa hasta
  que elijas. Con `- **Decisions:** pre-approved` en el encabezado de `tasks.md` (queda así solo si
  apruebas de antemano las decisiones, aparte de las pausas) toma la opción recomendada y la
  registra como `(recommended)`. Cada decisión queda registrada en `tasks.md` y los resúmenes la
  citan.
- **Pausa por entrega.** Al cerrar cada entrega, el orquestador escribe y commitea su resumen,
  `specs/<NNN-slug>/summaries/S<k>.md`: qué cambió y por qué, requisitos, tamaño, riesgos,
  decisiones, rondas de revisión y replanteos, y un orden de lectura con archivos y líneas. Te lo
  muestra, te hace dos o tres preguntas sobre el código de la entrega y, si una respuesta está
  mal, explica la correcta con archivo y líneas. Espera tu visto bueno, que nunca depende de las
  respuestas; lo que pidas cambiar ahí pasa a ser tareas nuevas o un cambio de plan aprobado antes
  de la entrega siguiente. Con `- **Checkpoints:** pre-approved` en el encabezado de `tasks.md`
  (queda así si apruebas las pausas al pedir la feature o con el plan) escribe el resumen y pasa a
  la entrega siguiente sin detenerse ni preguntarte. Aprobar las pausas no aprueba las decisiones:
  sin `- **Decisions:** pre-approved`, una decisión abierta sigue pausando su tarea.
- **Una sesión nueva por entrega.** Terminada la pausa, la feature sigue en una sesión nueva por
  entrega, que retoma desde el plan y el repositorio, así el costo de cada turno no crece con la
  feature. En la app de escritorio el orquestador la abre en la misma carpeta; en otro lado, la
  sesión termina con el comando exacto para seguir:
  `claude "/konundrm-eng:develop-feature specs/<NNN-slug>"`. Si quedan archivos sin commitear, se
  detiene con una línea `BLOCKED:` que los nombra. Con `- **Sessions:** single` en el encabezado de
  `tasks.md` (si lo pides al pedir la feature, al aprobar el plan o en una pausa) la feature sigue
  en la misma sesión; `per-slice` es el valor por defecto.
- **Un check por tarea y revisiones a la vez.** Cada tarea corre el check completo una vez, salvo
  que algo cambie después de pasar, y sus revisiones de spec, de código y de seguridad corren al
  mismo tiempo, con una sola ronda de arreglo para todos sus hallazgos.
- **Resumen de la feature.** Al final escribe `specs/<NNN-slug>/summary.md`: el problema, qué
  módulo es dueño de qué, los resúmenes de cada entrega, las decisiones, los requisitos con sus
  tests y evidencia, los replanteos, los hallazgos refutados, las sugerencias no aplicadas y cómo
  probar la feature.
- **Entrega.** Después de la verificación final, y solo si apruebas el push, te ofrece un pull
  request apilado por entrega (por defecto) o uno solo con todas. Apilados, `risk:high` va solo en
  las entregas con una tarea de riesgo alto; con uno solo y alguna tarea de riesgo alto, avisa
  antes que `risk:high` cubrirá la feature completa. Cada descripción sale del resumen de su
  entrega y enlaza el resumen de la feature.
- **Notas de mejora.** Al cerrar cada entrega y al final de la feature, el `process-reviewer`
  lee el registro del flujo (rondas de revisión, escalamientos, replanteos, subagentes bloqueados,
  eventos de los gates y tus correcciones) y propone mejoras al plugin, cada una con su evidencia.
  `improvement_notes.py` las guarda, sin código, secretos ni correos, en un archivo común a todos
  tus proyectos: `~/.claude/konundrm-eng/improvements.md` (o bajo `CLAUDE_CONFIG_DIR`, en
  `konundrm-eng/improvements.md`, si está definida). Si no puede escribirlo, las deja en
  `specs/<NNN-slug>/improvement-notes.md` y te avisa. Nada las aplica al plugin por sí solo: tú
  decides cuáles llevar a un cambio.

### Controles automáticos (hooks)

| Hook | Cuándo | Qué hace |
| --- | --- | --- |
| `session_doctor.py` | Al iniciar la sesión, también después de compactar | Le dice a Claude el comando `check` y las features en curso con su próxima tarea (con particiones en paralelo, la próxima de cada partición de la ola en curso), para que una sesión larga retome su lugar. Avisa si falta Git o si siguen instaladas las skills antiguas. Si no hay Python, avisa `run.sh` |
| `enforce_role_boundaries.py` | Antes de cada edición | Impone las columnas "Puede editar" de la tabla anterior según el subagente que edita (respuesta inmediata) |
| `block_secret_writes.py` | Antes de cada edición | Si el contenido trae algo con forma de credencial real (claves de AWS, GitHub, Stripe, Anthropic, OpenAI, llaves privadas…), te pregunta antes de escribirlo |
| `audit_subagent_changes.py` | Al iniciar y al terminar cada subagente | Compara el árbol de trabajo antes y después, sin importar con qué herramienta cambió (Edit, Bash, scripts), solo en el árbol que fotografió al iniciar el subagente (el worktree de la sesión). Si un rol tocó lo que no le corresponde, se lo devuelve una vez; si insiste, restaura esos archivos y avisa |
| `format_and_lint.py` | Después de cada edición | Formatea y pasa el linter al archivo con las herramientas que el proyecto ya usa (ruff, biome, prettier, eslint) y devuelve a Claude los errores que quedan |
| `gate_git_commit.py` | Antes de cada comando Bash/PowerShell | Bloquea `git commit` si el check falla, si intenta saltarse los hooks, si lo hace un subagente o si los cambios agregan un silenciador sin motivo (`# noqa`, `# type: ignore`, `eslint-disable`, un test saltado o enfocado). Pregunta si agregan algo con forma de credencial. Detecta el commit aunque venga envuelto (`env`, `sudo`, `&`, `bash -c`, `pwsh -Command`, `cmd /c`). Falla cerrado: si el propio hook se rompe, deniega el commit |
| `guard_new_dependencies.py` | Antes de cada comando Bash/PowerShell | Contra el *slopsquatting* y las dependencias riesgosas: antes de instalar o ejecutar un paquete nuevo consulta el registro público y OSV.dev. Te pide confirmación, con todos los motivos, si no existe, tiene menos de 30 días, casi no se descarga, no se pudo verificar, su última versión tiene vulnerabilidades conocidas o su licencia falta o es copyleft fuerte o de red, propietaria o no libre. Si OSV reporta esa versión como malware, bloquea el comando |
| `record_check_result.py` | Después de cada comando Bash/PowerShell | Si Claude corrió el `check` y pasó, lo recuerda: los gates no lo repiten mientras el contenido de los archivos sea el mismo. Para un comando que no puede ser el check, `run.sh` responde sin arrancar Python |
| `quality_gate.py` | Al empezar y al terminar el turno | Si el turno cambió código, por cualquier vía, corre el check y busca silenciadores sin motivo que el turno haya agregado; si hay algo, Claude sigue trabajando (máximo 3 intentos). Ignora lo que ya estaba antes del turno |

El turno puede terminar con problemas a propósito solo cuando el mensaje final tiene una línea
`RED:` (entrega de TDD) o `BLOCKED:` (escalamiento a la persona).

Las skills también usan seis herramientas del plugin: `find_duplicates.py` (bloques de seis o más
líneas que el cambio copió de otra parte del proyecto; `--all` para todo el repo),
`metrics_report.py` (el informe de `measure-impact`), `improvement_notes.py` (guarda las notas de
mejora del `process-reviewer`, ver [Cómo avanza una feature](#cómo-avanza-una-feature)),
`task_ledger.py` (la contabilidad del flujo en una llamada: la próxima tarea, el mensaje del commit
de cada tarea y las casillas al cerrar una entrega), `run_slices.py` (encadena las sesiones de una
feature, ver [Uso](#uso)) y `session_costs.py` (lo que costó una corrida, por rol).

Los gates que bloquean, preguntan o restauran algo dejan un evento en un log local por proyecto
(en los datos del plugin, nunca en el repo), que `/konundrm-eng:measure-impact` cruza con el
historial de Git, las rondas de revisión de `specs/*/tasks.md` y los pull requests de GitHub.

Los hooks buscan el comando de calidad en este orden: variable `KONUNDRM_CHECK_CMD`, script
`check` de `package.json`, tarea `check` de poethepoet en `pyproject.toml`, objetivo `check` de
`Makefile` o `justfile`. Las skills usan esa misma búsqueda (`quality_check.py`), así que el modelo
y los hooks nunca difieren en qué es "el check". Sin comando, el check no corre, pero los
silenciadores y las credenciales se revisan igual. `KONUNDRM_GATE=off` apaga temporalmente los
gates de calidad; el bloqueo de `--no-verify` sigue activo.

El guard de dependencias no revisa los paquetes que el proyecto ya declara o tiene en el lockfile,
los binarios locales de `npx`, los scopes de npm con registro propio en `.npmrc`, ni los nombres que
calcen con `KONUNDRM_TRUSTED_PACKAGES` (globs separados por coma, como `@konundrm/*,konundrm-*`).
`KONUNDRM_ACCEPTED_LICENSES` (globs separados por coma, como `GPL-3.0*`) lista las licencias que el
proyecto acepta, `KONUNDRM_OSV_URL` apunta a un espejo de OSV y `KONUNDRM_DEPENDENCY_GUARD=off`
apaga el guard. `KONUNDRM_PR_BUDGET` cambia el presupuesto de líneas por pull request (400).

### De dónde salen las prácticas

| Práctica | Quién la publica | Dónde está en el plugin |
| --- | --- | --- |
| Requisitos EARS → diseño → tareas trazables | Amazon Kiro, GitHub Spec Kit | `writing-specs`, `writing-plans` |
| Test primero; quien implementa no toca los tests | Spec Kit, [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | `test-writer`, `implementer` y los hooks de roles |
| Descartar tests que no pasan 5 veces seguidas | [Meta TestGen-LLM](https://arxiv.org/abs/2402.09171), Uber AutoCover | `develop-feature`, `test-driven-development` |
| Tests guiados por mutantes; propiedades desde los requisitos | Meta ACH, Kiro | Verificación por riesgo y el gate de mutación en CI |
| Revisión que verifica cada hallazgo antes de publicarlo | Uber uReview, [Anthropic Code Review](https://claude.com/blog/code-review) | `finding-verifier`, `reviewing-pull-requests` |
| IA revisando cada pull request | [Microsoft](https://devblogs.microsoft.com/engineering-at-microsoft/enhancing-code-quality-at-scale-with-ai-powered-code-reviews/) | `claude-review.yml` |
| Lotes pequeños y PRs acotados | [DORA 2025](https://cloud.google.com/blog/products/ai-machine-learning/introducing-doras-inaugural-ai-capabilities-model), [Google](https://google.github.io/eng-practices/review/developer/small-cls.html) | Entregas en `tasks.md`, `opening-pull-requests` |
| Análisis estático, secretos y dependencias antes de entregar | [GitHub Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations), Veracode | Semgrep, gitleaks/secretlint, `block_secret_writes.py`, el guard con OSV |
| Agentes que no actúan sobre texto no confiable sin una persona | Meta "Rule of Two" | La revisión en CI solo comenta y solo en PRs del propio repo |
| Migraciones con herramientas deterministas, gates y lotes | [Google](https://arxiv.org/abs/2501.06972), Airbnb, Amazon | `migrate-code` |
| Instrucciones como índice corto; linters que dicen cómo arreglar; limpieza periódica | [OpenAI](https://openai.com/index/harness-engineering/), [AGENTS.md](https://agents.md) | `AGENTS.md`, reglas de arquitectura con remedio, `tidy-codebase` |
| Medir en vez de confiar en la percepción | [METR](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/), [GitClear](https://gitclear.com/the_ai_code_quality_maintainability_gap) | `measure-impact`, `find_duplicates.py` |

### Límites conocidos

- **El gate de commit es una barrera de protección, no un sandbox.** Lee el comando antes de que
  corra; un script que invoque Git por su cuenta (o un alias como `git ci`) no se ve. Por eso el
  hook de pre-commit y la CI corren el mismo `check`, y setup-project propone la protección de rama.
- **El gate de commit falla cerrado.** Si el hook no puede correr (un error interno, un timeout o
  sin `sh` en Windows), Claude Code bloquea el comando en vez de dejarlo pasar sin revisar. Sin
  Python, `run.sh` deniega solo los comandos que mencionan un commit.
- **La auditoría de subagentes atribuye cambios por tiempo.** Corre los subagentes de
  konundrm-eng de a uno por árbol de trabajo. `develop-feature` ya lo hace, también al construir
  en paralelo: cada sesión de partición trabaja en su propio worktree, fuera de la carpeta del
  proyecto. Si abres sesiones paralelas por tu cuenta, dale a cada una su worktree fuera de la
  carpeta del proyecto: los gates revisan el worktree en que corre la sesión.
- **El gate de commit revisa el árbol de trabajo completo, no cada commit parcial.** En Python, el
  framework pre-commit sí corre el `check` sobre lo preparado de cada commit (guarda aparte el
  resto); husky y la CI revisan el árbol o la punta del pull request.
- **La detección de silenciadores lee línea por línea.** Ignora los que están dentro de un string
  en esa misma línea, pero no reconoce un docstring de varias líneas: un `# noqa` escrito como
  texto dentro de un docstring cuenta como silenciador.
- **La detección de credenciales solo reconoce formatos con prefijo fijo** (y llaves privadas).
  Un secreto sin formato reconocible lo encuentran gitleaks o secretlint en el pre-commit y
  TruffleHog en la CI.
- **El guard de dependencias consulta registros públicos.** Un índice privado configurado fuera
  del comando (`pip.conf`, `[[tool.uv.index]]`) no se detecta: sus paquetes se marcan como
  inexistentes y te pide confirmar. Decláralos en `KONUNDRM_TRUSTED_PACKAGES`.
- **mutmut no corre en Windows nativo, y el sandbox de Claude Code tampoco.** Para las tareas de
  riesgo alto en Python, la mutación se exige en el job `risk:high` de la CI (o usa WSL).
- **Las métricas son una aproximación.** "Defecto escapado" es un `fix` que toca archivos que una
  tarea cambió en los 30 días anteriores; los eventos de los gates se registran por máquina.
- **`measure-impact` no junta los eventos de los gates de sesiones paralelas.** Cada worktree
  registra los suyos por separado.
- **La mutación en CI de un pull request `risk:high` cubre todo lo que cambia**, no solo los
  archivos de sus tareas de riesgo alto.
- **`record_check_result.py` confía en que Claude Code reporta los comandos fallidos como
  `PostToolUseFailure`**, como dice su documentación y como se comprobó en Claude Code 2.1.295.
  Además ignora corridas interrumpidas, en segundo plano o con código de salida distinto de 0.
- **Claude Code rotula como "Stop hook error" el primer bloqueo del gate de fin de turno**, aunque
  sea intencional. Claude recibe el motivo como "Stop hook feedback" y sigue trabajando.

## Requisitos

- Claude Code 2.1.295 o posterior (plan Pro, Max, Team o Enterprise) y Git. En Windows, Git for
  Windows: los hooks corren con su `sh`. Sin Git Bash, el gate de commit no puede correr y Claude
  Code bloquea los comandos de shell hasta que lo instales.
- Python 3.10 o superior en el `PATH` como `python3`, `python` o `py`, para los hooks. Sin él los
  controles quedan apagados, los commits a través de Claude se deniegan y el plugin lo avisa al
  iniciar la sesión.

## Instalación

Probar en local, sin instalar:

```bash
claude plugin validate ./plugins/konundrm-eng
```

```bash
claude --plugin-dir ./plugins/konundrm-eng
```

Dentro de la sesión, `/reload-plugins` recarga los cambios que hagas a los archivos.

Instalación para todo el equipo, una vez subido el repo a GitHub: `/konundrm-eng:setup-project`
deja en cada proyecto un `.claude/settings.json` que registra el marketplace y activa el plugin;
cada persona lo recibe al confiar en la carpeta. Para instalarlo a mano:

```bash
claude plugin marketplace add konundrm/konundrm-claude
```

```bash
claude plugin install konundrm-eng@konundrm
```

Una organización con plan Team o Enterprise puede además forzarlo con la configuración
administrada de Claude Code (`enabledPlugins`, `strictKnownMarketplaces`) y medir uso y costo por
plugin, skill y agente con la telemetría OpenTelemetry de Claude Code.

### Migrar desde las skills de cuenta

Las 6 skills originales siguen activas en `~/.claude/skills/` y en tu cuenta de claude.ai. Con el
plugin instalado, desactívalas para que Claude no elija entre dos versiones de la misma skill:
mueve `~/.claude/skills/{deployer,documentator,engineer,mapper,tdd,tester}` fuera de esa carpeta y
desactiva las copias en la configuración de skills de claude.ai. Mientras sigan en
`~/.claude/skills/`, el plugin lo avisa al iniciar cada sesión; las copias de claude.ai no las
puede ver.

## Uso

1. En cada repositorio, una vez: `/konundrm-eng:setup-project`. Deja el comando `check`, las
   reglas de arquitectura, pre-commit, CI, `AGENTS.md`, `CLAUDE.md` y la configuración del equipo.
2. Para cada feature: `/konundrm-eng:develop-feature agregar login con Google`. Aprobarás la spec
   y el plan, eligiendo en las decisiones de diseño que quedaron abiertas, y, si hace falta, dirás
   si construir en paralelo. Después el orquestador trabaja solo y se detiene tras cada entrega
   para mostrarte su resumen y hacerte unas preguntas, salvo que hayas aprobado las pausas de
   antemano; la entrega siguiente sigue en una sesión nueva. Al final te pregunta antes de hacer
   push y te deja elegir entre un pull request apilado por entrega o uno solo (ver
   [Cómo avanza una feature](#cómo-avanza-una-feature)).
3. Para retomar una feature, o seguirla en la sesión de su próxima entrega:
   `/konundrm-eng:develop-feature specs/003-google-login`.
4. Para construir sin supervisión un plan con `- **Checkpoints:** pre-approved`, encadena desde una
   terminal las sesiones sin interfaz, una por entrega:

   ```bash
   sh plugins/konundrm-eng/hooks/run.sh run_slices.py specs/003-google-login
   ```

   Esa es la carpeta del plugin en este repositorio; en una copia instalada, la ruta está en el
   `installPath` de `~/.claude/plugins/installed_plugins.json` (bajo
   `~/.claude/plugins/cache/konundrm/konundrm-eng/<versión>`). Su última línea dice cómo terminó:
   `DONE`, `BLOCKED:`, `RED:` (una decisión te espera), `FAILED:` o `STALLED:`.
5. Para cada bug: `/konundrm-eng:fix-bug #123` o la descripción del problema.
6. Para una migración grande: `/konundrm-eng:migrate-code pasar de Enzyme a Testing Library`.
7. Cada semana, o como tarea programada: `/konundrm-eng:tidy-codebase`.
8. Para ver si está sirviendo: `/konundrm-eng:measure-impact 30`. Para medir además cuánto costó
   una corrida, por rol, en tokens y tiempo, agrega las carpetas de sus transcripciones de Claude
   Code: viven en `~/.claude/projects/`, una por proyecto, con la ruta del proyecto y cada carácter
   que no sea letra ni dígito cambiado por `-`. Una carpeta con espacios va entre comillas:

   ```text
   /konundrm-eng:measure-impact 30 "C:/Users/Ana Soto/.claude/projects/C--Users-Ana-Soto-src-tienda"
   ```

   Desde una terminal, `sh <carpeta del plugin>/hooks/run.sh session_costs.py <carpeta>...` da
   el mismo informe de costos.

Las demás skills también se activan solas cuando el pedido calza ("hagamos esto con TDD",
"commitea esto", "abre un PR", "revisa el PR 42", "mejora los nombres").

## Desarrollo del plugin

La CI (`.github/workflows/ci.yml`) corre todo esto en cada push y pull request, con los tests en
Linux, Windows y macOS sobre Python 3.10 y 3.13.

En local, `python scripts/check.py` (o `npm run check`, el comando que detectan los hooks del
plugin) corre los mismos pasos: usa ruff y mypy si están instalados y, si no, las versiones fijadas
en `requirements-dev.txt` a través de `uvx`.

```bash
python -m pip install -r requirements-dev.txt
```

```bash
ruff format --check . && ruff check . && mypy
```

```bash
python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks
```

Esos tests incluyen los de contrato de `hooks/tests/contract/`, que comprueban sin un modelo los
acuerdos entre skills, agentes y plantillas: el modelo y el esfuerzo de cada rol, sus permisos,
cada paso del flujo, la versión, el `CHANGELOG.md` y este README. Cada uno nombra en su docstring los
requisitos que cubre.

```bash
claude plugin eval plugins/konundrm-eng --allow-tools Bash Write Edit
```

Los casos de comportamiento escriben archivos, crean repos y hacen commits, así que necesitan
`--allow-tools`; sin ese permiso el runner los marca como "not granted". Los casos que usan
subagentes (`behavior-review-*`, `behavior-verifier-*`, `behavior-fix-bug-*`,
`behavior-develop-feature-*` y los cinco del flujo por entregas: `behavior-slice-checkpoint`,
`behavior-design-decision`, `behavior-slice-summary`, `behavior-feature-summary` y
`behavior-improvement-notes`) se comparan mejor con `--ablation none`, porque en el brazo sin
plugin los agentes no existen. `behavior-develop-feature-end-to-end` corre una feature completa:
es largo y caro, para antes de publicar una versión.

En Windows el runner no tiene sandbox para la shell y rechaza cualquier caso con `Bash`
concedido. Ahí usa `--allow-tools Write Edit`: los casos que necesitan git
(`behavior-commit-*`, `behavior-fix-bug-*`, `behavior-develop-feature-*` y los cinco del flujo
por entregas) solo pueden pasar en Linux o macOS.

Los evals cubren tres cosas: que cada skill se active con su pedido (`triggers-*`), que no se
active la skill vecina ni ninguna en preguntas ajenas (`not-*`, `no-trigger-*`), y que las skills
críticas se comporten como prometen, evaluado por un juez LLM (`behavior-*`: TDD se detiene en
rojo, la spec entrevista antes de escribir, el commit no hace push sin permiso, el gate de commit
se respeta en vez de saltarse, un bug empieza con su test de regresión, la revisión aprueba un
cambio limpio sin inventar hallazgos, la cobertura incluye propiedades, un hallazgo falso se
refuta con evidencia, una feature completa sigue el flujo, cada entrega termina en una pausa con
su resumen, una decisión abierta se te pregunta, la feature termina con su resumen y el
`process-reviewer` deja notas de mejora).

Para publicar un cambio, sube `version` en `plugin.json` siguiendo versionado semántico y anota el
cambio en `CHANGELOG.md`. Sin ese cambio de versión, las instalaciones existentes no se actualizan.
