# Cash Flow

The cash flow module models financial transactions over time with temporal awareness.

## Category System

`CashFlowEntry.category` is a `frozenset[str]`, enabling multi-tagging. A single item can belong to multiple groups simultaneously.

### Auto-normalization

`CashFlowItem` normalizes the `category` parameter:

- `"interest"` → `frozenset({"interest"})`
- `{"interest", "settlement:1"}` → `frozenset({"interest", "settlement:1"})`
- `None` → `frozenset()`

The `_normalize_category` function in `entry.py` handles all conversions. The `CategoryInput` type alias accepts `str | Set[str] | FrozenSet[str] | None`.

### Query Semantics

`CashFlowQuery.filter_by(category=...)`:

- **String argument** (`category="interest"`): membership check — returns items where `"interest" in item.category`.
- **Set/frozenset argument** (`category={"interest", "settlement:1"}`): subset check — returns items where all specified tags are present.

### Consumer Patterns

```python
# Check if an entry has a specific category
"interest" in entry.category          # True if tagged with "interest"

# Check overlap with a set of categories
not entry.category.isdisjoint({"principal", "interest"})  # True if any match

# Empty category (was None)
not entry.category                     # True when frozenset is empty
```

### Loan Payment Tags

The `PaymentLedger` tags each payment item with both its type and settlement group:

| Example tags | Meaning |
|---|---|
| `{"interest", "settlement:1"}` | Interest portion of the first payment |
| `{"principal", "settlement:2"}` | Principal portion of the second payment |
| `{"fine", "settlement:1"}` | Fine portion of the first payment |

This enables `ledger.items_for_settlement(n)` to query by `settlement:N` tag instead of offset-based slicing.

## Design Decisions

### frozenset over Optional[str]

The original `Optional[str]` category forced a single label per item. The `PaymentLedger` needed to group items by payment event while preserving their type identity. A `frozenset[str]` allows both: `{"interest", "settlement:1"}`.

### Backward Compatibility

Passing `category="interest"` still works — the `CashFlowItem` constructor normalizes it. `filter_by(category="interest")` uses membership check, so it finds items tagged `{"interest", "settlement:1"}` as well as `{"interest"}`.
