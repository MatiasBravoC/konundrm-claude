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
# Shell builtins on the hot path: every external command is a process start, which costs tens of
# milliseconds on Windows, and these hooks run around every tool call. The one exception is the
# check recorder's fast path below, which pays for dd and cat so it never starts Python.
case $0 in
  */*) here=${0%/*} ;;
  *\\*) here=${0%\\*} ;; # a Windows path with backslashes only
  *) here=. ;;
esac
cache_dir="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}/konundrm-eng}"
cache_file="$cache_dir/python-path"

# Removes trailing whitespace from check_word.
trim_check_word() {
  while :; do
    case $check_word in
      *[[:space:]]) check_word=${check_word%?} ;;
      *) return ;;
    esac
  done
}

# Sets check_word to a word that every command running the project's check contains: "check" for
# a discovered check, else the last word of KONUNDRM_CHECK_CMD once the trailing "2>&1" and ";"
# that quality_check.is_check_invocation ignores are gone. It repeats quality_check._normalize's
# steps in order, so the word is the last word of the canonical check and appears in each of its
# equivalent forms; a command without it cannot be the check. Empty when the override has no
# word left, or holds a character outside printable ASCII, which makes every command go to Python.
find_check_word() {
  check_word=${KONUNDRM_CHECK_CMD-}
  # Python's str.split() also splits on whitespace the shell's [[:space:]] may not match, such as
  # U+00A0, U+3000 or \x1c, so only an override in printable ASCII has the same words for both. The
  # characters are spelled out because ranges and classes such as [[:print:]] follow the locale.
  case $check_word in
    *[!' !"#$%&'\''()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~']*)
      check_word="" && return ;;
  esac
  case $check_word in
    *[![:space:]]*) ;;
    *) check_word=check && return ;; # an unset or blank override leaves the discovered check
  esac
  trim_check_word
  case $check_word in
    *'2>&1') check_word=${check_word%'2>&1'} && trim_check_word ;;
  esac
  while :; do
    case $check_word in
      *';') check_word=${check_word%?} ;;
      *) break ;;
    esac
  done
  trim_check_word
  check_word=${check_word##*[[:space:]]}
}

# Succeeds only when the start of a PostToolUse event ($1) shows a whole command that cannot be the
# check. Any doubt fails it, so Python runs (R5.3): no "command" key after "tool_input", the key
# Python reads, a value cut off where the start ends, or a value with JSON escapes, whose raw text
# differs from the command.
is_other_command() {
  case $1 in
    *'"tool_input":'*'"command":'*) ;;
    *) return 1 ;;
  esac
  command_text=${1#*'"tool_input":'}
  command_text=${command_text#*'"command":'}
  command_text=${command_text#"${command_text%%[! ]*}"}
  case $command_text in
    '"'*'"'*) command_text=${command_text#'"'} ;;
    *) return 1 ;;
  esac
  command_text=${command_text%%'"'*}
  case $command_text in
    *'\'*) return 1 ;;
  esac
  find_check_word
  case $command_text in
    *"$check_word"*) return 1 ;;
  esac
  return 0
}

# Only the check recorder takes the fast path; every other hook gets its stdin untouched.
event_start=""
if [ "$script" = record_check_result.py ]; then
  # dd issues one read(2), so it never consumes more than it prints; head -c can (BSD head reads
  # through stdio and drops what it buffered past the limit). A short read only shortens the start,
  # which sends the event to Python. The trailing "." keeps the newlines that command substitution
  # would strip from the end.
  event_start=$(dd bs=8192 count=1 2>/dev/null; printf .)
  event_start=${event_start%.}
  if is_other_command "$event_start"; then
    cat >/dev/null # drain the rest so Claude Code never writes into a closed pipe
    exit 0
  fi
fi

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
if [ "$script" = record_check_result.py ]; then
  # Hands Python the event byte for byte: the start already read, then the rest of stdin.
  { printf '%s' "$event_start"; exec cat; } | "$python_bin" "$here/scripts/$script" "$@"
  exit
fi
exec "$python_bin" "$here/scripts/$script" "$@"
