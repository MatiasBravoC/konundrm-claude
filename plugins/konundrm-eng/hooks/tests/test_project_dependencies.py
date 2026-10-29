"""Unit tests for hooks/scripts/project_dependencies.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from project_dependencies import declared_packages, local_binaries, private_npm_scopes


class ProjectDependenciesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_reads_every_npm_dependency_section(self) -> None:
        package = {
            "dependencies": {"React": "19"},
            "devDependencies": {"vitest": "3"},
            "peerDependencies": {"zod": "4"},
        }
        (self.root / "package.json").write_text(json.dumps(package))
        self.assertEqual(declared_packages(self.root), {("npm", "react"), ("npm", "vitest"), ("npm", "zod")})

    @unittest.skipIf(sys.version_info < (3, 11), "pyproject parsing needs tomllib")
    def test_reads_pyproject_dependencies_groups_and_poetry_tables(self) -> None:
        (self.root / "pyproject.toml").write_text(
            "[project]\ndependencies = ['Django>=5', 'httpx']\n"
            "[project.optional-dependencies]\nfast = ['orjson']\n"
            "[dependency-groups]\ndev = ['pytest', {include-group = 'lint'}]\n"
            "[tool.poetry.dependencies]\npython = '^3.12'\nRequests = '*'\n"
        )
        self.assertEqual(
            declared_packages(self.root),
            {("pypi", name) for name in ("django", "httpx", "orjson", "pytest", "requests")},
        )

    def test_reads_lock_files_and_requirements(self) -> None:
        (self.root / "uv.lock").write_text('[[package]]\nname = "Pydantic_Core"\nversion = "2"\n')
        (self.root / "requirements-dev.txt").write_text("# tools\nruff==0.17\n-r base.txt\n")
        self.assertEqual(declared_packages(self.root), {("pypi", "pydantic-core"), ("pypi", "ruff")})

    def test_lists_local_binaries_without_windows_shims(self) -> None:
        binaries = self.root / "node_modules" / ".bin"
        binaries.mkdir(parents=True)
        for name in ("tsc", "tsc.cmd", "tsc.ps1", "eslint"):
            (binaries / name).write_text("")
        self.assertEqual(local_binaries(self.root), {"tsc", "eslint"})

    def test_finds_npm_scopes_with_their_own_registry(self) -> None:
        (self.root / ".npmrc").write_text("@Konundrm:registry=https://npm.pkg.github.com\nregistry=https://x\n")
        self.assertEqual(private_npm_scopes(self.root), {"@konundrm"})

    def test_a_project_without_manifests_declares_nothing(self) -> None:
        self.assertEqual(declared_packages(self.root), set())
        self.assertEqual(local_binaries(self.root), set())


if __name__ == "__main__":
    unittest.main()
