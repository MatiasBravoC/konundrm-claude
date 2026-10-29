"""Unit tests for the setup-project template scripts/check_mutation.py (no mutmut needed)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "setup-project" / "templates" / "python"))

import check_mutation

SEP = check_mutation.METHOD_SEPARATOR

DIFF = """diff --git a/src/shop/cart.py b/src/shop/cart.py
--- a/src/shop/cart.py
+++ b/src/shop/cart.py
@@ -3,0 +4,2 @@ def total(items):
+    if not items:
+        return 0
@@ -20 +22 @@ class Cart:
-        return x
+++ fake header inside a hunk
diff --git a/README.md b/README.md
--- /dev/null
+++ b/README.md
@@ -0,0 +1 @@
+# Shop
@@ -40,3 +42,0 @@
"""

SOURCE = """import functools


def total(items):
    if not items:
        return 0
    return sum(items)


def untouched():
    return 1


class Cart:
    def __init__(self):
        self.items = []

    @functools.cache
    def count(self):
        return len(self.items)

    def clear(self):
        self.items = []
"""


class ChangedLinesTest(unittest.TestCase):
    def test_reads_added_lines_per_file_and_skips_pure_deletions(self) -> None:
        self.assertEqual(check_mutation.changed_lines(DIFF), {"src/shop/cart.py": {4, 5, 22}, "README.md": {1}})


class ModuleNameTest(unittest.TestCase):
    def test_follows_mutmut_naming(self) -> None:
        self.assertEqual(check_mutation.module_name("src/shop/cart.py", "src"), "shop.cart")
        self.assertEqual(check_mutation.module_name("src/shop/__init__.py", "src/"), "shop")
        self.assertEqual(check_mutation.module_name("shop/cart.py", "shop"), "shop.cart")

    def test_ignores_files_outside_the_source_or_not_python(self) -> None:
        self.assertIsNone(check_mutation.module_name("tests/test_cart.py", "src"))
        self.assertIsNone(check_mutation.module_name("src/shop/data.json", "src"))


class ChangedFunctionsTest(unittest.TestCase):
    def test_names_functions_and_methods_that_contain_a_changed_line(self) -> None:
        self.assertEqual(check_mutation.changed_functions(SOURCE, {5}), ["x_total"])
        self.assertEqual(
            check_mutation.changed_functions(SOURCE, {19, 23}), [f"x{SEP}Cart{SEP}count", f"x{SEP}Cart{SEP}clear"]
        )

    def test_a_changed_decorator_counts_for_its_method(self) -> None:
        self.assertEqual(check_mutation.changed_functions(SOURCE, {18}), [f"x{SEP}Cart{SEP}count"])

    def test_module_level_changes_have_no_mutants(self) -> None:
        self.assertEqual(check_mutation.changed_functions(SOURCE, {1}), [])

    def test_builds_globs_for_existing_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "shop").mkdir(parents=True)
            (root / "src" / "shop" / "cart.py").write_text(SOURCE, encoding="utf-8")
            globs = check_mutation.mutant_globs({"src/shop/cart.py": {5}, "src/gone.py": {1}}, "src", root)
        self.assertEqual(globs, ["shop.cart.x_total__mutmut_*"])


class ResultsTest(unittest.TestCase):
    RESULTS = "\n".join(
        [
            "    shop.cart.x_total__mutmut_1: killed",
            "    shop.cart.x_total__mutmut_2: survived",
            "    shop.cart.x_total__mutmut_3: timeout",
            "    shop.cart.x_total__mutmut_4: no tests",
            "    shop.cart.x_total__mutmut_5: skipped",
            "    shop.other.x_f__mutmut_1: survived",
        ]
    )

    def test_keeps_only_the_changed_functions_mutants(self) -> None:
        statuses = check_mutation.parse_results(self.RESULTS, ["shop.cart.x_total__mutmut_*"])
        self.assertEqual(len(statuses), 5)
        self.assertNotIn("shop.other.x_f__mutmut_1", statuses)

    def test_scores_detected_over_detected_plus_undetected(self) -> None:
        statuses = check_mutation.parse_results(self.RESULTS, ["shop.cart.x_total__mutmut_*"])
        score, undetected = check_mutation.mutation_score(statuses)
        self.assertEqual(score, 50.0)
        self.assertEqual(undetected, ["shop.cart.x_total__mutmut_2", "shop.cart.x_total__mutmut_4"])

    def test_no_counted_mutants_has_no_score(self) -> None:
        self.assertEqual(check_mutation.mutation_score({"a": "skipped"}), (None, []))


if __name__ == "__main__":
    unittest.main()
