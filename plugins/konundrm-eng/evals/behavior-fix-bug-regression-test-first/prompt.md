---
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, Task]
---
/konundrm-eng:fix-bug El total del carrito queda negativo cuando el descuento supera la suma de los precios: total([10, 5], 20) devuelve -5 y debería devolver 0. No hay issue asociado. Para preparar el caso antes de empezar: inicializa un repositorio git en esta carpeta, crea `carrito.py` con la función `def total(precios, descuento): return sum(precios) - descuento` (en dos líneas), crea `tests/test_carrito.py` con un test de pytest que verifique que total([10, 5], 3) == 12, y haz un commit inicial con esos dos archivos.
