"""Reads the plugin's own files (agents, skills) for the contract tests."""

from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = PLUGIN_ROOT / "agents"
SKILLS_DIR = PLUGIN_ROOT / "skills"


def read_frontmatter(path: Path) -> dict[str, str]:
    """Return the top-level `name: value` keys of a Markdown file's frontmatter.

    The frontmatter is the block between the first two lines that are exactly `---`. Indented lines
    (items of list values such as `skills:`) are ignored.

    Raises:
        ValueError: the file does not have two `---` fences; the message names the file.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    fences = [index for index, line in enumerate(lines) if line == "---"][:2]
    if len(fences) < 2:
        raise ValueError(f"{path}: frontmatter needs two '---' fence lines, found {len(fences)}")
    fields: dict[str, str] = {}
    for line in lines[fences[0] + 1 : fences[1]]:
        if line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def read_section(path: Path, heading: str) -> str:
    """Return the body of a `## ` section of a Markdown file, or "" when the file lacks it.

    The body is the text after the line that is exactly `## <heading>` up to the next line that
    starts with `## ` (or the end of the file). Lines are read with universal newlines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(f"## {heading}") + 1
    except ValueError:
        return ""
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])
