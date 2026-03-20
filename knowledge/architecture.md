# Architecture

MoneyWarp is a Time Value of Money library built around the metaphor of "time-warping" financial instruments. It models personal loans with daily-compounding interest, flexible payment schedules, and a context-manager-based time machine that lets you observe any loan's state at an arbitrary date.

## Package Structure

```
money_warp/
├── __init__.py            # Public API exports
├── money.py               # Money (high-precision currency)
├── rate.py                # Rate (signed base) + CompoundingFrequency + YearSize
├── interest_rate.py       # InterestRate (non-negative refinement of Rate)
├── time_context.py        # TimeContext (shared Warp-compatible time source)
├── cash_flow/
│   ├── entry.py           # CashFlowEntry (abstract base), Expected/HappenedCashFlowEntry
│   ├── item.py            # CashFlowItem (temporal container with timeline)
│   ├── flow.py            # CashFlow (collection, resolves items)
│   └── query.py           # CashFlowQuery (SQLAlchemy-style filtering)
├── billing_cycle/
│   ├── base.py            # BaseBillingCycle (abstract)
│   └── monthly.py         # MonthlyBillingCycle (fixed calendar day)
├── credit_card/
│   ├── credit_card.py     # CreditCard state machine
│   └── statement.py       # Statement (frozen derived view)
├── loan/
│   ├── loan.py               # Loan facade (~760 lines, down from ~1411)
│   ├── interest_calculator.py # InterestCalculator (stateless rate math)
│   ├── fine_tracker.py        # FineTracker (fine state + late-payment logic)
│   ├── payment_ledger.py      # PaymentLedger (CashFlow-backed payment recording)
│   ├── settlement_engine.py   # SettlementEngine (settlement/installment building)
│   ├── tvm.py                 # TVM standalone functions (PV, IRR, anticipation)
│   ├── installment.py         # Installment dataclass
│   └── settlement.py          # Settlement, SettlementAllocation dataclasses
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
├── warp.py                # Warp context manager + WarpedTime (generic)
└── date_utils.py          # Date generation utilities
```

## Core Design Decisions

### Dual-Precision Money

`Money` stores a `raw_amount: Decimal` at full precision for intermediate calculations and exposes a `real_amount: Decimal` rounded to 2 decimal places for display and comparison. All arithmetic returns new `Money` instances (immutable value object). Comparisons (`==`, `<`, `<=`, `>`, `>=`) use `real_amount`, so two values that round to the same cents are considered equal. The right-hand side of comparisons accepts `Money`, `Decimal`, `int`, and `float`, so `Money("100.50") == Decimal("100.50")` and `Money("100") == 100` both work directly. `float(money)` returns `float(raw_amount)` — full internal precision, useful for interop with libraries that expect plain floats.

Money is registered as `numbers.Real` (via `numbers.Real.register(Money)`) so it participates in Python's numeric tower. This enables `pytest.approx(Money(...))` and other numeric-protocol-aware code to recognise Money as a real number. Reflected operators (`__radd__`, `__rsub__`, `__rmul__`) accept `Decimal`, `int`, and `float` on the left-hand side, so expressions like `Decimal("200") - Money("100")` and `1.5 * Money("100")` return `Money`.

### Rate and InterestRate

The library uses two rate types to model the domain distinction between computed metrics and contractual parameters:

- **`Rate`** (`rate.py`) — signed, general-purpose base type. Stores a decimal rate plus a `CompoundingFrequency` enum (`DAILY`, `MONTHLY`, `QUARTERLY`, `SEMI_ANNUALLY`, `ANNUALLY`, `CONTINUOUS`). Supports positive, negative, and zero values. All conversions go through an effective annual rate as the canonical intermediate form. Used as the return type for IRR and MIRR, and accepted by `present_value()` and `discount_factor()`.

- **`InterestRate`** (`interest_rate.py`) — non-negative refinement of `Rate`. Adds a validation that rejects negative rates at construction time (both string and numeric). Also provides the `accrue(principal, days)` method for computing compound interest, which belongs exclusively to contractual rates. Used for loan terms, scheduler inputs, and annuity/perpetuity calculations.

Conversion methods (`to_daily()`, `to_monthly()`, `to_annual()`) use `self.__class__(...)` so subclass identity is preserved.

String parsing accepts human-friendly formats like `"5.25% a"`, `"-2.5% annual"` (negatives only for `Rate`), or `"0.004167 m"`, as well as abbreviated (Brazilian/LatAm) notation: `"5.25% a.a."`, `"0.5% a.m."`, `"0.0137% a.d."`, `"2.75% a.t."`, `"3% a.s."`. The `str_style` constructor parameter (`"long"` default, or `"abbrev"`) controls how `__str__` renders the period label. Parsing an abbreviated string auto-sets `str_style="abbrev"` so that `str()` round-trips correctly. The style propagates through conversions.

### Year Size (Day-Count Convention)

The `YearSize` enum controls how many days constitute one year for daily rate conversions: `commercial` (365, default) and `banker` (360). The `year_size` parameter on `Rate.__init__` (and `InterestRate.__init__`) defaults to `YearSize.commercial` for backward compatibility. It affects three areas:

- **Daily conversions** (`to_daily()`, `_to_effective_annual()` for DAILY rates): the exponent uses `year_size.value` instead of a hardcoded 365.
- **`to_periodic_rate()`**: the short-circuit check compares against `year_size.value` for DAILY frequencies, so a banker-based daily rate correctly matches `num_periods=360`.
- **`accrue()`**: inherits the correct daily rate through `to_daily()`.

Monthly, quarterly, semi-annual, and annual conversions are unaffected by year size (they always use 12, 4, 2, and 1 periods per year respectively). The `year_size` propagates through all conversion methods (`to_daily`, `to_monthly`, `to_annual`) and is shown in `__repr__` only when non-default.

### Temporal CashFlow Model (CashFlowEntry / CashFlowItem / CashFlow)

Cash-flow data is separated from time-awareness:

- **`CashFlowEntry`** (`cash_flow/entry.py`) — abstract frozen dataclass holding `amount`, `datetime`, `description`, `category`, and an abstract `kind` property. Two concrete subclasses encode whether an entry is projected or recorded:
  - **`ExpectedCashFlowEntry`** — `kind` returns `CashFlowType.EXPECTED`.
  - **`HappenedCashFlowEntry`** — `kind` returns `CashFlowType.HAPPENED`.
- **`CashFlowType`** (`cash_flow/entry.py`) — `str` enum with values `EXPECTED` and `HAPPENED`. Used for filtering (`filter_by(kind=...)`, `cf.query.expected`, `cf.query.happened`).
- **`CashFlowItem`** (`cash_flow/item.py`) — temporal container wrapping a timeline of `CashFlowEntry` snapshots (or `None` for deletion). Key methods: `resolve()` (active entry at the current time), `update(effective_date, new_entry)`, `delete(effective_date)`. The constructor accepts `kind=CashFlowType.HAPPENED` (default) to instantiate the correct entry subclass. Each item holds a reference to a shared `TimeContext` so Warp compatibility comes for free.
- **`CashFlow`** (`cash_flow/flow.py`) — collection of `CashFlowItem` objects. Public iteration (`__iter__`, `__len__`, `__getitem__`, `items()`) resolves each item and filters out deleted entries, yielding `CashFlowEntry` objects. `raw_items()` exposes the underlying `CashFlowItem` containers for when callers need `update()`/`delete()`. The `query` property returns a `CashFlowQuery` builder that supports `filter_by()`, `order_by()`, `limit()`, `offset()`, and terminal methods. Convenience methods `filter_by_kind()` and `filter_by_category()` provide direct filtering shortcuts.

Equality between `CashFlowItem` and `CashFlowEntry` uses Python's reflected-equality protocol — `CashFlowItem.__eq__` resolves and compares against the entry, so both `entry == item` and `item == entry` work transparently. Entries of different kinds (Expected vs Happened) are never equal, even with identical field values.

### Loan as Thin Facade

`Loan` is a facade that orchestrates five focused components:

- **`InterestCalculator`** — stateless interest math (regular + mora split).
- **`FineTracker`** — fine state (`fines_applied`) and late-payment detection.
- **`PaymentLedger`** — records payments as tagged CashFlowItems in a shared `CashFlow`. Replaces four fragile parallel lists with category-tag queries (`settlement:N`).
- **`SettlementEngine`** — pure computation of settlements and installments from ledger data.
- **`tvm.py`** — standalone functions for PV, IRR, and anticipation (eliminates circular imports).

The shared `CashFlow` in the `PaymentLedger` is the single source of truth for payment data. Schedule generation (`generate_expected_cash_flow`, `get_original_schedule`, `get_amortization_schedule`) and cash-flow assembly (`get_actual_cash_flow`) stay in `Loan`.

### Flexible Scheduling via Due Dates

Rather than encoding "monthly" or "bi-weekly" into the loan, the constructor accepts `due_dates: List[date]` (calendar due dates). This supports irregular schedules, seasonal payments, and custom arrangements. Convenience functions in `date_utils.py` return `List[datetime]`; use `tz.to_date()` element-wise when passing their output into `Loan` and schedulers.

### Three-Date Payment Model

Every recorded payment carries three dates: `payment_date` (when money moved), `interest_date` (cutoff for interest accrual), and `processing_date` (audit trail). Decoupling `interest_date` from `payment_date` enables early-payment discounts (fewer interest days) and mora interest on late payments (extra interest days beyond the due date). Sugar methods (`pay_installment`, `anticipate_payment`) set these dates automatically from `self.now()`.

### Payment Allocation, Fines, and Mora Interest

All payments allocate funds in strict priority: outstanding fines first, then accrued interest, then principal. Late payments trigger two costs: a flat fine (percentage of the missed installment, calculated from the original schedule) and mora interest (daily-compounded interest for the extra days beyond the due date). When a late payment is recorded, the interest is split into two `CashFlowItem` entries: regular interest (`"interest"`, up to the due date) and mora interest (`"mora_interest"`, beyond the due date). A configurable `grace_period_days` delays fine application. Fine state is managed by `FineTracker`.

Payment items are stored in a shared `CashFlow` via `PaymentLedger`. Each item is tagged with both its type (e.g. `"interest"`) and its settlement group (e.g. `"settlement:1"`) using the `frozenset[str]` category system. This eliminates offset-based grouping and makes same-time-payment bugs impossible by design.

The expected-vs-happened distinction is structural: expected schedule items use `ExpectedCashFlowEntry` (kind=EXPECTED) and recorded payments use `HappenedCashFlowEntry` (kind=HAPPENED). Categories are frozensets of string tags: `{"disbursement"}`, `{"interest"}`, `{"principal"}`, `{"fine"}`, `{"mora_interest"}`, `{"tax"}`, `{"interest", "settlement:1"}`, etc.

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
Rate ◄── InterestRate ──────────────┬──────► Loan ──► irr() returns Rate
                                    │       │   │
                                    │  Scheduler ◄─┘
                                    │       │       └──► Warp (generic)
                                    │       ▼          (clones + overrides TimeContext
                                    │  BaseTax (IOF)    + calls _on_warp)
                                    │       │
                                    │  grossup()
                                    │
                                    └──────► CreditCard
                                             │
                                    BaseBillingCycle ◄─┘
                                        ▲
                                   MonthlyBillingCycle
```

- `CashFlowEntry` is an abstract frozen data record with `ExpectedCashFlowEntry` and `HappenedCashFlowEntry` subclasses
- `CashFlowItem` wraps a timeline of `CashFlowEntry` snapshots; `resolve()` returns the active entry
- `CashFlow` holds `CashFlowItem` containers; public iteration yields active `CashFlowEntry` objects
- `Loan` creates a shared `TimeContext` passed to all its `CashFlowItem` instances
- `Loan` delegates schedule generation to a `BaseScheduler` subclass
- `Loan` optionally stores `BaseTax` instances for tax reporting in cash flows
- `BaseTax` implementations (e.g. `IOF`) compute taxes from a `PaymentSchedule`
- `grossup()` uses a scheduler and taxes to compute a grossed-up principal
- `CreditCard` creates a shared `TimeContext` and records transactions as `CashFlowItem` objects
- `CreditCard` delegates billing-cycle dates to a `BaseBillingCycle` subclass
- `Warp` is generic — deep-clones any object with `_time_ctx` and calls `_on_warp()` if present
