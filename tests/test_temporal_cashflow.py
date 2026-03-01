"""Tests for temporal CashFlowItem behavior (resolve, update, delete, Warp)."""

import copy
from datetime import datetime, timezone

from money_warp import (
    CashFlow,
    CashFlowItem,
    InterestRate,
    Loan,
    Money,
    Warp,
)
from money_warp.cash_flow.entry import CashFlowEntry
from money_warp.time_context import TimeContext
from money_warp.warp import WarpedTime

# -- CashFlowItem resolve --------------------------------------------------


def test_cashflow_item_resolve_returns_entry():
    entry = CashFlowEntry(
        amount=Money("100.00"),
        datetime=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    item = CashFlowItem(entry=entry)
    assert item.resolve() == entry


def test_cashflow_item_delete_returns_none_after_effective_date():
    ctx = TimeContext()
    entry = CashFlowEntry(
        amount=Money("100.00"),
        datetime=datetime(2024, 6, 15, tzinfo=timezone.utc),
    )
    item = CashFlowItem(entry=entry, time_context=ctx)

    delete_date = datetime(2024, 3, 1, tzinfo=timezone.utc)
    item.delete(delete_date)

    ctx.override(WarpedTime(datetime(2024, 2, 28, tzinfo=timezone.utc)))
    assert item.resolve() == entry

    ctx.override(WarpedTime(datetime(2024, 3, 2, tzinfo=timezone.utc)))
    assert item.resolve() is None


def test_cashflow_item_update_changes_entry_after_effective_date():
    ctx = TimeContext()
    old_entry = CashFlowEntry(
        amount=Money("100.00"),
        datetime=datetime(2024, 6, 15, tzinfo=timezone.utc),
        description="original",
    )
    new_entry = CashFlowEntry(
        amount=Money("200.00"),
        datetime=datetime(2024, 6, 15, tzinfo=timezone.utc),
        description="updated",
    )
    item = CashFlowItem(entry=old_entry, time_context=ctx)

    update_date = datetime(2024, 3, 1, tzinfo=timezone.utc)
    item.update(update_date, new_entry)

    ctx.override(WarpedTime(datetime(2024, 2, 28, tzinfo=timezone.utc)))
    assert item.resolve() == old_entry

    ctx.override(WarpedTime(datetime(2024, 3, 2, tzinfo=timezone.utc)))
    assert item.resolve() == new_entry


def test_cashflow_item_resolve_reflects_time_context_override():
    ctx = TimeContext()
    entry = CashFlowEntry(
        amount=Money("500.00"),
        datetime=datetime(2024, 6, 15, tzinfo=timezone.utc),
    )
    item = CashFlowItem(entry=entry, time_context=ctx)
    item.delete(datetime(2024, 4, 1, tzinfo=timezone.utc))

    ctx.override(WarpedTime(datetime(2024, 3, 15, tzinfo=timezone.utc)))
    assert item.resolve() == entry

    ctx.override(WarpedTime(datetime(2024, 5, 1, tzinfo=timezone.utc)))
    assert item.resolve() is None


# -- CashFlow filters deleted items ----------------------------------------


def test_cashflow_items_filters_deleted():
    ctx = TimeContext()
    items = [
        CashFlowItem(
            Money("100.00"),
            datetime(2024, 1, 15, tzinfo=timezone.utc),
            time_context=ctx,
        ),
        CashFlowItem(
            Money("200.00"),
            datetime(2024, 2, 15, tzinfo=timezone.utc),
            time_context=ctx,
        ),
        CashFlowItem(
            Money("300.00"),
            datetime(2024, 3, 15, tzinfo=timezone.utc),
            time_context=ctx,
        ),
    ]
    cf = CashFlow(items)

    items[1].delete(datetime(2024, 1, 10, tzinfo=timezone.utc))

    assert len(cf) == 2
    assert cf[0].amount == Money("100.00")
    assert cf[1].amount == Money("300.00")


# -- TimeContext deepcopy ---------------------------------------------------


def test_time_context_shared_in_deepcopy():
    ctx = TimeContext()
    item_a = CashFlowItem(
        Money("100.00"),
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        time_context=ctx,
    )
    item_b = CashFlowItem(
        Money("200.00"),
        datetime(2024, 2, 15, tzinfo=timezone.utc),
        time_context=ctx,
    )

    cloned_a, cloned_b = copy.deepcopy((item_a, item_b))

    assert cloned_a._time_ctx is cloned_b._time_ctx
    assert cloned_a._time_ctx is not ctx


# -- Warp overrides TimeContext ---------------------------------------------


def test_warp_overrides_time_context():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    target = datetime(2024, 2, 15, tzinfo=timezone.utc)
    with Warp(loan, target) as warped:
        assert warped.now() == target
