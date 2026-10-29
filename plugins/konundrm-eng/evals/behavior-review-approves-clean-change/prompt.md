---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
Revisa este cambio antes de abrir el pull request:

```diff
--- a/src/billing/discounts.py
+++ b/src/billing/discounts.py
@@ -1 +1,24 @@
 """Discount rules applied to order totals."""
+
+from decimal import ROUND_HALF_UP, Decimal
+
+
+def apply_percentage_discount(total: Decimal, percent: Decimal) -> Decimal:
+    """Applies a percentage discount to an order total.
+
+    Args:
+        total: Order total before the discount; must not be negative.
+        percent: Discount between 0 and 100.
+
+    Returns:
+        The discounted total, rounded half-up to 2 decimals.
+
+    Raises:
+        ValueError: If total is negative or percent is outside [0, 100].
+    """
+    if total < 0 or not Decimal(0) <= percent <= Decimal(100):
+        raise ValueError(f"invalid discount: total={total}, percent={percent}")
+    discounted = total * (Decimal(100) - percent) / Decimal(100)
+    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
--- /dev/null
+++ b/tests/billing/test_discounts.py
@@ -0,0 +1,19 @@
+from decimal import Decimal
+
+import pytest
+
+from billing.discounts import apply_percentage_discount
+
+
+def test_applies_ten_percent_to_the_total():
+    assert apply_percentage_discount(Decimal("200.00"), Decimal("10")) == Decimal("180.00")
+
+
+def test_rounds_half_up_to_cents():
+    assert apply_percentage_discount(Decimal("0.05"), Decimal("50")) == Decimal("0.03")
+
+
+@pytest.mark.parametrize(("total", "percent"), [(Decimal("-1"), Decimal("10")), (Decimal("1"), Decimal("101"))])
+def test_rejects_negative_totals_and_percentages_outside_0_to_100(total, percent):
+    with pytest.raises(ValueError, match="invalid discount"):
+        apply_percentage_discount(total, percent)
```
