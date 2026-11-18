---
runs: 1
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Write, Edit, Glob, Grep, Skill]
---
Ya está aprobado el spec que va al final de este mensaje. Para preparar el caso, guárdalo tal cual como `specs/001-tarjeta/requirements.md` y después planifiquemos cómo implementarlo y divídelo en tareas. El proyecto es nuevo y está vacío: `tarjeta.py` y `resumen.py` todavía no existen. No escribas código ni tests: muéstrame el plan y espera mi aprobación. El contenido del spec va desde la línea siguiente hasta el final del mensaje:

# Tarjeta de contacto para la terminal

- **Spec:** 001-tarjeta
- **Status:** Approved
- **Date:** 2026-11-17

## Problem

La herramienta de contactos muestra cada contacto como un diccionario crudo y no dice cuántos contactos hay por dominio de correo. Quien la usa en la terminal no puede leerlos de un vistazo.

## Goals

- Mostrar cada contacto como una tarjeta de texto legible.
- Saber cuántos contactos hay por dominio de correo.

## Non-goals

- Colores, tablas o cualquier formato que no sea texto plano.
- Validar que el correo exista.

## User stories and acceptance criteria

### US1. La tarjeta de un contacto

Como persona que usa la terminal, quiero ver cada contacto como una tarjeta de texto, para leerlo de un vistazo.

- `R1.1` WHEN se pide la tarjeta de un contacto, THE SYSTEM SHALL mostrar su nombre en la primera línea y su correo en la segunda.
- `R1.2` WHEN el contacto tiene teléfono, THE SYSTEM SHALL mostrarlo en una tercera línea con el prefijo `Tel: `.
- `R1.3` IF el contacto no tiene teléfono, THEN THE SYSTEM SHALL dejar la tarjeta en dos líneas.
- `R1.4` IF el nombre tiene más de 30 caracteres, THEN THE SYSTEM SHALL mostrar los primeros 29 seguidos de `…`.

### US2. El resumen por dominio

Como persona que administra los contactos, quiero saber cuántos hay por dominio de correo, para ver de dónde vienen.

- `R2.1` WHEN se pide el resumen de una lista de contactos, THE SYSTEM SHALL devolver cuántos contactos hay por dominio de correo, sin distinguir mayúsculas de minúsculas en el dominio, de modo que la suma de esos conteos sea igual al total de contactos.

## Constraints

- Python 3.11 con pytest y hypothesis. La presentación vive en `tarjeta.py` y el conteo en `resumen.py`; los tests van en `tests/`.
- Sin dependencias nuevas.

## Final verification

`pytest` pasa, y `python -c "from tarjeta import tarjeta; print(tarjeta({'nombre': 'Ana Soto', 'correo': 'ana@ejemplo.cl'}))"` imprime el nombre y el correo en dos líneas.
