"""Unit tests for hooks/scripts/package_installs.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from package_installs import PackageRequest, find_package_requests, normalize_name


def found(command_line: str) -> list[tuple[str, str]]:
    return [(request.ecosystem, request.name) for request in find_package_requests(command_line)]


class FindPackageRequestsTest(unittest.TestCase):
    def test_reads_npm_family_installs_without_versions(self) -> None:
        cases = {
            "npm install lodash@4.17.21": [("npm", "lodash")],
            "npm i -D vitest @types/node@^22": [("npm", "vitest"), ("npm", "@types/node")],
            "pnpm add zod": [("npm", "zod")],
            "yarn add react react-dom": [("npm", "react"), ("npm", "react-dom")],
            "bun add hono": [("npm", "hono")],
            "npm install my-alias@npm:real-package@1.0.0": [("npm", "real-package")],
        }
        for command_line, expected in cases.items():
            with self.subTest(command_line=command_line):
                self.assertEqual(found(command_line), expected)

    def test_reads_only_the_package_a_runner_runs(self) -> None:
        self.assertEqual(found("npx create-vite@latest my-app --template react"), [("npm", "create-vite")])
        self.assertEqual(found("npx -p typescript tsc --init"), [("npm", "typescript")])
        self.assertEqual(found("pnpm dlx degit user/repo"), [("npm", "degit")])
        (request,) = find_package_requests("npx eslint .")
        self.assertTrue(request.runs_binary)

    def test_reads_python_installers_and_normalises_names(self) -> None:
        cases = {
            "pip install Requests[security]==2.32.0": [("pypi", "requests")],
            "python -m pip install --upgrade Django_Rest_Framework": [("pypi", "django-rest-framework")],
            "uv add 'pydantic>=2' httpx": [("pypi", "pydantic"), ("pypi", "httpx")],
            "uv pip install -p 3.12 numpy": [("pypi", "numpy")],
            "uvx ruff@latest check .": [("pypi", "ruff")],
            "uvx --from httpie http GET x": [("pypi", "httpie")],
            "uv run --with rich script.py": [("pypi", "rich")],
            "poetry add -G dev pytest": [("pypi", "pytest")],
            "pipx run --spec black==24.1 black .": [("pypi", "black")],
            "python3.12 -m pip install attrs": [("pypi", "attrs")],
            "pip3.12 install attrs": [("pypi", "attrs")],
            "timeout 120 uv add attrs": [("pypi", "attrs")],
            "yarn global add serve": [("npm", "serve")],
        }
        for command_line, expected in cases.items():
            with self.subTest(command_line=command_line):
                self.assertEqual(found(command_line), expected)

    def test_finds_installs_inside_chains_and_nested_shells(self) -> None:
        self.assertEqual(found("cd app && bash -c 'npm i left-pad'"), [("npm", "left-pad")])

    def test_skips_lockfile_installs_paths_urls_and_files(self) -> None:
        for command_line in (
            "npm install",
            "npm ci",
            "uv sync",
            "pip install -r requirements.txt",
            "pip install -e .",
            "pip install ./dist/pkg-1.0-py3-none-any.whl",
            "pip install git+https://github.com/org/repo.git",
            "npm install ../local-lib",
            "npm install user/repo",
            "npm install https://example.com/pkg.tgz",
            "npm run build",
            "pip list",
        ):
            with self.subTest(command_line=command_line):
                self.assertEqual(found(command_line), [])

    def test_skips_commands_that_use_a_custom_package_source(self) -> None:
        for command_line in (
            "pip install --index-url https://pypi.internal/simple corp-lib",
            "pip install -i https://pypi.internal/simple corp-lib",
            "npm install --registry=https://npm.internal corp-lib",
            "uv add --index internal corp-lib",
        ):
            with self.subTest(command_line=command_line):
                self.assertEqual(found(command_line), [])

    def test_reports_each_package_once(self) -> None:
        self.assertEqual(found("npm i lodash && npm i lodash"), [("npm", "lodash")])


class NormalizeNameTest(unittest.TestCase):
    def test_follows_pep_503_for_pypi_and_lower_case_for_npm(self) -> None:
        self.assertEqual(normalize_name("pypi", "Zope.Interface__x"), "zope-interface-x")
        self.assertEqual(normalize_name("npm", "@Scope/Pkg"), "@scope/pkg")

    def test_requests_compare_by_value(self) -> None:
        self.assertEqual(PackageRequest("npm", "a"), PackageRequest("npm", "a"))


if __name__ == "__main__":
    unittest.main()
