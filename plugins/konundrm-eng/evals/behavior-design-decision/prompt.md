---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, Task, TodoWrite]
---
/konundrm-eng:develop-feature Una función `parsear_duracion(texto: str) -> int` en Python que convierta duraciones como `1h30m`, `45s` o `2h5m10s` a segundos y rechace con ValueError cualquier texto que no siga ese formato. Se puede implementar con una expresión regular o con un pequeño analizador que recorra el texto carácter por carácter; esa elección quiero tomarla yo. Contexto del caso: esta carpeta está vacía; antes de empezar, inicializa un repositorio git con un pyproject.toml mínimo (pytest y hypothesis como dependencias de desarrollo) y un commit inicial. No hay comando check: continúa sin gates. Usa `specs/001-duraciones/` como carpeta de la feature. Quiero un plan de un solo slice con una sola tarea, sin particiones en paralelo. Apruebo de antemano la spec que propongas y las pausas al terminar cada slice. El plan no está aprobado de antemano: muéstramelo y espera mi aprobación. No hagas push.
