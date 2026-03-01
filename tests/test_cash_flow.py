"""Tests for CashFlow and CashFlowItem classes - following project patterns."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import CashFlow, CashFlowItem, CashFlowQuery, Money


# CashFlowItem Creation Tests
@pytest.mark.parametrize(
    "amount,expected_amount",
    [
        (Money("100.50"), Money("100.50")),
        ("100.50", Money("100.50")),
        (100, Money("100.00")),
        (Decimal("100.50"), Money("100.50")),
    ],
)
def test_cash_flow_item_creation_from_various_types(amount, expected_amount):
    item = CashFlowItem(amount, datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.amount == expected_amount


def test_cash_flow_item_creation_with_all_fields():
    item = CashFlowItem(Money("500.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Loan payment", "payment")
    assert item.amount == Money("500.00")
    assert item.datetime == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert item.description == "Loan payment"
    assert item.category == "payment"


def test_cash_flow_item_creation_minimal_fields():
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.amount == Money("100.00")
    assert item.datetime == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert item.description is None
    assert item.category is None


# CashFlowItem Flow Direction Tests
def test_cash_flow_item_is_inflow_positive_amount():
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.is_inflow()


def test_cash_flow_item_is_outflow_negative_amount():
    item = CashFlowItem(Money("-100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.is_outflow()


def test_cash_flow_item_is_zero_zero_amount():
    item = CashFlowItem(Money.zero(), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.is_zero()


def test_cash_flow_item_inflow_not_outflow():
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert not item.is_outflow()


def test_cash_flow_item_outflow_not_inflow():
    item = CashFlowItem(Money("-100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert not item.is_inflow()


# CashFlowItem Equality Tests
def test_cash_flow_item_equality_same_values():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Payment", "loan")
    item2 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Payment", "loan")
    assert item1 == item2


def test_cash_flow_item_equality_different_amounts():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    item2 = CashFlowItem(Money("200.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item1 != item2


def test_cash_flow_item_equality_different_datetimes():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    item2 = CashFlowItem(Money("100.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc))
    assert item1 != item2


def test_cash_flow_item_equality_different_descriptions():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Payment 1")
    item2 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Payment 2")
    assert item1 != item2


def test_cash_flow_item_equality_different_categories():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="loan")
    item2 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="investment")
    assert item1 != item2


def test_cash_flow_item_equality_with_non_cash_flow_item():
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item != "not a cash flow item"


# CashFlowItem String Representation Tests
def test_cash_flow_item_string_representation_with_description():
    item = CashFlowItem(Money("100.50"), datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc), "Loan payment")
    assert str(item) == "100.50 on 2024-01-15 10:30:00+00:00 - Loan payment"


def test_cash_flow_item_string_representation_without_description():
    item = CashFlowItem(Money("100.50"), datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc))
    assert str(item) == "100.50 on 2024-01-15 10:30:00+00:00"


def test_cash_flow_item_repr_representation():
    item = CashFlowItem(Money("100.50"), datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc), "Payment", "loan")
    expected = (
        "CashFlowItem(amount=Money(100.50), datetime=datetime.datetime(2024, 1, 15, 10, 30,"
        " tzinfo=datetime.timezone.utc), description='Payment', category='loan')"
    )
    assert repr(item) == expected


# CashFlow Creation Tests
def test_cash_flow_creation_empty():
    cf = CashFlow()
    assert cf.is_empty()


def test_cash_flow_creation_with_items():
    items = [
        CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
        CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
    ]
    cf = CashFlow(items)
    assert len(cf) == 2


def test_cash_flow_empty_class_method():
    cf = CashFlow.empty()
    assert cf.is_empty()


# CashFlow Item Management Tests
def test_cash_flow_add_item():
    cf = CashFlow.empty()
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    cf.add_item(item)
    assert len(cf) == 1


def test_cash_flow_add_by_components():
    cf = CashFlow.empty()
    cf.add(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), "Payment", "loan")
    assert len(cf) == 1
    assert cf[0].amount == Money("100.00")
    assert cf[0].description == "Payment"


def test_cash_flow_items_returns_copy():
    item = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    cf = CashFlow([item])
    items = cf.items()
    items.clear()  # Modify the returned list
    assert len(cf) == 1  # Original should be unchanged


def test_cash_flow_iteration():
    items = [
        CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
        CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
    ]
    cf = CashFlow(items)
    iterated_entries = list(cf)
    assert iterated_entries == items


def test_cash_flow_indexing():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    item2 = CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc))
    cf = CashFlow([item1, item2])
    assert cf[0] == item1
    assert cf[1] == item2


# CashFlow Sorting Tests
def test_cash_flow_sorted_items_by_datetime():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc))  # Latest
    item2 = CashFlowItem(Money("-50.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))  # Earliest
    item3 = CashFlowItem(Money("25.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc))  # Middle

    cf = CashFlow([item1, item2, item3])
    sorted_items = cf.sorted_items()

    assert sorted_items[0] == item2  # 2024-01-15
    assert sorted_items[1] == item3  # 2024-02-15
    assert sorted_items[2] == item1  # 2024-03-15


# CashFlow Calculation Tests
def test_cash_flow_net_present_value_empty():
    cf = CashFlow.empty()
    assert cf.net_present_value() == Money.zero()


def test_cash_flow_net_present_value_mixed_flows():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert cf.net_present_value() == Money("75.00")


def test_cash_flow_total_inflows():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert cf.total_inflows() == Money("125.00")


def test_cash_flow_total_outflows():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert cf.total_outflows() == Money("75.00")


def test_cash_flow_total_inflows_empty():
    cf = CashFlow.empty()
    assert cf.total_inflows() == Money.zero()


def test_cash_flow_total_outflows_empty():
    cf = CashFlow.empty()
    assert cf.total_outflows() == Money.zero()


# CashFlow Filtering Tests
def test_cash_flow_filter_by_category():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="interest"),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc), category="principal"),
            CashFlowItem(Money("25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc), category="interest"),
        ]
    )

    interest_cf = cf.filter_by_category("interest")
    assert len(interest_cf) == 2
    assert interest_cf.net_present_value() == Money("125.00")


def test_cash_flow_filter_by_category_no_matches():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="interest"),
        ]
    )

    principal_cf = cf.filter_by_category("principal")
    assert principal_cf.is_empty()


def test_cash_flow_filter_by_datetime_range():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    filtered_cf = cf.filter_by_datetime_range(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), datetime(2024, 2, 28, 23, 59, tzinfo=timezone.utc)
    )
    assert len(filtered_cf) == 2
    assert filtered_cf.net_present_value() == Money("50.00")


def test_cash_flow_filter_by_datetime_range_inclusive():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    # Test that boundaries are inclusive
    filtered_cf = cf.filter_by_datetime_range(
        datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)
    )
    assert len(filtered_cf) == 2


# CashFlow DateTime Range Tests
def test_cash_flow_earliest_datetime():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert cf.earliest_datetime() == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_cash_flow_latest_datetime():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert cf.latest_datetime() == datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)


def test_cash_flow_earliest_datetime_empty():
    cf = CashFlow.empty()
    assert cf.earliest_datetime() is None


def test_cash_flow_latest_datetime_empty():
    cf = CashFlow.empty()
    assert cf.latest_datetime() is None


# CashFlow Equality Tests
def test_cash_flow_equality_same_items():
    items = [
        CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
        CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
    ]
    cf1 = CashFlow(items)
    cf2 = CashFlow(items)
    assert cf1 == cf2


def test_cash_flow_equality_different_items():
    cf1 = CashFlow([CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))])
    cf2 = CashFlow([CashFlowItem(Money("200.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))])
    assert cf1 != cf2


def test_cash_flow_equality_different_order():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    item2 = CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc))

    cf1 = CashFlow([item1, item2])
    cf2 = CashFlow([item2, item1])
    assert cf1 != cf2  # Order matters for equality


def test_cash_flow_equality_with_non_cash_flow():
    cf = CashFlow.empty()
    assert cf != "not a cash flow"


# CashFlow String Representation Tests
def test_cash_flow_string_representation_empty():
    cf = CashFlow.empty()
    assert str(cf) == "CashFlow(empty)"


def test_cash_flow_string_representation_with_items():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )
    assert str(cf) == "CashFlow(2 items, net: 50.00)"


def test_cash_flow_repr_representation():
    items = [CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))]
    cf = CashFlow(items)
    assert repr(cf) == f"CashFlow(items={items!r})"


# Edge Case Tests
def test_cash_flow_item_negative_zero():
    item = CashFlowItem(Money("-0.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.is_zero()


def test_cash_flow_high_precision_amounts():
    item = CashFlowItem(Money("100.123456789"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.amount.raw_amount == Decimal("100.123456789")
    assert item.amount.real_amount == Decimal("100.12")


def test_cash_flow_very_large_amounts():
    item = CashFlowItem(Money("999999999.99"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert item.amount.real_amount == Decimal("999999999.99")


def test_cash_flow_many_items_performance():
    items = [CashFlowItem(Money(f"{i}.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)) for i in range(1000)]
    cf = CashFlow(items)
    assert len(cf) == 1000
    # Sum should be 0+1+2+...+999 = 499500
    assert cf.net_present_value() == Money("499500.00")


# DateTime Precision Tests
def test_cash_flow_item_datetime_precision():
    dt = datetime(2024, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
    item = CashFlowItem(Money("100.00"), dt)
    assert item.datetime == dt


def test_cash_flow_sorted_items_by_precise_datetime():
    item1 = CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc))
    item2 = CashFlowItem(Money("-50.00"), datetime(2024, 1, 15, 10, 30, 44, tzinfo=timezone.utc))  # 1 second earlier
    item3 = CashFlowItem(Money("25.00"), datetime(2024, 1, 15, 10, 30, 46, tzinfo=timezone.utc))  # 1 second later

    cf = CashFlow([item1, item2, item3])
    sorted_items = cf.sorted_items()

    assert sorted_items[0] == item2  # 10:30:44
    assert sorted_items[1] == item1  # 10:30:45
    assert sorted_items[2] == item3  # 10:30:46


# CashFlowQuery Tests
def test_cash_flow_query_property():
    cf = CashFlow([CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))])
    query = cf.query
    assert isinstance(query, CashFlowQuery)


def test_cash_flow_query_filter_by_category():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="loan"),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc), category="fee"),
        ]
    )

    loan_items = cf.query.filter_by(category="loan").all()
    assert len(loan_items) == 1
    assert loan_items[0].category == "loan"


def test_cash_flow_query_filter_by_amount_gt():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    large_items = cf.query.filter_by(amount__gt=Money("75.00")).all()
    assert len(large_items) == 2
    assert all(item.amount > Money("75.00") for item in large_items)


def test_cash_flow_query_filter_by_datetime_range():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    filtered_items = cf.query.filter_by(
        datetime__gte=datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc),
        datetime__lte=datetime(2024, 2, 28, 23, 59, tzinfo=timezone.utc),
    ).all()
    assert len(filtered_items) == 1
    assert filtered_items[0].datetime.month == 2


def test_cash_flow_query_filter_inflows():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    inflows = cf.query.filter_by(is_inflow=True).all()
    assert len(inflows) == 2
    assert all(item.is_inflow() for item in inflows)


def test_cash_flow_query_filter_outflows():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    outflows = cf.query.filter_by(is_inflow=False).all()
    assert len(outflows) == 2
    assert all(item.is_outflow() for item in outflows)


def test_cash_flow_query_chained_filters():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="loan"),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc), category="loan"),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc), category="fee"),
            CashFlowItem(Money("-25.00"), datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc), category="loan"),
        ]
    )

    # Chain: loan category AND amount > 75
    result = cf.query.filter_by(category="loan").filter_by(amount__gt=Money("75.00")).all()
    assert len(result) == 1
    assert result[0].amount == Money("100.00")


def test_cash_flow_query_order_by_single_field():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    ordered_items = cf.query.order_by("datetime").all()
    assert ordered_items[0].datetime.month == 1
    assert ordered_items[1].datetime.month == 2
    assert ordered_items[2].datetime.month == 3


def test_cash_flow_query_order_by_descending():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    ordered_items = cf.query.order_by("-amount").all()
    assert ordered_items[0].amount == Money("200.00")
    assert ordered_items[1].amount == Money("100.00")
    assert ordered_items[2].amount == Money("50.00")


def test_cash_flow_query_limit():
    cf = CashFlow(
        [CashFlowItem(Money(f"{i}.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)) for i in range(10)]
    )

    limited_items = cf.query.limit(3).all()
    assert len(limited_items) == 3


def test_cash_flow_query_offset():
    cf = CashFlow(
        [CashFlowItem(Money(f"{i}.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)) for i in range(10)]
    )

    offset_items = cf.query.offset(5).all()
    assert len(offset_items) == 5
    assert offset_items[0].amount == Money("5.00")


def test_cash_flow_query_first():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    first_item = cf.query.first()
    assert first_item.amount == Money("100.00")


def test_cash_flow_query_first_empty():
    cf = CashFlow.empty()
    assert cf.query.first() is None


def test_cash_flow_query_last():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    last_item = cf.query.last()
    assert last_item.amount == Money("50.00")


def test_cash_flow_query_last_empty():
    cf = CashFlow.empty()
    assert cf.query.last() is None


def test_cash_flow_query_count():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    assert cf.query.count() == 2
    assert cf.query.filter_by(amount__gt=Money("75.00")).count() == 1


def test_cash_flow_query_sum_amounts():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("-50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("25.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    total = cf.query.sum_amounts()
    assert total == Money("75.00")

    inflow_total = cf.query.filter_by(is_inflow=True).sum_amounts()
    assert inflow_total == Money("125.00")


def test_cash_flow_query_to_cash_flow():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), category="loan"),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc), category="fee"),
        ]
    )

    loan_cf = cf.query.filter_by(category="loan").to_cash_flow()
    assert isinstance(loan_cf, CashFlow)
    assert len(loan_cf) == 1
    assert loan_cf[0].category == "loan"


def test_cash_flow_query_iteration():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    query_items = list(cf.query)
    assert len(query_items) == 2
    assert query_items[0].amount == Money("100.00")


def test_cash_flow_query_indexing():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    query = cf.query
    assert query[0].amount == Money("100.00")
    assert query[1].amount == Money("50.00")


def test_cash_flow_query_len():
    cf = CashFlow(
        [
            CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("50.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    assert len(cf.query) == 2
    assert len(cf.query.filter_by(amount__gt=Money("75.00"))) == 1


def test_cash_flow_query_invalid_filter_argument():
    cf = CashFlow([CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))])

    with pytest.raises(ValueError, match="Unknown filter argument: invalid_field"):
        cf.query.filter_by(invalid_field="test").all()


def test_cash_flow_query_invalid_order_field():
    cf = CashFlow([CashFlowItem(Money("100.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc))])

    with pytest.raises(ValueError, match="Unknown field: invalid_field"):
        cf.query.order_by("invalid_field").all()


@pytest.mark.parametrize(
    "filter_kwargs,expected_count",
    [
        ({"amount__gte": Money("50.00")}, 3),
        ({"amount__lt": Money("100.00")}, 1),
        ({"amount__lte": Money("100.00")}, 2),
        ({"datetime__lt": datetime(2024, 2, 1, tzinfo=timezone.utc)}, 1),
        ({"datetime__gte": datetime(2024, 2, 1, tzinfo=timezone.utc)}, 2),
    ],
)
def test_cash_flow_query_comparison_operators(filter_kwargs, expected_count):
    cf = CashFlow(
        [
            CashFlowItem(Money("50.00"), datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("100.00"), datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc)),
            CashFlowItem(Money("200.00"), datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)),
        ]
    )

    filtered_items = cf.query.filter_by(**filter_kwargs).all()
    assert len(filtered_items) == expected_count
