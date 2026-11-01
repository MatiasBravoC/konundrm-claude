"""Tests for hooks/scripts/run_slices.py, run as the CLI a person starts, with a scripted fake `claude`."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
RUN_SLICES = PLUGIN / "hooks" / "scripts" / "run_slices.py"
DEVELOP_FEATURE = PLUGIN / "skills" / "develop-feature" / "SKILL.md"
FEATURE = "specs/001-demo"
PLAN_PATH = f"{FEATURE}/tasks.md"
RESUME_PROMPT = f"/konundrm-eng:develop-feature {FEATURE}"
# Flag-like, so an exact argv shows run_slices adds no flag of its own (no permission flags) and
# drops none; free of the characters cmd.exe re-parses in the Windows wrapper.
EXTRA_ARGS = ["--model", "sonnet", "--max-turns", "7"]
SEED_COUNT = 10
PYTHON_UTF8_VARIABLES = {"PYTHONIOENCODING", "PYTHONUTF8"}
# Tokens a parser that reads past `--`, or a wrapper that "helps" with permissions, would mishandle.
TRICKY_TOKENS = ["--", "-p", "--print", "--claude", "--max-sessions", "3", "--permission-mode", "acceptEdits"]
TRICKY_TOKENS += ["--dangerously-skip-permissions", "--model", "sonnet", "specs/other", "two words", ""]
# cmd.exe re-parses the Windows wrapper's arguments, so these are drawn on POSIX only.
CMD_SPECIAL = '&|^%"<>!'
TOKEN_ALPHABET = string.ascii_letters + string.digits + "-_=./:" + ("" if os.name == "nt" else CMD_SPECIAL)

# One headless session: reads its step from the script, logs its arguments, may commit a task and
# mark the plan Done in the repository it runs in (its current directory), prints, and exits.
FAKE_CLAUDE = r"""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # as claude writes to a pipe, whatever the platform
log = Path(os.environ["FAKE_CLAUDE_LOG"])
steps = json.loads(Path(os.environ["FAKE_CLAUDE_SCRIPT"]).read_text(encoding="utf-8"))
earlier = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\n")
if len(earlier) >= len(steps):
    print("fake claude: no session scripted for this call")
    sys.exit(97)
step = steps[len(earlier)]


def git(*args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True)


for task in step.get("tasks") or ([step["task"]] if step.get("task") else []):
    Path(task + ".txt").write_text(task + "\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat: build " + task, "-m", "Task: " + task)
if step.get("done"):
    plan = Path(os.environ["FAKE_CLAUDE_PLAN"])
    text = plan.read_text(encoding="utf-8").replace("- **Status:** Approved", "- **Status:** Done")
    plan.write_text(text, encoding="utf-8", newline="\n")
    git("add", "-A")
    git("commit", "-q", "-m", "docs(specs): mark the plan done")
if step.get("echo_stdin"):
    print("stdin: " + json.dumps(sys.stdin.read()))
for line in step.get("stdout", []):
    print(line)
sys.stdout.flush()
if step.get("kill"):
    os.kill(os.getpid(), signal.SIGKILL)
sys.exit(step.get("exit", 0))
"""


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def commit(root: Path, message: str) -> str:
    """Commit everything with `message` (written to a UTF-8 file, so `·` survives) and return its sha."""
    message_file = root.parent / "message.txt"
    message_file.write_text(message, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-F", str(message_file))
    return git(root, "rev-parse", "HEAD")


# Real plans carry a comment after the value, and the template's spans lines.
PRE_APPROVED = "- **Checkpoints:** pre-approved <!-- el usuario aprobó las pausas\ncon el plan -->\n"
BLOCKED_REASON = "T2 needs a plan change"
# Each decoration the stop gate accepts (deliberate_stops.DELIBERATE_STOP) on a BLOCKED: line.
DECORATED_BLOCKED_LINES = [f"**BLOCKED:** {BLOCKED_REASON}", f"**BLOCKED**: {BLOCKED_REASON}"]
DECORATED_BLOCKED_LINES += [
    f"> BLOCKED: {BLOCKED_REASON}",
    f"- BLOCKED: {BLOCKED_REASON}",
    f"  BLOCKED: {BLOCKED_REASON}",
]
# Builds the whole feature if the runner ever starts a session.
BUILD_ALL = [{"task": "T1"}, {"task": "T2", "done": True}]


def plan_text(base: str) -> str:
    return (
        "# Tasks: demo\n"
        "\n"
        "- **Status:** Approved\n"
        f"- **Base commit:** `{base}`\n"
        f"{PRE_APPROVED}"
        "\n"
        "## Slice S1: the first half\n"
        "\n"
        "- [ ] **T1** builds the first half · `behavior` · Risk: low · Covers: R1.1\n"
        "\n"
        "## Slice S2: the second half\n"
        "\n"
        "- [ ] **T2** builds the second half · `behavior` · Risk: low · Covers: R1.2\n"
    )


def plan_with_slices(slices: list[list[str]]) -> Callable[[str], str]:
    """An `edit_plan` that replaces the fixture's two slices with `slices` (each a list of task IDs)."""
    sections = "\n".join(
        f"## Slice S{index}: part {index}\n\n"
        + "".join(f"- [ ] **{task}** builds {task} · `behavior` · Risk: low · Covers: R1.1\n" for task in tasks)
        for index, tasks in enumerate(slices, start=1)
    )
    return lambda text: text[: text.index("## Slice S1")] + sections


def write_fake_claude(folder: Path) -> Path:
    """Write the fake `claude` so subprocess can start it without a shell on every platform."""
    script = folder / "fake_claude.py"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    if os.name == "nt":
        # CreateProcess cannot run a shebang script; it runs a .cmd through cmd.exe.
        wrapper = folder / "claude.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return wrapper
    launcher = folder / "claude"
    launcher.write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def last_line(output: str) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


@unittest.skipIf(shutil.which("git") is None, "Git is not installed")
class RunSlicesTest(unittest.TestCase):
    def run_feature(
        self,
        steps: list[dict[str, object]],
        extra: list[str] | None = None,
        edit_plan: Callable[[str], str] = str,
        feature: str = FEATURE,
        claude_options: list[str] | None = None,
        path: str | None = None,
        stdin_text: str | None = None,
        committed: list[str] | None = None,
        options: list[str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        """Build a two-slice feature in a fresh repository with `steps` as the sessions' script.

        `extra` goes after `--` (EXTRA_ARGS when None); `edit_plan` rewrites the plan's text and
        `feature` is the folder the runner is given. `claude_options` replaces `--claude <the fake>`,
        `path` the runner's PATH, and `stdin_text` is fed to its stdin. Each task in `committed` gets a
        `Task:` commit after the plan's, and `options` go to the runner before `--`. Returns the run and each
        session's argv[1:].
        """
        extra = EXTRA_ARGS if extra is None else extra
        folder_handle = tempfile.TemporaryDirectory()
        self.addCleanup(folder_handle.cleanup)
        folder = Path(folder_handle.name).resolve()
        root = folder / "repo"
        root.mkdir()
        git(root, "init", "-q")
        (root / "README.md").write_text("demo\n", encoding="utf-8")
        base = commit(root, "chore: start the feature branch\n")
        plan = root / PLAN_PATH
        plan.parent.mkdir(parents=True)
        plan.write_text(edit_plan(plan_text(base)), encoding="utf-8", newline="\n")
        commit(root, "docs(specs): add spec and plan\n")
        for task in committed or []:
            (root / f"{task}.txt").write_text(f"{task}\n", encoding="utf-8")
            commit(root, f"feat: build {task}\n\nTask: {task}\n")
        script = folder / "steps.json"
        script.write_text(json.dumps(steps), encoding="utf-8")
        log = folder / "calls.log"
        # Without these the runner's own UTF-8 setup is what keeps its output UTF-8, as for a person.
        inherited = {name: value for name, value in os.environ.items() if name not in PYTHON_UTF8_VARIABLES}
        environment = inherited | {
            "FAKE_CLAUDE_LOG": str(log),
            "FAKE_CLAUDE_SCRIPT": str(script),
            "FAKE_CLAUDE_PLAN": str(plan),
        }
        if path is not None:
            environment["PATH"] = path
        if claude_options is None:
            claude_options = ["--claude", str(write_fake_claude(folder))]

        completed = subprocess.run(
            [sys.executable, str(RUN_SLICES), feature, *claude_options, *(options or []), "--", *extra],
            cwd=root,
            env=environment,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )

        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return completed, calls

    # R1.4: one headless session per slice, in order, until the feature is done, a session stops with
    # BLOCKED: or a session fails; the last line says which. Threats row 3: each session gets the
    # resume prompt and the user's arguments after --, nothing more.
    def test_runs_one_session_per_slice_until_done_blocked_or_failed(self) -> None:
        scenarios = {
            "done": (
                [
                    # Mid-line mentions of the stop words do not stop the run.
                    {
                        "task": "T1",
                        "stdout": ["Slice S1 built; nothing was BLOCKED: going on to S2", "T1 went RED: then green"],
                    },
                    {"task": "T2", "done": True, "stdout": ["Feature built."]},
                ],
                "DONE",
                2,
            ),
            "blocked": (
                [
                    {
                        "task": "T1",
                        "stdout": [
                            "BLOCKED: T2 needs a plan change",
                            "The plan says one thing and the spec another.",
                            "Options: change the plan, or change the spec.",
                        ],
                    }
                ],
                "BLOCKED: T2 needs a plan change",
                1,
            ),
            "failed": ([{"task": "T1", "stdout": ["Slice S1 half built"], "exit": 3}], "FAILED: exit 3", 1),
            # A failure wins over a stop line in the same session.
            "blocked and failed": (
                [{"task": "T1", "stdout": [f"BLOCKED: {BLOCKED_REASON}"], "exit": 3}],
                "FAILED: exit 3",
                1,
            ),
        }
        expected_argv = ["-p", RESUME_PROMPT, *EXTRA_ARGS]

        runs = self.run_features([{"steps": steps} for steps, _, _ in scenarios.values()])

        for (name, (_, expected_last_line, expected_sessions)), (completed, calls) in zip(
            scenarios.items(), runs, strict=True
        ):
            with self.subTest(scenario=name):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(last_line(completed.stdout), expected_last_line, report)
                self.assertEqual(completed.returncode, 0 if expected_last_line == "DONE" else 1, report)
                self.assertEqual(calls, [expected_argv] * expected_sessions, report)

    # R1.4: develop-feature says, on one line, when to use run_slices.py.
    def test_develop_feature_says_when_to_use_run_slices(self) -> None:
        skill_lines = DEVELOP_FEATURE.read_text(encoding="utf-8").splitlines()
        self.assertTrue(
            any(re.search(r"\brun_slices\.py\b", line) and "pre-approved" in line for line in skill_lines),
            "develop-feature names run_slices.py and when to use it (Checkpoints: pre-approved) on one line",
        )

    def run_features(self, runs: list[dict[str, object]]) -> list[tuple[subprocess.CompletedProcess[str], list]]:
        """Run `run_feature(**run)` for each run side by side (own repository and processes each)."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda run: self.run_feature(**run), runs))

    # R1.4, Threats row 3: a BLOCKED: line stops the run however Markdown decorates it, as the stop
    # gate (deliberate_stops.DELIBERATE_STOP) accepts; the summary carries the undecorated reason.
    def test_stops_on_a_blocked_line_however_markdown_decorates_it(self) -> None:
        stdout = ["The plan says one thing and the spec another.", "Options: change the plan, or the spec."]
        runs = [
            {"steps": [{"task": "T1", "stdout": [line, *stdout]}, BUILD_ALL[1]]} for line in DECORATED_BLOCKED_LINES
        ]

        for line, (completed, calls) in zip(DECORATED_BLOCKED_LINES, self.run_features(runs), strict=True):
            with self.subTest(line=line):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(calls, [["-p", RESUME_PROMPT, *EXTRA_ARGS]], report)
                self.assertEqual(completed.returncode, 1, report)
                self.assertEqual(last_line(completed.stdout), f"BLOCKED: {BLOCKED_REASON}", report)

    # R1.4 (approved plan change: a fourth ending): a session that waits for a person's decision, a
    # RED: line as the stop gate reads it, stops the run; the summary carries the undecorated line.
    def test_stops_when_a_session_waits_for_a_decision(self) -> None:
        lines = ["RED: T2 waits for a decision", "**RED:** T2 waits for a decision"]
        report_lines = ["DECISION: T2 the open question", "Options: A or B; recommended A."]
        runs = [{"steps": [{"task": "T1", "stdout": [line, *report_lines]}, BUILD_ALL[1]]} for line in lines]

        for line, (completed, calls) in zip(lines, self.run_features(runs), strict=True):
            with self.subTest(line=line):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(calls, [["-p", RESUME_PROMPT, *EXTRA_ARGS]], report)
                self.assertEqual(completed.returncode, 1, report)
                self.assertEqual(last_line(completed.stdout), "RED: T2 waits for a decision", report)

    # R1.4 (the pauses are pre-approved), Threats row 3: before any session, the runner refuses a plan
    # whose pauses are not pre-approved (no Checkpoints line reads as ask), one not Approved, or none.
    def test_refuses_a_plan_whose_pauses_are_not_pre_approved(self) -> None:
        cases = {
            "Checkpoints: ask": (
                {"edit_plan": lambda text: text.replace(PRE_APPROVED, "- **Checkpoints:** ask <!-- a comment -->\n")},
                r"Checkpoints",
            ),
            "no Checkpoints line": ({"edit_plan": lambda text: text.replace(PRE_APPROVED, "")}, r"Checkpoints"),
            "Status: Draft": (
                {"edit_plan": lambda text: text.replace("**Status:** Approved", "**Status:** Draft")},
                r"(?i)\bplan\b|status|tasks\.md",
            ),
            # An unreadable plan is refused for that reason, not for its (missing) Status.
            "no tasks.md": ({"feature": "specs/001-dmeo"}, r"(?i)\bcannot read\b.*\bplan\b"),
        }
        runs = [{"steps": BUILD_ALL, **options} for options, _ in cases.values()]

        for (name, (_, reason)), (completed, calls) in zip(cases.items(), self.run_features(runs), strict=True):
            with self.subTest(case=name):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(calls, [], report)
                self.assertEqual(completed.returncode, 2, report)
                self.assertNotRegex(completed.stdout, r"(?m)^\s*DONE\b", report)
                self.assertRegex(completed.stderr, reason, report)

    # R1.4: a plan already Done opens no session and says DONE.
    def test_opens_no_session_for_a_plan_already_done(self) -> None:
        completed, calls = self.run_feature(
            BUILD_ALL, edit_plan=lambda text: text.replace("**Status:** Approved", "**Status:** Done")
        )

        report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(calls, [], report)
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(last_line(completed.stdout), "DONE", report)

    # R1.4: each session's lines, Spanish included, are echoed as UTF-8 before the summary, which is
    # the session's first stop line (a later one may be a quote in its escalation).
    def test_echoes_each_sessions_output_as_utf8_before_the_first_stop_line(self) -> None:
        stop_line = "BLOCKED: T2 necesita un cambio de diseño → plan"
        escalation = [stop_line, "El plan dice una cosa y la spec otra.", "> BLOCKED: una cita, no la parada"]
        steps = [{"task": "T1", "stdout": ["Construí el slice S1 ✓"]}, {"task": "T2", "stdout": escalation}]

        completed, calls = self.run_feature(steps)

        report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(completed.stdout.splitlines(), ["Construí el slice S1 ✓", *escalation, stop_line], report)
        self.assertEqual((completed.returncode, len(calls)), (1, 2), report)

    # R1.4: a session never waits on the terminal: its stdin is empty even when the runner's is not.
    def test_a_session_gets_an_empty_stdin(self) -> None:
        completed, _ = self.run_feature([{"task": "T1", "done": True, "echo_stdin": True}], stdin_text="y\n")

        report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(completed.stdout.splitlines(), ['stdin: ""', "DONE"], report)

    # R1.4: a session killed by a signal (a negative exit status) fails the run.
    @unittest.skipIf(os.name == "nt", "only POSIX kills a process by a signal; Windows exit codes are not negative")
    def test_a_session_killed_by_a_signal_fails_the_run(self) -> None:
        completed, calls = self.run_feature([{"task": "T1", "kill": True}, BUILD_ALL[1]])

        report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        self.assertEqual(last_line(completed.stdout), "FAILED: exit -9", report)
        self.assertEqual((completed.returncode, len(calls)), (1, 1), report)

    # R1.4: when claude is not on PATH (and no --claude) or cannot be started, the runner says so on
    # stderr, without a traceback, opens no session and exits 2.
    def test_says_claude_cannot_be_found_or_started(self) -> None:
        empty_folder = tempfile.TemporaryDirectory()
        self.addCleanup(empty_folder.cleanup)
        cases = {
            "not on PATH": ({"claude_options": [], "path": empty_folder.name}, r"--claude"),
            "cannot start": ({"claude_options": ["--claude", str(PLUGIN / "no-such-claude")]}, r"(?i)cannot start"),
        }

        runs = self.run_features([{"steps": BUILD_ALL, **options} for options, _ in cases.values()])

        for (name, (_, reason)), (completed, calls) in zip(cases.items(), runs, strict=True):
            with self.subTest(case=name):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual((completed.returncode, calls, completed.stdout), (2, [], ""), report)
                self.assertRegex(completed.stderr, reason, report)
                self.assertNotIn("Traceback", completed.stderr, report)

    # R1.5, Threats row 3: a session that exits 0 without a stop line but leaves HEAD where it was
    # stops the run with STALLED instead of opening another session, even when the next ones would
    # build the whole feature.
    def test_stops_when_a_session_adds_no_commit(self) -> None:
        idle = {"stdout": ["Looked at the plan.", "Nothing to build right now."]}
        cases = {
            "second session": ([BUILD_ALL[0], idle, BUILD_ALL[1]], 2),
            "first session": ([idle, *BUILD_ALL], 1),
        }

        runs = self.run_features([{"steps": steps} for steps, _ in cases.values()])

        for (name, (_, stalled_session)), (completed, calls) in zip(cases.items(), runs, strict=True):
            with self.subTest(case=name):
                report = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(calls, [["-p", RESUME_PROMPT, *EXTRA_ARGS]] * stalled_session, report)
                self.assertEqual(completed.returncode, 1, report)
                self.assertEqual(
                    last_line(completed.stdout), f"STALLED: session {stalled_session} added no commit", report
                )

    # R1.5 (T32 invariant): whatever the plan, the tasks already committed and --max-sessions N, the
    # runner opens at most pending slices + 1 sessions (the extra one finishes the feature) and N only
    # lowers that cap. Sessions that keep committing without finishing stop exactly at the cap.
    def test_never_opens_more_sessions_than_pending_slices_plus_one(self) -> None:
        cases = []
        for seed in range(SEED_COUNT):
            rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
            sizes = [rng.randint(1, 2) for _ in range(rng.randint(1, 4))]
            ids = iter(f"T{number}" for number in range(1, sum(sizes) + 1))
            slices = [[next(ids) for _ in range(size)] for size in sizes]
            tasks = [task for tasks in slices for task in tasks]
            committed = tasks[: rng.randint(0, len(tasks) - 1)]  # never all, so a slice is pending
            remaining = [left for tasks in slices if (left := [task for task in tasks if task not in committed])]
            pending = len(remaining)
            max_sessions = rng.choice([None, rng.randint(1, pending + 3)])
            cap = min(pending + 1, max_sessions or pending + 1)
            is_slow = rng.random() < 0.5
            if is_slow:  # one commit per session, never Done; T5x are commits outside the plan
                steps = [
                    {"task": task}
                    for task in [
                        *(task for tasks in remaining for task in tasks),
                        *(f"T5{k}" for k in range(pending + 4)),
                    ]
                ]
            else:
                steps = [*({"tasks": tasks} for tasks in remaining), {"done": True}]
            options = [] if max_sessions is None else ["--max-sessions", str(max_sessions)]
            run = {"steps": steps, "committed": committed, "options": options, "edit_plan": plan_with_slices(slices)}
            cases.append((seed, is_slow, pending, max_sessions, cap, run))

        runs = self.run_features([run for *_, run in cases])

        for (seed, is_slow, pending, max_sessions, cap, _), (completed, calls) in zip(cases, runs, strict=True):
            with self.subTest(seed=seed):
                context = f"seed {seed}, slow {is_slow}, pending {pending}, N {max_sessions}\n"
                context += f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertLessEqual(len(calls), cap, context)
                outcome = (len(calls), completed.returncode, last_line(completed.stdout))
                if is_slow:
                    self.assertEqual(outcome, (cap, 1, f"STALLED: reached the cap of {cap} sessions"), context)
                elif cap == pending + 1:
                    self.assertEqual(outcome, (pending + 1, 0, "DONE"), context)
        self.assertEqual({case[1] for case in cases}, {True, False}, "both modes occur")
        self.assertIn(None, [case[3] for case in cases], "N is absent at least once")
        self.assertTrue(any(case[3] is not None and case[3] < case[2] + 1 for case in cases), "N binds once")
        self.assertGreater(len({case[2] for case in cases}), 1, "pending slices vary")

    # R1.4, Threats row 3 (T31 invariant): every session's argv[1:] is the resume prompt and exactly
    # the arguments after `--`, in order: nothing added (no permission flags), dropped or reordered,
    # even when those arguments look like run_slices' own options or another separator.
    def test_claude_gets_only_the_resume_prompt_and_the_arguments_after_the_separator(self) -> None:
        cases = []
        for seed in range(SEED_COUNT):
            rng = random.Random(seed)  # noqa: S311 - seeded for reproducible test data, not cryptography
            extra = [
                rng.choice(TRICKY_TOKENS)
                if rng.random() < 0.85
                else "".join(rng.choices(TOKEN_ALPHABET, k=rng.randint(1, 6)))
                for _ in range(rng.randint(0, 5))
            ]
            done = rng.random() < 0.5
            steps = [{"task": "T1"}, {"task": "T2", "done": True}] if done else [{"task": "T1", "exit": 3}]
            cases.append((seed, extra, steps))

        # Each seed has its own repository and processes, so the seeds run side by side to stay fast.
        with ThreadPoolExecutor(max_workers=8) as pool:
            runs = list(pool.map(lambda case: self.run_feature(case[2], case[1]), cases))

        for (seed, extra, steps), (completed, calls) in zip(cases, runs, strict=True):
            with self.subTest(seed=seed):
                context = f"seed {seed}, ARGS {extra!r}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                self.assertEqual(calls, [["-p", RESUME_PROMPT, *extra]] * len(steps), context)
        drawn = [extra for _, extra, _ in cases]
        self.assertTrue(any("--" in extra for extra in drawn), drawn)
        self.assertTrue(any({"--claude", "--max-sessions"} & set(extra) for extra in drawn), drawn)
        self.assertEqual({len(steps) for _, _, steps in cases}, {1, 2}, "some seeds end DONE, some FAILED")


if __name__ == "__main__":
    unittest.main()
