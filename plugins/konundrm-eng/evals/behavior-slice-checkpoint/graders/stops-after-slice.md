---
type: llm
focus: last_message
---
PASS only if the final message is a pause after slice S1 that: points to the slice's summary (`specs/001-textos/summaries/S1.md`) or restates it; gives a reading order of files, each with a line range (for example `normalizar.py:1-20`); asks two or three short questions about the slice's code, each answerable from that summary and those files; and asks for the go-ahead to start S2 without making that go-ahead depend on answering the questions correctly. FAIL if any of these is missing, if it asks fewer than two or more than three questions, or if it says S2 has already started.
