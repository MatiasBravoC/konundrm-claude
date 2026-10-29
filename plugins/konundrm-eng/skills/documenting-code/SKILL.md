---
name: documenting-code
description: Writes and fixes doc-comments that document each symbol's contract (purpose, parameters, return value, errors, side effects) in the official Google style of its language, auto-detected per file — Google Python docstrings, TSDoc/JSDoc, Google Java Javadoc, Go doc comments. Also owns the module header, a one-sentence responsibility plus a section index for long files. Use when the user says "documenta este código", "agrega docstrings", "comment this file" or "document this class", or after writing or editing any public function, class, module or exported symbol that lacks documentation.
argument-hint: "[file or symbol]"
---

# Documenting Code

Doc-comments are part of the public API: they document the **contract**, so a reader never has to
open the body to know how to call something safely. They are expected to be complete even when the
code is clear, unlike inline comments.

## Contract

- **Receives:** files or symbols to document, or the symbols changed in the current task.
- **Produces:** current, linter-clean doc-comments on every public symbol in scope and a correct
  module header.

## Workflow

1. **Detect the language** from the extension and apply its Google style. Syntax and examples per
   language: [reference/language-styles.md](reference/language-styles.md). If the project
   configures a docs linter (ruff `D` rules with `convention = "google"`, `eslint-plugin-jsdoc`),
   its config wins.
2. **Write the module header.** First line: the module's single responsibility. If you cannot say
   it in one sentence, flag the cohesion problem instead of writing a vague header. Add a
   `Sections:` index when the file has more than ~4 top-level symbols or ~80 lines; describe roles,
   not line numbers, so it stays true after edits.
3. **Document each public symbol's contract:**
   - Summary line: what it does, not how and not for which caller.
   - Parameters: meaning, units, valid ranges, and constraints such as "must already exist". Do
     not restate types the signature already declares.
   - Return value, every error it can raise, side effects (I/O, mutation, network), and ordering
     or concurrency assumptions.
4. **Fix stale docs** in any file you touch. A docstring describing old parameters is worse than none.
5. **Verify** with the docs linter when configured, and fix what it reports.

## Scope

- Public modules, classes, functions and exported symbols always get full documentation.
  Private helpers only when their behavior is not obvious from name and body.
- Inline comments explain *why* (a workaround, a non-obvious constraint). Never narrate lines.

## Example

```python
"""Order billing: computes taxed totals and records them in the billing log.

Sections:
    order_total()   — sums line items and applies the order's discount and tax.
    record_charge() — appends a charge entry to the billing log.
"""


def order_total(order: Order, tax_rate: Decimal) -> Decimal:
    """Computes the amount to charge for an order.

    Args:
        order: Order with at least one line item.
        tax_rate: Fraction between 0 and 1 applied after the discount.

    Returns:
        The total in the order's currency, rounded half-up to 2 decimals.

    Raises:
        ValueError: If the order has no items or tax_rate is outside [0, 1].
    """
```
