# Architecture

MoneyWarp is a Time Value of Money library built around the metaphor of "time-warping" financial instruments. It models personal loans with daily-compounding interest, flexible payment schedules, and a context-manager-based time machine that lets you observe any loan's state at an arbitrary date.

## Package Structure

```
money_warp/
├── __init__.py            # Public API exports
├── money.py               # Money (high-precision currency)
├── interest_rate.py       # InterestRate + CompoundingFrequency
├── cash_flow/
│   ├── item.py            # CashFlowItem (single transaction)
│   ├── flow.py            # CashFlow (collection of items)
│   └── query.py           # CashFlowQuery (SQLAlchemy-style filtering)
├── loan/
│   └── loan.py            # Loan state machine
├── scheduler/
│   ├── base.py            # BaseScheduler (abstract)
│   ├── price.py           # PriceScheduler (French amortization)
│   └── inverted_price.py  # InvertedPriceScheduler (SAC)
├── present_value.py       # PV, NPV, IRR, MIRR, discount_factor
├── warp.py                # Warp context manager + WarpedTime
└── date_utils.py          # Date generation utilities
```

## Core Design Decisions

### Dual-Precision Money

`Money` stores a `raw_amount: Decimal` at full precision for intermediate calculations and exposes a `real_amount: Decimal` rounded to 2 decimal places for display and comparison. All arithmetic returns new `Money` instances (immutable value object). Comparisons use `real_amount`, so two values that round to the same cents are considered equal.

### Explicit Interest Rates

`InterestRate` eliminates the "is 5 the rate or the percentage?" ambiguity. It stores a decimal rate plus a `CompoundingFrequency` enum (`DAILY`, `MONTHLY`, `QUARTERLY`, `SEMI_ANNUALLY`, `ANNUALLY`, `CONTINUOUS`). All conversions go through an effective annual rate as the canonical intermediate form.

String parsing accepts human-friendly formats like `"5.25% a"` or `"0.004167 m"`.

### CashFlow as a Query-able Container

`CashFlow` holds a list of `CashFlowItem` objects (amount + datetime + optional description/category). The `query` property returns a `CashFlowQuery` builder that supports `filter_by()`, `order_by()`, `limit()`, `offset()`, and terminal methods like `all()`, `first()`, `sum_amounts()`, and `to_cash_flow()`. This lets calling code express complex filters without manual loops.

### Loan as State Machine

`Loan` does not store multiple cash flow versions. Instead it holds the loan parameters and a list of recorded payments, then generates cash flows on demand:

- `generate_expected_cash_flow()` — the contractual schedule (via the configured scheduler)
- `get_actual_cash_flow()` — expected + recorded payments + fine events
- `current_balance` — computed from principal balance + accrued interest + outstanding fines

This keeps the source of truth minimal and avoids stale derived data.

### Flexible Scheduling via Due Dates

Rather than encoding "monthly" or "bi-weekly" into the loan, the constructor accepts `due_dates: List[datetime]`. This supports irregular schedules, seasonal payments, and custom arrangements. Convenience functions in `date_utils.py` generate common date patterns.

### Time Awareness via Function Replacement

The loan calls `self.now()` internally, which delegates to `self.datetime_func.now()`. Normally `datetime_func` is Python's `datetime` class. The `Warp` context manager deep-clones the loan and replaces `datetime_func` with a `WarpedTime` instance that returns a fixed date — every time-dependent method then sees the warped date without any code changes.

## Component Relationships

```
Money ──────────► CashFlowItem ──────────► CashFlow
                                              │
InterestRate ─────────────────────────────► Loan
                                           │   │
                                Scheduler ◄─┘   └──► Warp
                                                     (clones + time-warps)
```

- `CashFlowItem.amount` is a `Money`
- `CashFlow` aggregation methods return `Money`
- `Loan` uses `InterestRate` for compounding, `Money` for amounts, and generates `CashFlow` objects
- `Loan` delegates schedule generation to a `BaseScheduler` subclass
- `Warp` deep-clones a `Loan` and replaces its time source
