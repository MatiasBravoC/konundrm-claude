#!/bin/sh
# Runs one konundrm-eng hook script with Python 3.10 or newer: sh run.sh <script.py> [args...]
#
# Every hook in hooks.json, and every skill that needs the check command, goes through this
# launcher, so finding the interpreter lives in one place. It skips interpreters that cannot run
# scripts, such as the Microsoft Store "python3" stub on Windows, and caches the first usable one.
# Without Python the gates are off and the SessionStart hook tells the person why, except for
# commits: the commit gate then denies any command that mentions one, since it cannot check it.

script="$1"
shift
# Shell builtins only on the hot path: every external command is a process start, which costs
# tens of milliseconds on Windows, and these hooks run around every tool call.
case $0 in
  */*) here=${0%/*} ;;
  *\\*) here=${0%\\*} ;; # a Windows path with backslashes only
  *) here=. ;;
esac
cache_dir="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}/konundrm-eng}"
cache_file="$cache_dir/python-path"

is_usable() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

python_bin=""
if [ -f "$cache_file" ]; then
  IFS= read -r python_bin <"$cache_file" || :
  command -v "$python_bin" >/dev/null 2>&1 || python_bin=""
fi
if [ -z "$python_bin" ]; then
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1 && is_usable "$candidate"; then
      python_bin=$(command -v "$candidate")
      break
    fi
  done
  if [ -n "$python_bin" ]; then
    mkdir -p "$cache_dir" 2>/dev/null && printf '%s\n' "$python_bin" >"$cache_file" 2>/dev/null
  fi
fi

if [ -z "$python_bin" ]; then
  case "$script" in
    session_doctor.py)
      printf '%s\n' '{"systemMessage": "konundrm-eng: no Python 3.10+ found on PATH (python3, python or py), so the quality gates and role checks are off and commits through Claude are denied. Install Python and restart Claude Code."}'
      ;;
    gate_git_commit.py)
      # Fail closed for commits, reading the event with builtins only: a rough match is enough here.
      event=""
      while IFS= read -r line || [ -n "$line" ]; do event="$event$line"; done
      case "$event" in
        *git*commit*)
          printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "konundrm-eng: no Python 3.10+ found, so the commit gate cannot check this commit. Install Python (python3, python or py on PATH) and restart Claude Code, or commit outside Claude Code."}}'
          ;;
      esac
      ;;
  esac
  exit 0
fi
exec "$python_bin" "$here/scripts/$script" "$@"
