# konundrm-claude

Marketplace de plugins de Claude Code de Konundrm. Contiene un plugin, **`konundrm-eng`**, que
convierte las skills de ingeniería en un flujo fijo: especificar → planificar en entregas del
tamaño de un pull request → por cada tarea, test en rojo → implementación en verde → refactor →
revisiones → verificación según el riesgo → commit → pull request revisado por una persona. Cada
rol corre en un subagente distinto y los controles medibles los imponen hooks, no instrucciones
que el modelo pueda olvidar. La barrera final es la misma de cualquier equipo: el hook de
pre-commit, la CI y la protección de rama corren el mismo `check` (ver
[Límites conocidos](#límites-conocidos)).

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
    ├── agents/                            6 subagentes (ver tabla)
    ├── hooks/hooks.json                   controles automáticos (ver tabla)
    ├── hooks/run.sh                       lanzador: encuentra Python 3.10+ y corre el script pedido
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
| `writing-plans` | Claude o `/konundrm-eng:writing-plans` | Escribe `design.md` (con amenazas si hay riesgo alto) y `tasks.md`: tareas de 2–5 minutos con su riesgo, agrupadas en entregas del tamaño de un pull request |
| `test-driven-development` | Claude y el `test-writer` | Escribe un test en rojo (de ejemplo o de propiedad) y se detiene; exige cinco corridas verdes |
| `designing-modules` | Claude y el `implementer` | Decide qué módulo es dueño de cada responsabilidad y busca duplicados con `find_duplicates.py` |
| `adding-test-coverage` | Claude | Cubre código existente con tests de ejemplo y de propiedades; agrega mutation testing |
| `documenting-code` | Claude y el `implementer` | Doc-comments estilo Google y el encabezado de cada módulo |
| `naming-identifiers` | Claude y el `implementer` | Auditoría de nombres y renombrado seguro |
| `committing-changes` | Claude | Commits atómicos en Conventional Commits, sin emojis, solo con el check en verde |
| `opening-pull-requests` | Claude | Hace push (con permiso) y abre un pull request por entrega, apilados, con la tabla requisito → test → evidencia y el riesgo |
| `reviewing-pull-requests` | Claude, o la CI con `claude-review.yml` | Revisa un PR con los revisores del plugin y publica solo hallazgos verificados; nunca aprueba |
| `develop-feature` | Solo `/konundrm-eng:develop-feature` | Orquestador de features: encadena todo, verifica según el riesgo y termina en pull requests |
| `fix-bug` | Solo `/konundrm-eng:fix-bug` | Orquestador de bugs: reproduce, test de regresión en rojo, causa raíz, arreglo mínimo, revisiones y un commit `fix` con `Escaped-gate:` |
| `migrate-code` | Solo `/konundrm-eng:migrate-code` | Migraciones grandes: inventario determinista, receta aprobada, codemods primero, cada archivo con su gate y lotes del tamaño de un PR |
| `tidy-codebase` | Solo `/konundrm-eng:tidy-codebase` | Limpieza periódica: duplicados, silenciadores viejos, código sin uso e instrucciones desactualizadas, en cambios pequeños |
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

| Agente | Precarga | Puede editar |
| --- | --- | --- |
| `test-writer` | standards, test-driven-development | Solo archivos de test |
| `implementer` | standards, designing-modules, naming-identifiers, documenting-code | Todo menos tests y los documentos de la feature (`requirements`, `design`, `tasks`) |
| `spec-reviewer` | standards | Nada (solo lectura) |
| `code-reviewer` | standards | Nada (solo lectura) |
| `security-reviewer` | standards | Nada (solo lectura): revisa como atacante las tareas de riesgo alto, contra las amenazas de `design.md` |
| `finding-verifier` | standards | Nada (solo lectura): intenta refutar cada hallazgo Critical antes de que se corrija |

Los agentes que escriben (`test-writer`, `implementer`) usan el modelo de la sesión. Los revisores no fijan
modelo, así que con `CLAUDE_CODE_SUBAGENT_MODEL=<modelo>` revisan con un modelo distinto al que escribió
el código, lo que reduce los puntos ciegos compartidos.

### Controles automáticos (hooks)

| Hook | Cuándo | Qué hace |
| --- | --- | --- |
| `session_doctor.py` | Al iniciar la sesión, también después de compactar | Le dice a Claude el comando `check` y las features en curso con su próxima tarea, para que una sesión larga retome su lugar. Avisa si falta Git o si siguen instaladas las skills antiguas. Si no hay Python, avisa `run.sh` |
| `enforce_role_boundaries.py` | Antes de cada edición | Impone las columnas "Puede editar" de la tabla anterior según el subagente que edita (respuesta inmediata) |
| `block_secret_writes.py` | Antes de cada edición | Si el contenido trae algo con forma de credencial real (claves de AWS, GitHub, Stripe, Anthropic, OpenAI, llaves privadas…), te pregunta antes de escribirlo |
| `audit_subagent_changes.py` | Al iniciar y al terminar cada subagente | Compara el árbol de trabajo antes y después, sin importar con qué herramienta cambió (Edit, Bash, scripts). Si un rol tocó lo que no le corresponde, se lo devuelve una vez; si insiste, restaura esos archivos y avisa |
| `format_and_lint.py` | Después de cada edición | Formatea y pasa el linter al archivo con las herramientas que el proyecto ya usa (ruff, biome, prettier, eslint) y devuelve a Claude los errores que quedan |
| `gate_git_commit.py` | Antes de cada comando Bash/PowerShell | Bloquea `git commit` si el check falla, si intenta saltarse los hooks, si lo hace un subagente o si los cambios agregan un silenciador sin motivo (`# noqa`, `# type: ignore`, `eslint-disable`, un test saltado o enfocado). Pregunta si agregan algo con forma de credencial. Detecta el commit aunque venga envuelto (`env`, `sudo`, `&`, `bash -c`, `pwsh -Command`, `cmd /c`). Falla cerrado: si el propio hook se rompe, deniega el commit |
| `guard_new_dependencies.py` | Antes de cada comando Bash/PowerShell | Contra el *slopsquatting* y las dependencias riesgosas: antes de instalar o ejecutar un paquete nuevo consulta el registro público y OSV.dev. Te pide confirmación, con todos los motivos, si no existe, tiene menos de 30 días, casi no se descarga, no se pudo verificar, su última versión tiene vulnerabilidades conocidas o su licencia falta o es copyleft fuerte o de red, propietaria o no libre. Si OSV reporta esa versión como malware, bloquea el comando |
| `record_check_result.py` | Después de cada comando Bash/PowerShell | Si Claude corrió el `check` y pasó, lo recuerda: los gates no lo repiten mientras el contenido de los archivos sea el mismo |
| `quality_gate.py` | Al empezar y al terminar el turno | Si el turno cambió código, por cualquier vía, corre el check y busca silenciadores sin motivo que el turno haya agregado; si hay algo, Claude sigue trabajando (máximo 3 intentos). Ignora lo que ya estaba antes del turno |

El turno puede terminar con problemas a propósito solo cuando el mensaje final tiene una línea
`RED:` (entrega de TDD) o `BLOCKED:` (escalamiento a la persona).

Las skills también usan dos herramientas del plugin: `find_duplicates.py` (bloques de seis o más
líneas que el cambio copió de otra parte del proyecto; `--all` para todo el repo) y
`metrics_report.py` (el informe de `measure-impact`).

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
  konundrm-eng de a uno por árbol de trabajo (`develop-feature` ya lo hace). Para trabajar en
  paralelo, usa un worktree y una sesión por feature: los gates funcionan por árbol de trabajo.
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
   y el plan; después el orquestador trabaja solo hasta los commits y te pregunta antes de hacer
   push y abrir un pull request por entrega.
3. Para retomar una feature: `/konundrm-eng:develop-feature specs/003-google-login`.
4. Para cada bug: `/konundrm-eng:fix-bug #123` o la descripción del problema.
5. Para una migración grande: `/konundrm-eng:migrate-code pasar de Enzyme a Testing Library`.
6. Cada semana, o como tarea programada: `/konundrm-eng:tidy-codebase`.
7. Para ver si está sirviendo: `/konundrm-eng:measure-impact 30`.

Las demás skills también se activan solas cuando el pedido calza ("hagamos esto con TDD",
"commitea esto", "abre un PR", "revisa el PR 42", "mejora los nombres").

## Desarrollo del plugin

La CI (`.github/workflows/ci.yml`) corre todo esto en cada push y pull request, con los tests en
Linux, Windows y macOS sobre Python 3.10 y 3.13.

```bash
python -m pip install -r requirements-dev.txt
```

```bash
ruff format --check . && ruff check . && mypy
```

```bash
python -m unittest discover -s plugins/konundrm-eng/hooks/tests -t plugins/konundrm-eng/hooks
```

```bash
claude plugin eval plugins/konundrm-eng --allow-tools Bash Write Edit
```

Los casos de comportamiento escriben archivos, crean repos y hacen commits, así que necesitan
`--allow-tools`; sin ese permiso el runner los marca como "not granted". Los casos que usan
subagentes (`behavior-review-*`, `behavior-verifier-*`, `behavior-fix-bug-*`,
`behavior-develop-feature-*`) se comparan mejor con `--ablation none`, porque en el brazo sin
plugin los agentes no existen. `behavior-develop-feature-end-to-end` corre una feature completa:
es largo y caro, para antes de publicar una versión.

En Windows el runner no tiene sandbox para la shell y rechaza cualquier caso con `Bash`
concedido. Ahí usa `--allow-tools Write Edit`: los casos que necesitan git
(`behavior-commit-*`, `behavior-fix-bug-*`, `behavior-develop-feature-*`) solo pueden pasar en
Linux o macOS.

Los evals cubren tres cosas: que cada skill se active con su pedido (`triggers-*`), que no se
active la skill vecina ni ninguna en preguntas ajenas (`not-*`, `no-trigger-*`), y que las skills
críticas se comporten como prometen, evaluado por un juez LLM (`behavior-*`: TDD se detiene en
rojo, la spec entrevista antes de escribir, el commit no hace push sin permiso, el gate de commit
se respeta en vez de saltarse, un bug empieza con su test de regresión, la revisión aprueba un
cambio limpio sin inventar hallazgos, la cobertura incluye propiedades, un hallazgo falso se
refuta con evidencia y una feature completa sigue el flujo).

Para publicar un cambio, sube `version` en `plugin.json` siguiendo versionado semántico y anota el
cambio en `CHANGELOG.md`. Sin ese cambio de versión, las instalaciones existentes no se actualizan.
