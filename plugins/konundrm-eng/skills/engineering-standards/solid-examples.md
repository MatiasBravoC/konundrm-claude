# SOLID: before and after

Each example shows the smallest violation a reviewer should recognise and the smallest fix.
Python is used for brevity; the same shapes apply in TypeScript.

## Contents

- Single responsibility
- Open/closed
- Liskov substitution
- Interface segregation
- Dependency inversion

## Single responsibility

```python
# Before: three reasons to change (pricing rules, persistence, notification channel).
def checkout(cart, db, mailer):
    total = sum(i.price * i.qty for i in cart.items) * (1 - cart.discount)
    db.save_order(cart.id, total)
    mailer.send(cart.email, f"Total: {total}")

# After: each function owns one decision; the use case only orchestrates.
def order_total(cart) -> Decimal: ...
def place_order(cart, orders: OrderRepository, notifier: Notifier) -> Order:
    order = orders.save(cart.id, order_total(cart))
    notifier.order_placed(order)
    return order
```

## Open/closed

```python
# Before: every new export format edits this function (and its twins elsewhere).
def export(report, kind):
    if kind == "pdf": ...
    elif kind == "csv": ...

# After: a new format is a new class registered once; existing code is untouched.
class Exporter(Protocol):
    def export(self, report: Report) -> bytes: ...

EXPORTERS: dict[str, Exporter] = {"pdf": PdfExporter(), "csv": CsvExporter()}
```

Apply this only once the second or third variant exists. One `if` is not a violation.

## Liskov substitution

```python
# Before: callers of Repo.save() now crash when handed a ReadOnlyRepo.
class ReadOnlyRepo(Repo):
    def save(self, item):
        raise NotImplementedError

# After: model the capability honestly; writers ask for a WritableRepo.
class Reader(Protocol):
    def get(self, id: str) -> Item: ...
class Writer(Reader, Protocol):
    def save(self, item: Item) -> None: ...
```

## Interface segregation

```ts
// Before: the report job can now break when unrelated Storage methods change.
function buildReport(storage: Storage) { return storage.get("sales"); }

// After: depend on the one capability used.
interface KeyReader { get(key: string): Promise<Blob>; }
function buildReport(source: KeyReader) { return source.get("sales"); }
```

## Dependency inversion

```python
# Before: domain logic is welded to an SDK; it cannot be tested without AWS.
class InvoiceService:
    def archive(self, invoice):
        boto3.client("s3").put_object(Bucket="invoices", Key=invoice.id, Body=invoice.pdf)

# After: the domain owns the abstraction; infrastructure implements it.
class InvoiceArchive(Protocol):          # domain/ports.py
    def store(self, invoice_id: str, pdf: bytes) -> None: ...

class S3InvoiceArchive:                  # infrastructure/s3_archive.py
    def store(self, invoice_id, pdf): self._client.put_object(...)

class InvoiceService:                    # domain/invoices.py
    def __init__(self, archive: InvoiceArchive): self._archive = archive
```
