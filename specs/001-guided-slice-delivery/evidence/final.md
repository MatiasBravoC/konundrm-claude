# Evidencia final: entrega guiada por slices

Fecha: 2026-10-30 · Rama: `feat/001-guided-slice-delivery` · Commit verificado: `7daed5f` (la punta antes
del commit de cierre) · Máquina: Windows 11, Git 2.55, Python 3.13, Claude Code 2.1.310.

La verificación final de [requirements.md](../requirements.md) tiene dos pasos. El primero está
automatizado y corrió entero. El segundo es una corrida interactiva que necesita a una persona y no
se corrió: sus pasos exactos están al final.

## Paso 1: check y validación del plugin (automatizado)

1. `npm run check` en la punta: `Ran 404 tests` y `All checks passed.` (lint, tipos, hooks y
   la suite de contratos nueva).
2. `claude plugin validate ./plugins/konundrm-eng`: `✔ Validation passed`. Da una advertencia del
   directorio de plugins, `ICON_MISSING` (el plugin no tiene ícono), que no es de esta feature.

## Comprobaciones de punta a punta extra (automatizadas)

**Notas de mejora con el script real (R7.2, R7.3).** `improvement_notes.py` corrió por `run.sh`, como
lo corre el flujo, con `CLAUDE_CONFIG_DIR` apuntando a una carpeta temporal para no tocar el archivo
central del usuario:

- Una nota con un bloque de código y un correo: el archivo central nuevo tiene el encabezado
  (`## 2026-10-30 · slice S1`, `- Project:`, `- Feature:`) y, desde el bloque, la línea
  `[rest omitted: it may contain code]`. Ni el código ni el correo aparecen (0 coincidencias).
- Una nota con solo un correo: el correo queda como `[email removed]` (0 coincidencias).
- El script terminó con código 0 las dos veces y nombró el archivo escrito.

**Notas reales de esta corrida (R7.1).** El archivo central `~/.claude/konundrm-eng/improvements.md`
tiene entradas de esta feature con alcance `slice S7`, `slice S8`, `slice S9`, `slice S10` y
`feature`. El process-reviewer y el script llegaron en S7, así que S1–S6 no tienen notas.

**Historial trazable.** Las 79 tareas están marcadas en `tasks.md`, cada una con su línea
`Rounds:`, y `git log -E --grep "^Task: T<n>( |$)" b8c3142..HEAD` encuentra un commit para cada una.
Los diez resúmenes de slice están en `summaries/S1.md`–`summaries/S10.md`.

## Paso 2: corrida interactiva en un proyecto de prueba (no corrida)

No se corrió: necesita que una persona apruebe la spec y el plan, elija la decisión abierta,
responda las preguntas de la pausa y elija la entrega, y una corrida sin esas respuestas no prueba lo
que el paso pide. Los pasos exactos, con lo que debe verse en cada uno, están en
[summary.md, "How to test the feature"](../summary.md#how-to-test-the-feature). En resumen:

1. En una carpeta vacía con `git init` y un comando de check mínimo, abrir Claude Code con el plugin
   de esta rama: `claude --plugin-dir <repo>/plugins/konundrm-eng`.
2. Correr `/konundrm-eng:develop-feature` con una feature chica de dos slices, cuyo segundo slice
   tenga dos partes independientes y una tarea con dos enfoques razonables, sin aprobar de antemano
   ni las pausas ni las decisiones.
3. Ver el plan con slices, la tabla de particiones de S2 y la decisión con sus opciones; elegir una
   y ver `- Decision: <opción> (user)` y las líneas `Checkpoints:` y `Decisions:` en `ask`.
4. Ver la pregunta sobre construir en paralelo.
5. Al cerrar S1, ver la pausa: el commit `summarize slice S1`, el orden de lectura y dos o tres
   preguntas; contestar una mal y ver la explicación con archivo y líneas.
6. Ver S2 construido por dos sesiones, la segunda en un worktree fuera de la carpeta del proyecto, e
   integrado de a una partición.
7. Al final, ver `summary.md`, el commit `Status: Done` y la elección entre pull requests apiladas
   (por defecto) o una sola, con el aviso de `risk:high` si alguna tarea es de riesgo alto.
8. Abrir `~/.claude/konundrm-eng/improvements.md` y ver entradas nuevas del proyecto de prueba, sin
   código, secretos ni correos.
