---
max_turns: 10
allowed_tools: [Read, Write, Bash, Glob, Grep, Skill, Agent]
---
Crea `textutils/slug.py` exactamente con este contenido:

```python
"""Turns titles into URL slugs."""

import re
import unicodedata


def slugify(title: str) -> str:
    """Returns a lowercase ASCII slug: words joined by single hyphens, no leading or trailing hyphen."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
```

Un revisor dejó este hallazgo Critical: "textutils/slug.py:10 — slugify('--Hola Mundo--') devuelve '-hola-mundo-' con guiones al borde, lo que rompe las URLs". Antes de tocar nada, verifica si el hallazgo es real.
