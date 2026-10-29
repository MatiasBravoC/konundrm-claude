# Google-style doc-comments by language

## Contents

- Python
- TypeScript and JavaScript
- Java
- Go
- Other languages

## Python

Google Python Style Guide, section 3.8. Triple-quoted docstring right under `def`/`class`; summary
line ending in a period; blank line; then only the sections that apply, in this order: `Args:`,
`Returns:` (or `Yields:`), `Raises:`.

```python
def apply_discount(total: Decimal, pct: Decimal) -> Decimal:
    """Applies a percentage discount to a total.

    Args:
        total: Pre-discount amount in the store's base currency.
        pct: Discount fraction between 0 and 1.

    Returns:
        The discounted total.

    Raises:
        ValueError: If pct is not between 0 and 1.
    """
```

Classes describe what an instance represents and list public attributes under `Attributes:`.
Modules start with a docstring stating their responsibility. Enforce with ruff:
`[tool.ruff.lint] select = ["D"]` and `[tool.ruff.lint.pydocstyle] convention = "google"`.

## TypeScript and JavaScript

TSDoc in TypeScript, JSDoc in JavaScript. Do not repeat types the annotations already declare.

```ts
/**
 * Applies a percentage discount to a total.
 *
 * @param total - Pre-discount amount in the store's base currency.
 * @param pct - Discount fraction between 0 and 1.
 * @returns The discounted total.
 * @throws {RangeError} If `pct` is not between 0 and 1.
 */
export function applyDiscount(total: number, pct: number): number { … }
```

In plain JavaScript, include types: `@param {number} total - …`. React components get a comment
describing what they render and what each prop means; the `Props` type carries the shapes.
Module header: a `@file` or `@packageDocumentation` block at the top. Enforce with
`eslint-plugin-jsdoc` (`flat/recommended-typescript` in TS projects).

## Java

Google Java Style Guide, section 7. Summary fragment first, then block tags in order `@param`,
`@return`, `@throws`, each with a non-empty description.

```java
/**
 * Applies a percentage discount to a total.
 *
 * @param total the pre-discount amount
 * @param pct the discount fraction, between 0 and 1
 * @return the discounted total
 * @throws IllegalArgumentException if pct is not between 0 and 1
 */
```

## Go

Doc comments are full sentences that start with the identifier's name. Package comment in
`doc.go` or above `package`, starting with "Package <name>".

```go
// ApplyDiscount returns total reduced by pct. It panics if pct is outside [0, 1].
func ApplyDiscount(total, pct float64) float64 { … }
```

## Other languages

Keep the same shape (summary, parameters, return, errors, side effects) in the language's standard
doc syntax: XML doc comments (`///`) in C#, rustdoc (`///` with `# Errors` and `# Panics`
sections) in Rust, Doxygen in C++.
