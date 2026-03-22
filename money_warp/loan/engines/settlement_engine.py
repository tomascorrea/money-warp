"""Settlement and installment computation from payment data."""

from datetime import date, datetime
from typing import Dict, List, Optional

from ...money import Money
from ...scheduler import PaymentSchedule
from ...tz import to_datetime
from ..installment import Installment
from ..settlement import Settlement, SettlementAllocation
from .interest_calculator import InterestCalculator
from .payment_ledger import PaymentLedger

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
    # Contractual interest for skipped periods
    # ------------------------------------------------------------------

    @staticmethod
    def _skipped_contractual_interest(
        installments: List[Installment],
        next_due: Optional[date],
        cutoff: date,
    ) -> Money:
        """Sum unpaid contractual interest for installments past *next_due*.

        Returns the total ``expected_interest - interest_paid`` for every
        installment whose due date falls strictly after *next_due* and on
        or before *cutoff*.  These are periods that
        :meth:`InterestCalculator.compute_accrued_interest` cannot reach
        because it only considers one due-date boundary.
        """
        if next_due is None:
            return Money.zero()
        total = Money.zero()
        for inst in installments:
            if inst.due_date > next_due and inst.due_date <= cutoff:
                owed = inst.expected_interest - inst.interest_paid
                if owed.is_positive():
                    total = total + owed
        return total

    # ------------------------------------------------------------------
    # Per-installment payment allocation
    # ------------------------------------------------------------------

    @staticmethod
    def allocate_payment_per_installment(
        amount: Money,
        installments: List[Installment],
        ending_balance: Money,
        fine_cap: Money,
        interest_cap: Money,
        mora_cap: Money,
    ) -> tuple:
        """Allocate a payment across installments in priority order.

        Each installment is processed sequentially.  Within each
        installment the priority is fine -> mora -> interest -> principal.
        Installment 1's obligations are fully addressed before
        installment 2 receives anything.

        *fine_cap*, *interest_cap*, and *mora_cap* bound the total
        amount that may be allocated to each category.  During live
        allocation these come from the loan-level accrual (preserving
        the early-payment discount).  During reconstruction they match
        the recorded CashFlowItem totals.

        Any payment remainder after all installment obligations are met
        is attributed to principal (overpayment).

        Returns:
            ``(fine_total, mora_total, interest_total, principal_total,
            allocations)`` where *allocations* is a list of
            :class:`SettlementAllocation`.
        """
        loan_fully_paid = ending_balance <= _COVERAGE_TOLERANCE
        remaining = amount
        fine_remaining = fine_cap
        mora_remaining = mora_cap
        interest_remaining = interest_cap
        fine_total = Money.zero()
        mora_total = Money.zero()
        interest_total = Money.zero()
        principal_total = Money.zero()
        allocations: List[SettlementAllocation] = []

        for inst in installments:
            if not remaining.raw_amount:
                break

            allocation, remaining, fine_remaining, mora_remaining, interest_remaining = inst.allocate_from_payment(
                remaining,
                fine_remaining,
                mora_remaining,
                interest_remaining,
            )

            if allocation.total_allocated.raw_amount <= 0:
                continue

            fine_total = fine_total + allocation.fine_allocated
            mora_total = mora_total + allocation.mora_allocated
            interest_total = interest_total + allocation.interest_allocated
            principal_total = principal_total + allocation.principal_allocated

            if not allocation.total_allocated.is_positive():
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

        if remaining.raw_amount > 0:
            mora_spill = Money(min(remaining.raw_amount, mora_remaining.raw_amount))
            remaining = remaining - mora_spill
            mora_total = mora_total + mora_spill

            interest_spill = Money(min(remaining.raw_amount, interest_remaining.raw_amount))
            remaining = remaining - interest_spill
            interest_total = interest_total + interest_spill

            if remaining.raw_amount > 0:
                principal_total = principal_total + remaining

        return fine_total, mora_total, interest_total, principal_total, allocations

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

        covered = self.covered_due_date_count(snap.beginning_balance, schedule)
        next_due = schedule[covered].due_date if covered < len(schedule) else None
        interest_accrued, _ = self._interest.compute_accrued_interest(
            snap.days_in_period, snap.beginning_balance, next_due, last_pay_date
        )
        skipped_contractual = self._skipped_contractual_interest(installments, next_due, snap.payment_date.date())
        interest_cap = Money(interest_accrued.raw_amount + skipped_contractual.raw_amount)

        allocations = self.build_settlement_allocations(
            installments,
            fine_paid,
            mora_paid,
            interest_paid,
            principal_paid,
            snap.ending_balance,
            interest_cap_override=interest_cap,
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
        interest_cap_override: Optional[Money] = None,
    ) -> List[SettlementAllocation]:
        """Reconstruct per-installment allocations from recorded totals.

        Uses the same :meth:`allocate_payment_per_installment` logic so
        that reconstruction and live allocation are always consistent.
        The recorded totals serve as caps so that fines/interest/mora
        applied by *later* payments don't leak into earlier settlements.

        When *interest_cap_override* is provided it replaces the default
        ``interest_paid`` cap, ensuring the reconstruction uses the same
        effective cap as the live allocation in :meth:`Loan.record_payment`.
        """
        payment_amount = fine_paid + mora_paid + interest_paid + principal_paid
        interest_cap = interest_cap_override if interest_cap_override is not None else interest_paid

        _, _, _, _, allocations = self.allocate_payment_per_installment(
            payment_amount,
            installments,
            ending_balance,
            fine_cap=fine_paid,
            interest_cap=interest_cap,
            mora_cap=mora_paid,
        )
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
