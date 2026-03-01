# Architecture

MoneyWarp is a Time Value of Money library built around the metaphor of "time-warping" financial instruments. It models personal loans with daily-compounding interest, flexible payment schedules, and a context-manager-based time machine that lets you observe any loan's state at an arbitrary date.

## Package Structure

```
money_warp/
├── __init__.py            # Public API exports
├── money.py               # Money (high-precision currency)
├── interest_rate.py       # InterestRate + CompoundingFrequency
├── time_context.py        # TimeContext (shared Warp-compatible time source)
├── cash_flow/
│   ├── entry.py           # CashFlowEntry (frozen data object)
│   ├── item.py            # CashFlowItem (temporal container with timeline)
│   ├── flow.py            # CashFlow (collection, resolves items)
│   └── query.py           # CashFlowQuery (SQLAlchemy-style filtering)
├── loan/
│   └── loan.py            # Loan state machine
├── scheduler/
│   ├── base.py            # BaseScheduler (abstract)
│   ├── price_scheduler.py           # PriceScheduler (French amortization)
│   └── inverted_price_scheduler.py  # InvertedPriceScheduler (SAC)
├── tax/
│   ├── base.py            # BaseTax (abstract), TaxResult, TaxInstallmentDetail
│   ├── iof.py             # IOF (Brazilian financial operations tax)
│   └── grossup.py         # grossup() function, GrossupResult
├── present_value.py       # PV, NPV, IRR, MIRR, discount_factor
├── tz.py                  # Timezone config, ensure_aware, tz_aware decorator
├── warp.py                # Warp context manager + WarpedTime
└── date_utils.py          # Date generation utilities
```

## Core Design Decisions

### Dual-Precision Money

`Money` stores a `raw_amount: Decimal` at full precision for intermediate calculations and exposes a `real_amount: Decimal` rounded to 2 decimal places for display and comparison. All arithmetic returns new `Money` instances (immutable value object). Comparisons (`==`, `<`, `<=`, `>`, `>=`) use `real_amount`, so two values that round to the same cents are considered equal. Both `Money` and `Decimal` are accepted on the right-hand side, so `Money("100.50") == Decimal("100.50")` works directly without extracting `.real_amount`.

### Explicit Interest Rates

`InterestRate` eliminates the "is 5 the rate or the percentage?" ambiguity. It stores a decimal rate plus a `CompoundingFrequency` enum (`DAILY`, `MONTHLY`, `QUARTERLY`, `SEMI_ANNUALLY`, `ANNUALLY`, `CONTINUOUS`). All conversions go through an effective annual rate as the canonical intermediate form. The `accrue(principal, days)` method computes compound interest on a principal over a number of days, centralising the formula that was previously duplicated across the `Loan` class.

String parsing accepts human-friendly formats like `"5.25% a"` or `"0.004167 m"`, as well as abbreviated (Brazilian/LatAm) notation: `"5.25% a.a."`, `"0.5% a.m."`, `"0.0137% a.d."`, `"2.75% a.t."`, `"3% a.s."`. The `str_style` constructor parameter (`"long"` default, or `"abbrev"`) controls how `__str__` renders the period label. Parsing an abbreviated string auto-sets `str_style="abbrev"` so that `str()` round-trips correctly. The style propagates through `to_daily()`, `to_monthly()`, and `to_annual()` conversions.

### Year Size (Day-Count Convention)

The `YearSize` enum controls how many days constitute one year for daily rate conversions: `commercial` (365, default) and `banker` (360). The `year_size` parameter on `InterestRate.__init__` defaults to `YearSize.commercial` for backward compatibility. It affects three areas:

- **Daily conversions** (`to_daily()`, `_to_effective_annual()` for DAILY rates): the exponent uses `year_size.value` instead of a hardcoded 365.
- **`to_periodic_rate()`**: the short-circuit check compares against `year_size.value` for DAILY frequencies, so a banker-based daily rate correctly matches `num_periods=360`.
- **`accrue()`**: inherits the correct daily rate through `to_daily()`.

Monthly, quarterly, semi-annual, and annual conversions are unaffected by year size (they always use 12, 4, 2, and 1 periods per year respectively). The `year_size` propagates through all conversion methods (`to_daily`, `to_monthly`, `to_annual`) and is shown in `__repr__` only when non-default.

### Temporal CashFlow Model (CashFlowEntry / CashFlowItem / CashFlow)

Cash-flow data is separated from time-awareness:

- **`CashFlowEntry`** (`cash_flow/entry.py`) — frozen dataclass holding `amount`, `datetime`, `description`, `category`. Pure data, no temporal behaviour.
- **`CashFlowItem`** (`cash_flow/item.py`) — temporal container wrapping a timeline of `CashFlowEntry` snapshots (or `None` for deletion). Key methods: `resolve()` (active entry at the current time), `update(effective_date, new_entry)`, `delete(effective_date)`. Each item holds a reference to a shared `TimeContext` so Warp compatibility comes for free.
- **`CashFlow`** (`cash_flow/flow.py`) — collection of `CashFlowItem` objects. Public iteration (`__iter__`, `__len__`, `__getitem__`, `items()`) resolves each item and filters out deleted entries, yielding `CashFlowEntry` objects. `raw_items()` exposes the underlying `CashFlowItem` containers for when callers need `update()`/`delete()`. The `query` property returns a `CashFlowQuery` builder that supports `filter_by()`, `order_by()`, `limit()`, `offset()`, and terminal methods.

Equality between `CashFlowItem` and `CashFlowEntry` uses Python's reflected-equality protocol — `CashFlowItem.__eq__` resolves and compares against the entry, so both `entry == item` and `item == entry` work transparently.

### Loan as State Machine

`Loan` does not store multiple cash flow versions. Instead it holds the loan parameters and a list of recorded payments, then generates cash flows on demand:

- `generate_expected_cash_flow()` — the contractual schedule (via the configured scheduler)
- `get_actual_cash_flow()` — expected + recorded payments + fine events
- `current_balance` — computed from principal balance + accrued interest + outstanding fines

This keeps the source of truth minimal and avoids stale derived data.

### Flexible Scheduling via Due Dates

Rather than encoding "monthly" or "bi-weekly" into the loan, the constructor accepts `due_dates: List[datetime]`. This supports irregular schedules, seasonal payments, and custom arrangements. Convenience functions in `date_utils.py` generate common date patterns.

### Three-Date Payment Model

Every recorded payment carries three dates: `payment_date` (when money moved), `interest_date` (cutoff for interest accrual), and `processing_date` (audit trail). Decoupling `interest_date` from `payment_date` enables early-payment discounts (fewer interest days) and mora interest on late payments (extra interest days beyond the due date). Sugar methods (`pay_installment`, `anticipate_payment`) set these dates automatically from `self.now()`.

### Payment Allocation, Fines, and Mora Interest

All payments allocate funds in strict priority: outstanding fines first, then accrued interest, then principal. Late payments trigger two costs: a flat fine (percentage of the missed installment, calculated from the original schedule) and mora interest (daily-compounded interest for the extra days beyond the due date). When a late payment is recorded, the interest is split into two `CashFlowItem` entries: regular interest (`"actual_interest"`, up to the due date) and mora interest (`"actual_mora_interest"`, beyond the due date). A configurable `grace_period_days` delays fine application. The `fines_applied` dict prevents duplicate fines for the same due date.

All `CashFlowItem` categories use explicit prefixes: `expected_` for projected schedule items (`"expected_disbursement"`, `"expected_interest"`, `"expected_principal"`) and `actual_` for recorded payments (`"actual_interest"`, `"actual_mora_interest"`, `"actual_principal"`, `"actual_fine"`).

### Timezone-Aware Datetimes

All datetimes inside the library are timezone-aware. The `tz` module (`tz.py`) provides the configuration:

- **`get_tz()` / `set_tz()`** — read or change the default timezone (UTC by default). `set_tz` accepts a string like `"America/Sao_Paulo"` or a `tzinfo` instance.
- **`now()`** — returns `datetime.now(get_tz())`, always aware.
- **`ensure_aware(dt)`** — attaches the configured timezone to naive datetimes; returns aware datetimes unchanged.
- **`tz_aware` decorator** — applied to public methods and functions that accept datetime arguments. At call time it inspects all positional and keyword arguments: `datetime` values are passed through `ensure_aware`, and `list[datetime]` values are coerced element-wise. This eliminates manual `ensure_aware` calls at every input boundary.

Uses `zoneinfo.ZoneInfo` from the standard library (no extra dependency).

### Time Awareness via TimeContext

`TimeContext` (`time_context.py`) is a shared, overridable time source. The `Loan` creates one at construction and passes the same instance to every `CashFlowItem` it creates. `deepcopy` preserves the shared reference within the clone, so `Warp` only needs to call `_time_ctx.override(WarpedTime(target))` on the cloned loan — every item in the clone immediately sees the warped time.

The `Loan` calls `self.now()` internally, which delegates to `self._time_ctx.now()`. By default `_time_ctx` wraps a `_DefaultTimeSource` instance (from `tz.py`) whose `now()` returns a timezone-aware UTC datetime. The `Warp` context manager deep-clones the loan and overrides the shared `TimeContext` with a `WarpedTime` instance that returns a fixed aware date.

## Component Relationships

```
Money ─► CashFlowEntry ─► CashFlowItem ─► CashFlow
                            ▲                  │
                  TimeContext                   │
                    ▲                           │
InterestRate ──────────────────────────────► Loan
                                            │   │
                                 Scheduler ◄─┘   └──► Warp
                                    │          (clones + overrides TimeContext)
                                    ▼
                               BaseTax (IOF)
                                    │
                               grossup()
```

- `CashFlowEntry` is a frozen data record (`amount: Money`, `datetime`, etc.)
- `CashFlowItem` wraps a timeline of `CashFlowEntry` snapshots; `resolve()` returns the active entry
- `CashFlow` holds `CashFlowItem` containers; public iteration yields active `CashFlowEntry` objects
- `Loan` creates a shared `TimeContext` passed to all its `CashFlowItem` instances
- `Loan` delegates schedule generation to a `BaseScheduler` subclass
- `Loan` optionally stores `BaseTax` instances for tax reporting in cash flows
- `BaseTax` implementations (e.g. `IOF`) compute taxes from a `PaymentSchedule`
- `grossup()` uses a scheduler and taxes to compute a grossed-up principal
- `Warp` deep-clones a `Loan` and overrides the shared `TimeContext`
