---
type: llm
focus: { source: file, path: specs/001-saludo/requirements.md }
---
PASS if an acceptance criterion says that an empty or blank name returns `Hola, desconocido.` and no criterion still says it returns `Hola.` alone. FAIL if the criterion still states the old greeting, or if the new one appears only outside the acceptance criteria.
