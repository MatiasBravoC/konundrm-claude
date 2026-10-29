---
runs: 1
max_turns: 250
timeout_seconds: 3600
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, Task, TodoWrite]
---
/konundrm-eng:develop-feature Una función `aplicar_cupon(total_centavos: int, porcentaje: int) -> int` en Python que aplique un cupón de porcentaje a un total en centavos: redondea hacia abajo, rechaza porcentajes fuera de 0..100 con ValueError y nunca devuelve un total negativo. Contexto del caso: esta carpeta está vacía; antes de empezar, inicializa un repositorio git con un pyproject.toml mínimo (pytest y hypothesis como dependencias de desarrollo) y un commit inicial. No hay comando check: continúa sin gates. Apruebo de antemano la spec y el plan que propongas, sin esperar mi respuesta en esos dos puntos; todo lo demás sigue el flujo normal. No hagas push.
