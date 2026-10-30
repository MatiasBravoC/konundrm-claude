---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, Task, TodoWrite]
---
/konundrm-eng:develop-feature Dos funciones de texto en Python. Primero `normalizar_espacios(texto: str) -> str`, en `normalizar.py`, que quite los espacios de los extremos y colapse cualquier secuencia de espacios en blanco en un solo espacio. Después `a_slug(texto: str) -> str`, en `slug.py`, que use `normalizar_espacios`, pase a minúsculas y reemplace los espacios por guiones. Contexto del caso: esta carpeta está vacía; antes de empezar, inicializa un repositorio git con un pyproject.toml mínimo (pytest y hypothesis como dependencias de desarrollo) y un commit inicial. No hay comando check: continúa sin gates. Usa `specs/001-textos/` como carpeta de la feature. Quiero un plan de dos slices, S1 con `normalizar_espacios` y S2 con `a_slug`, una tarea cada uno, sin particiones en paralelo. Apruebo de antemano la spec, el plan y cualquier decisión de diseño (toma la opción recomendada), sin esperar mi respuesta en esos puntos. Las pausas al terminar cada slice no están aprobadas de antemano: sigue el flujo normal en ellas. No hagas push.
