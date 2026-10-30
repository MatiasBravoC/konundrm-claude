---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, Task, TodoWrite]
---
/konundrm-eng:develop-feature Dos funciones de texto en Python, en `palabras.py`. Primero `es_palindromo(texto: str) -> bool`, que ignore mayúsculas, espacios y signos de puntuación. Después `contar_vocales(texto: str) -> int`, que cuente las vocales con y sin tilde. Contexto del caso: esta carpeta está vacía; antes de empezar, inicializa un repositorio git con un pyproject.toml mínimo (pytest y hypothesis como dependencias de desarrollo) y un commit inicial. No hay comando check: continúa sin gates. Usa `specs/001-palabras/` como carpeta de la feature. Quiero un plan de dos slices, S1 con `es_palindromo` y S2 con `contar_vocales`, una tarea cada uno, sin particiones en paralelo. Apruebo de antemano la spec, el plan, cualquier decisión de diseño (toma la opción recomendada) y las pausas al terminar cada slice, sin esperar mi respuesta en esos puntos; todo lo demás sigue el flujo normal hasta el final. No hagas push.
