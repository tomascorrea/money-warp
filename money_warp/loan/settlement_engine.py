"""Settlement and installment computation from payment data."""

from datetime import date, datetime
from typing import Dict, List, Optional

from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_datetime
from .installment import Installment
from .interest_calculator import InterestCalculator
from .payment_ledger import PaymentLedger
from .settlement import Settlement, SettlementAllocation

_COVERAGE_TOLERANCE = Money("0.01")


class SettlementEngine:
    """Pure computation of settlements and installments from ledger data.

    Holds no mutable state — all data comes from the PaymentLedger
    (which queries the shared CashFlow) and the original schedule.
    """

    def __init__(self, interest_calc: InterestCalculator) -> None:
        self._interest = interest_calc

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    @staticmethod
    def covered_due_date_count(
        remaining_balance: Money,
        schedule: PaymentSchedule,
    ) -> int:
        """How many due dates are covered given a remaining principal balance.

        Unifies the previously duplicated ``_covered_due_date_count`` and
        ``_covered_count_for_balance`` methods.
        """
        covered = 0
        for entry in schedule:
            if remaining_balance <= entry.ending_balance + _COVERAGE_TOLERANCE:
                covered += 1
            else:
                break
        return covered

    # ------------------------------------------------------------------
    # Settlement construction
    # ------------------------------------------------------------------

    def compute_settlement(
        self,
        entry_index: int,
        allocations_by_number: Dict[int, List[SettlementAllocation]],
        ledger: PaymentLedger,
        schedule: PaymentSchedule,
        fines_applied: Dict[date, Money],
        disbursement_date: datetime,
    ) -> Settlement:
        """Compute a Settlement for the payment event at entry_index.

        Args:
            entry_index: 0-based index into ledger snapshots.
            allocations_by_number: Per-installment allocations from prior settlements.
            ledger: The payment ledger to query.
            schedule: The original payment schedule.
            fines_applied: Fine amounts per due date.
            disbursement_date: Loan disbursement date (fallback for first payment).
        """
        snap = ledger.snapshot(entry_index)
        items = ledger.items_for_settlement(entry_index + 1)

        fine_paid = items["fine"]
        interest_paid = items["interest"]
        mora_paid = items["mora_interest"]
        principal_paid = items["principal"]
        payment_amount = fine_paid + interest_paid + mora_paid + principal_paid

        datetimes = ledger.actual_payment_datetimes()
        last_pay_date = disbursement_date if entry_index == 0 else datetimes[entry_index - 1]

        installments = self.build_installments_snapshot(
            allocations_by_number,
            snap.beginning_balance,
            snap.payment_date,
            schedule,
            fines_applied,
            last_payment_date=last_pay_date,
        )
        allocations = self.build_settlement_allocations(
            installments,
            fine_paid,
            mora_paid,
            interest_paid,
            principal_paid,
            snap.ending_balance,
        )

        return Settlement(
            payment_amount=payment_amount,
            payment_date=snap.payment_date,
            fine_paid=fine_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            principal_paid=principal_paid,
            remaining_balance=snap.ending_balance,
            allocations=allocations,
        )

    def build_settlement_allocations(
        self,
        installments: List[Installment],
        fine_paid: Money,
        mora_paid: Money,
        interest_paid: Money,
        principal_paid: Money,
        ending_balance: Money,
    ) -> List[SettlementAllocation]:
        """Distribute a payment's components across installments."""
        loan_fully_paid = ending_balance <= _COVERAGE_TOLERANCE
        remaining_fine = fine_paid
        remaining_mora = mora_paid
        remaining_interest = interest_paid
        remaining_principal = principal_paid

        allocations: List[SettlementAllocation] = []
        for inst in installments:
            if (
                remaining_fine.is_zero()
                and remaining_mora.is_zero()
                and remaining_interest.is_zero()
                and remaining_principal.is_zero()
            ):
                break

            allocation, remaining_fine, remaining_mora, remaining_interest, remaining_principal = inst.allocate(
                remaining_fine,
                remaining_mora,
                remaining_interest,
                remaining_principal,
            )
            total = (
                allocation.principal_allocated
                + allocation.interest_allocated
                + allocation.mora_allocated
                + allocation.fine_allocated
            )
            if not total.is_positive():
                continue

            if loan_fully_paid and not allocation.is_fully_covered:
                principal_owed = inst.expected_principal - inst.principal_paid
                if allocation.principal_allocated >= (principal_owed - _COVERAGE_TOLERANCE):
                    allocation = SettlementAllocation(
                        installment_number=allocation.installment_number,
                        principal_allocated=allocation.principal_allocated,
                        interest_allocated=allocation.interest_allocated,
                        mora_allocated=allocation.mora_allocated,
                        fine_allocated=allocation.fine_allocated,
                        is_fully_covered=True,
                    )

            allocations.append(allocation)

        return allocations

    def build_installments_snapshot(
        self,
        allocations_by_number: Dict[int, List[SettlementAllocation]],
        principal_balance: Money,
        as_of_date: datetime,
        schedule: PaymentSchedule,
        fines_applied: Dict[date, Money],
        last_payment_date: Optional[datetime] = None,
    ) -> List[Installment]:
        """Build Installment objects from pre-computed allocation data."""
        covered = self.covered_due_date_count(principal_balance, schedule)

        result: List[Installment] = []
        for i, entry in enumerate(schedule):
            installment_num = i + 1
            allocs = allocations_by_number.get(installment_num, [])

            expected_fine = fines_applied.get(entry.due_date, Money.zero())
            prior_mora = Money(sum(a.mora_allocated.raw_amount for a in allocs))

            if i < covered:
                expected_mora = prior_mora
            elif i == covered and entry.due_date < as_of_date.date():
                if last_payment_date is not None:
                    total_days = (as_of_date.date() - last_payment_date.date()).days
                    _, accrued_mora = self._interest.compute_accrued_interest(
                        total_days,
                        principal_balance,
                        entry.due_date,
                        last_payment_date,
                    )
                else:
                    days_overdue = (as_of_date.date() - entry.due_date).days
                    _, accrued_mora = self._interest.compute_accrued_interest(
                        days_overdue,
                        principal_balance,
                        entry.due_date,
                        to_datetime(entry.due_date),
                    )
                expected_mora = prior_mora + accrued_mora
            else:
                expected_mora = Money.zero()

            result.append(Installment.from_schedule_entry(entry, allocs, expected_mora, expected_fine))

        return result

    # ------------------------------------------------------------------
    # Aggregate views
    # ------------------------------------------------------------------

    def all_settlements(
        self,
        ledger: PaymentLedger,
        schedule: PaymentSchedule,
        fines_applied: Dict[date, Money],
        disbursement_date: datetime,
        current_time: datetime,
    ) -> List[Settlement]:
        """All settlements up to *current_time*, reconstructed from the ledger."""
        datetimes = ledger.actual_payment_datetimes()
        allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
        result: List[Settlement] = []
        for i, dt in enumerate(datetimes):
            if dt > current_time:
                break
            settlement = self.compute_settlement(
                i, allocs_by_number, ledger, schedule, fines_applied, disbursement_date
            )
            for a in settlement.allocations:
                allocs_by_number.setdefault(a.installment_number, []).append(a)
            result.append(settlement)
        return result

    def all_installments(
        self,
        settlements: List[Settlement],
        principal_balance: Money,
        as_of_date: datetime,
        schedule: PaymentSchedule,
        fines_applied: Dict[date, Money],
    ) -> List[Installment]:
        """Build the full installment list from accumulated settlement allocations."""
        allocations_by_number: Dict[int, List[SettlementAllocation]] = {}
        for settlement in settlements:
            for allocation in settlement.allocations:
                num = allocation.installment_number
                if num not in allocations_by_number:
                    allocations_by_number[num] = []
                allocations_by_number[num].append(allocation)

        return self.build_installments_snapshot(
            allocations_by_number,
            principal_balance,
            as_of_date,
            schedule,
            fines_applied,
        )
