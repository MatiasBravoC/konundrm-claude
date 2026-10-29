# Design: <Feature name>

- **Spec:** [requirements.md](requirements.md)
- **Status:** Draft <!-- Draft → Approved → Done -->

## Overview

<How the feature works in 3–5 sentences, naming the modules involved.>

## Module ownership

| Responsibility | Owner module | New or extended | Why there | Covers |
| --- | --- | --- | --- | --- |
| <one-sentence responsibility> | `src/…/module.py` | Extended | <it already owns X> | R1.1, R1.2 |

**Duplicates found:** <where the same logic already exists and how it will be consolidated, or "none">.

## Interfaces

```<language>
<public signatures, types and errors the tasks will implement>
```

## Data flow

<Request → module → module → storage/response. A short list or a mermaid sequence diagram.>

## Dependency rules

<Layers touched and confirmation that no inner layer imports an outer one; new architecture
contracts to add, if any.>

## Alternatives considered

- <Option> — rejected because <reason>.

## Threats

<!-- Required when any task is high risk (Standards → Security); otherwise write "None: no trust
boundary changes". One row per boundary the feature crosses (user → API, service → database,
app → third party). -->

| Boundary | What could go wrong (spoofing, tampering, disclosure, denial of service, elevation) | Control | Covers |
| --- | --- | --- | --- |
| <user → POST /coupons> | <a user applies another user's coupon> | <ownership check in `coupons/service.py`> | R2.1 |

## Delivery

<How the slices in tasks.md reach users: which slice makes the feature reachable, the flag or
unwired entry point that hides it until then, and how to roll back each slice (revert, flag off,
data migration down-step).>

## Risks

- <Risk> — <mitigation>.
