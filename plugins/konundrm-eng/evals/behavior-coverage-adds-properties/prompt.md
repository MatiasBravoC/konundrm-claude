---
max_turns: 14
allowed_tools: [Read, Write, Edit, Bash, Glob, Grep, Skill]
---
Crea `textutils/slug.py` exactamente con este contenido y después cúbrelo con tests (usa pytest; puedes instalar hypothesis si no está):

```python
"""Turns titles into URL slugs."""

import re
import unicodedata


def slugify(title: str) -> str:
    """Returns a lowercase ASCII slug: words joined by single hyphens, no leading or trailing hyphen."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
```
