"""Diagnostic: does the residual 1-cent gap come from C# using `double`?

Read-only investigation. Not a pytest test. Run directly:

    python -m tests.loan.external_validation._investigate_csharp_precision

For every fixture case in ``tests/loan/external_validation/fixtures/2026-*.json``
we recompute PMT five different ways and compare against the external system's
`payment` field (already rounded to cents):

  Model A  Full Decimal (current money_warp behaviour).
  Model B  Fractional exponent via ``math.pow`` (double); rest in Decimal.
  Model C  Full double -- PMT computed end-to-end with Python float.
  Model D  Double for fractional exponent AND the ``(1+d)**n`` factors;
           sum of reciprocals done in double, final division in Decimal.
  Model E  Decimal at 15-digit context (decimal-shaped analogue of double).
  Model F  Full-precision effective annual from the monthly rate string
           (``(1+monthly)**12 - 1`` with no 6-digit quantization). Tests whether
           the drift is really caused by ``precision=6`` truncation at the EA
           step, not by anything downstream.
  Model G  Baseline, but counted as a match if EITHER principal=P,
           principal=P+0.005, or principal=P-0.005 reproduces the external PMT.
           Tests the "external grossed up an un-rounded financed_amount, then
           rounded financed_amount to cents for display" hypothesis.
  Model H  Self-consistent schedule. For each candidate PMT (analytic rounded
           to cents, and ±1 cent around it), simulate the schedule with
           cent-rounded interest per period and equal payments throughout.
           Pick the PMT (rounded to cents) that yields the smallest absolute
           final-balance residual. Tests the "external tunes PMT so its
           cent-rounded schedule naturally closes to zero, rather than letting
           the last payment absorb the residual" hypothesis.

We then report, per (model, rounding) pair:
  - how many cases match exactly,
  - how many are within 0.005,
  - how many are within 0.01,
  - how many are outside 0.01,
  - the worst absolute error.

Finally we show the worst offenders under Model A so we can eyeball which
alternative model tracks the external.

Hypotheses tested:

  1. C# has no decimal-native fractional exponentiation; ``Math.Pow`` works on
     ``double``. If the external uses C#, its ``daily_rate`` (and potentially
     its ``(1+d)**n`` factors) have only ~15-16 significant digits instead of
     the ~28 that Python's Decimal carries. Models B, C, D, E probe this.
     REFUTED -- all decimal/double variants produce identical cent-rounded
     PMTs to Model A.

  2. The external's published ``financed_amount`` is its grossup result
     cent-rounded for display; its internal PMT came from the un-rounded
     value. Model G probes this.
     PARTIAL -- accounts for ~25% of mismatches.

  3. The external tunes PMT so that a schedule built with cent-rounded
     interest per period closes to zero with equal payments throughout,
     rather than letting the last payment absorb the residual. Model H
     probes this.
     PARTIAL -- fixes some cases but introduces others; net regression vs
     baseline. Combined with Model G the union covers ~65% of mismatches.
"""

import json
import math
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Callable, Dict, List, Tuple

FIXTURES_DIR = Path(__file__).parent / "fixtures"

CENT = Decimal("0.01")


def _load_cases() -> List[dict]:
    """Load every fixture case into a flat list of dicts.

    Uses the same glob as the parametrised pytest suite so the sample is
    identical to what the tolerance-asserting test currently exercises.
    """
    cases: List[dict] = []
    for fixture in sorted(FIXTURES_DIR.glob("2026-*.json")):
        with open(fixture) as f:
            data = json.load(f)
        for entry in data:
            cases.append(entry)
    return cases


def _return_days(disbursement: date, dues: List[date]) -> List[int]:
    return [(d - disbursement).days for d in dues]


def _quantize(value: Decimal, rounding: str) -> Decimal:
    return value.quantize(CENT, rounding=rounding)


def _pmt_model_a(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Full Decimal (current behaviour)."""
    daily = (Decimal(1) + ea) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    denom = sum(
        (Decimal(1) / (Decimal(1) + daily) ** Decimal(n) for n in ns),
        Decimal(0),
    )
    return principal / denom


def _pmt_model_b(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Fractional exponent via double; rest in Decimal."""
    daily_f = math.pow(1.0 + float(ea), 1.0 / 365.0) - 1.0
    daily = Decimal(repr(daily_f))
    denom = sum(
        (Decimal(1) / (Decimal(1) + daily) ** Decimal(n) for n in ns),
        Decimal(0),
    )
    return principal / denom


def _pmt_model_c(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Full double."""
    p_f = float(principal)
    ea_f = float(ea)
    daily_f = math.pow(1.0 + ea_f, 1.0 / 365.0) - 1.0
    denom_f = sum(1.0 / (1.0 + daily_f) ** n for n in ns)
    return Decimal(repr(p_f / denom_f))


def _pmt_model_d(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Double for fractional exponent AND for (1+d)**n factors; final division in Decimal."""
    ea_f = float(ea)
    daily_f = math.pow(1.0 + ea_f, 1.0 / 365.0) - 1.0
    denom_f = sum(math.pow(1.0 + daily_f, -n) for n in ns)
    denom = Decimal(repr(denom_f))
    return principal / denom


def _pmt_model_e(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Decimal at 15-digit context (decimal-shaped analogue of double)."""
    with localcontext() as ctx:
        ctx.prec = 15
        daily = (Decimal(1) + ea) ** (Decimal(1) / Decimal(365)) - Decimal(1)
        denom = sum(
            (Decimal(1) / (Decimal(1) + daily) ** Decimal(n) for n in ns),
            Decimal(0),
        )
        pmt = principal / denom
    return +pmt


def _simulate_final_balance(
    principal: Decimal,
    daily: Decimal,
    ns: List[int],
    pmt: Decimal,
    interest_rounding: str = ROUND_HALF_UP,
) -> Decimal:
    """Simulate a Price-style schedule with cent-rounded interest per period.

    All payments are equal to ``pmt`` (including the last). Returns the final
    balance residual; a self-consistent PMT produces a residual near zero.
    """
    balance = principal
    prev_n = 0
    for n in ns:
        days = n - prev_n
        factor = (Decimal(1) + daily) ** Decimal(days)
        interest = (balance * (factor - Decimal(1))).quantize(CENT, rounding=interest_rounding)
        principal_payment = pmt - interest
        balance = balance - principal_payment
        prev_n = n
    return balance


def _pmt_model_h(principal: Decimal, ea: Decimal, ns: List[int]) -> Decimal:
    """Self-consistent schedule: pick the cent-rounded PMT whose schedule self-closes."""
    daily = (Decimal(1) + ea) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    analytic = _pmt_model_a(principal, ea, ns)
    base = analytic.quantize(CENT, rounding=ROUND_HALF_UP)

    candidates = [base - CENT, base, base + CENT]
    best = min(
        candidates,
        key=lambda pmt: abs(_simulate_final_balance(principal, daily, ns, pmt)),
    )
    return best


def _parse_monthly_rate(rate_str: str) -> Decimal:
    """Parse fixture's ``rate`` field (always a monthly string like '1.0% m')."""
    value_str, _, _ = rate_str.strip().partition(" ")
    if value_str.endswith("%"):
        return Decimal(value_str[:-1]) / Decimal(100)
    return Decimal(value_str)


def _pmt_model_f(principal: Decimal, ea: Decimal, ns: List[int], monthly: Decimal) -> Decimal:
    """Full-precision effective annual (no 6-digit quantization)."""
    ea_full = (Decimal(1) + monthly) ** Decimal(12) - Decimal(1)
    daily = (Decimal(1) + ea_full) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    denom = sum(
        (Decimal(1) / (Decimal(1) + daily) ** Decimal(n) for n in ns),
        Decimal(0),
    )
    return principal / denom


MODELS: Dict[str, Callable[..., Decimal]] = {
    "A_decimal_full": _pmt_model_a,
    "B_double_frac_exp": _pmt_model_b,
    "C_double_full": _pmt_model_c,
    "D_double_frac_and_factors": _pmt_model_d,
    "E_decimal_prec15": _pmt_model_e,
    "F_ea_no_quantize": _pmt_model_f,
    "H_self_consistent": _pmt_model_h,
}

ROUNDINGS: Dict[str, str] = {
    "HALF_UP": ROUND_HALF_UP,
    "HALF_EVEN": ROUND_HALF_EVEN,
}


def _compute_pmts(case: dict) -> Dict[Tuple[str, str], Decimal]:
    """Return PMT per (model, rounding) pair for one fixture case."""
    principal = Decimal(str(case["financed_amount"]))
    ea = Decimal(str(case["annual_interest_rate"]))
    monthly = _parse_monthly_rate(case["rate"])
    disbursement = datetime.strptime(case["disbursement_date"], "%Y-%m-%d").date()
    dues = [datetime.strptime(d, "%Y-%m-%d").date() for d in case["due_dates"]]
    ns = _return_days(disbursement, dues)

    out: Dict[Tuple[str, str], Decimal] = {}
    for model_name, fn in MODELS.items():
        if model_name == "F_ea_no_quantize":
            raw = fn(principal, ea, ns, monthly)
        else:
            raw = fn(principal, ea, ns)
        for round_name, rounding in ROUNDINGS.items():
            out[(model_name, round_name)] = _quantize(raw, rounding)

    half_cent = Decimal("0.005")
    for shift_name, shifted_p in (
        ("G_grossup_minus", principal - half_cent),
        ("G_grossup_plus", principal + half_cent),
    ):
        raw = _pmt_model_a(shifted_p, ea, ns)
        for round_name, rounding in ROUNDINGS.items():
            out[(shift_name, round_name)] = _quantize(raw, rounding)
    return out


def _format_matrix(
    stats: Dict[Tuple[str, str], Dict[str, object]],
    total: int,
) -> str:
    header = (
        f"{'model':<28} {'rounding':<10} "
        f"{'exact':>8} {'<=0.005':>8} {'<=0.01':>8} {'>0.01':>8} {'max_err':>10}"
    )
    lines = [header, "-" * len(header)]
    all_names = list(MODELS.keys()) + [
        "G_grossup_minus",
        "G_grossup_plus",
        "G_grossup_either",
        "AHG_union",
    ]
    for model_name in all_names:
        for round_name in ROUNDINGS:
            s = stats[(model_name, round_name)]
            lines.append(
                f"{model_name:<28} {round_name:<10} "
                f"{s['exact']:>8} {s['within_half']:>8} {s['within_cent']:>8} "
                f"{s['over_cent']:>8} {s['max_err']:>10.4f}"
            )
    lines.append("-" * len(header))
    lines.append(f"total cases: {total}")
    return "\n".join(lines)


def _run() -> None:
    cases = _load_cases()
    total = len(cases)

    all_model_names = list(MODELS.keys()) + [
        "G_grossup_minus",
        "G_grossup_plus",
        "G_grossup_either",
        "AHG_union",
    ]
    stats: Dict[Tuple[str, str], Dict[str, object]] = {
        (model_name, round_name): {
            "exact": 0,
            "within_half": 0,
            "within_cent": 0,
            "over_cent": 0,
            "max_err": 0.0,
        }
        for model_name in all_model_names
        for round_name in ROUNDINGS
    }

    per_case_errors: List[Tuple[float, int, dict, Dict[Tuple[str, str], Decimal]]] = []

    for idx, case in enumerate(cases):
        expected = Decimal(str(case["payment"]))
        pmts = _compute_pmts(case)

        for round_name in ROUNDINGS:
            minus = pmts[("G_grossup_minus", round_name)]
            plus = pmts[("G_grossup_plus", round_name)]
            baseline = pmts[("A_decimal_full", round_name)]
            self_consistent = pmts[("H_self_consistent", round_name)]
            either = min(
                (minus, plus, baseline),
                key=lambda v: abs(v - expected),
            )
            pmts[("G_grossup_either", round_name)] = either
            pmts[("AHG_union", round_name)] = min(
                (baseline, minus, plus, self_consistent),
                key=lambda v: abs(v - expected),
            )

        for key, pmt in pmts.items():
            err = abs(pmt - expected)
            err_f = float(err)
            s = stats[key]
            if err == 0:
                s["exact"] += 1
                s["within_half"] += 1
                s["within_cent"] += 1
            elif err <= Decimal("0.005"):
                s["within_half"] += 1
                s["within_cent"] += 1
            elif err <= Decimal("0.01"):
                s["within_cent"] += 1
            else:
                s["over_cent"] += 1
            if err_f > s["max_err"]:
                s["max_err"] = err_f

        baseline_err = float(abs(pmts[("A_decimal_full", "HALF_UP")] - expected))
        per_case_errors.append((baseline_err, idx, case, pmts))

    print("=" * 80)
    print("Match matrix vs external `payment` (already rounded to cents)")
    print("=" * 80)
    print(_format_matrix(stats, total))
    print()

    per_case_errors.sort(reverse=True)
    print("=" * 80)
    print("Worst offenders under Model A (HALF_UP)")
    print("=" * 80)
    top_n = 15
    header = (
        f"{'idx':>6} {'ea':>10} {'P':>12} {'N':>4} {'expected':>10} "
        f"{'A_HU':>10} {'H_HU':>10} {'G_either':>10} {'F_HU':>10}"
    )
    print(header)
    print("-" * len(header))
    for err, idx, case, pmts in per_case_errors[:top_n]:
        ea = float(case["annual_interest_rate"])
        p = float(case["financed_amount"])
        n = len(case["due_dates"])
        expected = float(case["payment"])
        print(
            f"{idx:>6} {ea:>10.6f} {p:>12.2f} {n:>4} {expected:>10.2f} "
            f"{float(pmts[('A_decimal_full', 'HALF_UP')]):>10.2f} "
            f"{float(pmts[('H_self_consistent', 'HALF_UP')]):>10.2f} "
            f"{float(pmts[('G_grossup_either', 'HALF_UP')]):>10.2f} "
            f"{float(pmts[('F_ea_no_quantize', 'HALF_UP')]):>10.2f}"
        )


def _simulate_our_schedule(
    principal: Decimal,
    ea: Decimal,
    disbursement: date,
    dues: List[date],
    interest_rounding: str = ROUND_HALF_UP,
) -> List[dict]:
    """Replay ``PriceScheduler.generate_schedule`` without going through the full Loan API.

    Mirrors the real logic in ``money_warp/scheduler/price_scheduler.py`` exactly:
    analytic PMT rounded to cents, per-period interest rounded to cents, last
    payment absorbs the residual so the final balance is zero.
    """
    daily = (Decimal(1) + ea) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    ns = [(d - disbursement).days for d in dues]

    denom = sum(
        (Decimal(1) / (Decimal(1) + daily) ** Decimal(n) for n in ns),
        Decimal(0),
    )
    pmt = (principal / denom).quantize(CENT, rounding=ROUND_HALF_UP)

    entries: List[dict] = []
    balance = principal
    for i, due in enumerate(dues):
        prev = disbursement if i == 0 else dues[i - 1]
        days = (due - prev).days
        factor = (Decimal(1) + daily) ** Decimal(days)
        interest = (balance * (factor - Decimal(1))).quantize(CENT, rounding=interest_rounding)

        is_last = i == len(dues) - 1
        if is_last:
            principal_pay = balance
            total_pay = principal_pay + interest
        else:
            total_pay = pmt
            principal_pay = pmt - interest

        beginning = balance
        balance = beginning - principal_pay
        entries.append(
            {
                "period": i + 1,
                "running_day": days,
                "interest": interest,
                "principal": principal_pay,
                "balance": max(Decimal(0), balance),
                "payment": total_pay,
            }
        )
    return entries


def _analyze_schedule_drift(cases: List[dict]) -> None:
    """Locate the earliest period where our schedule diverges from the fixture.

    Produces three views:

      1. Across all cases, count where the FIRST divergence occurs:
         - running_day (day-count)
         - interest   (accrual)
         - principal or balance with matching interest (pure PMT propagation)
         - none       (fully aligned)

      2. Split the above by whether the case's PMT matched baseline Model A
         exactly, so we can see whether PMT-mismatched cases always have
         period-level drift or sometimes do not.

      3. Sample a handful of PMT-mismatched cases and pretty-print the first
         divergence side-by-side (ours vs theirs).
    """
    buckets = {
        "pmt_match": {"aligned": 0, "running_day": 0, "interest": 0, "propagation": 0},
        "pmt_mismatch": {"aligned": 0, "running_day": 0, "interest": 0, "propagation": 0},
    }
    first_period_counter: Dict[Tuple[str, int], int] = {}
    interest_drift_cases: List[Tuple[int, dict, List[dict], int, bool]] = []

    for idx, case in enumerate(cases):
        principal = Decimal(str(case["financed_amount"]))
        ea = Decimal(str(case["annual_interest_rate"]))
        disbursement = datetime.strptime(case["disbursement_date"], "%Y-%m-%d").date()
        dues = [datetime.strptime(d, "%Y-%m-%d").date() for d in case["due_dates"]]
        ours = _simulate_our_schedule(principal, ea, disbursement, dues)
        theirs = case["schedule"]

        expected_pmt = Decimal(str(case["payment"]))
        our_pmt = ours[0]["payment"]
        pmt_matches = (our_pmt == expected_pmt)
        bucket_name = "pmt_match" if pmt_matches else "pmt_mismatch"
        bucket = buckets[bucket_name]

        first_kind = "aligned"
        first_period_num = 0
        for ours_entry, theirs_entry in zip(ours, theirs):
            their_days = int(theirs_entry["running_day"])
            their_interest = Decimal(str(theirs_entry["interest"]))
            their_principal = Decimal(str(theirs_entry["principal"]))
            their_balance = Decimal(str(theirs_entry["balance"]))

            if ours_entry["running_day"] != their_days:
                first_kind = "running_day"
                first_period_num = ours_entry["period"]
                break
            if ours_entry["interest"] != their_interest:
                first_kind = "interest"
                first_period_num = ours_entry["period"]
                break
            if (
                ours_entry["principal"] != their_principal
                or ours_entry["balance"] != their_balance
            ):
                first_kind = "propagation"
                first_period_num = ours_entry["period"]
                break

        bucket[first_kind] += 1
        if first_kind != "aligned":
            first_period_counter[(first_kind, first_period_num)] = (
                first_period_counter.get((first_kind, first_period_num), 0) + 1
            )
        if first_kind == "interest":
            interest_drift_cases.append((idx, case, ours, first_period_num, pmt_matches))

    print()
    print("=" * 80)
    print("Per-period schedule drift (ours vs fixture `schedule`)")
    print("=" * 80)
    header = f"{'group':<16} {'aligned':>10} {'running_day':>12} {'interest':>10} {'propagation':>12} {'total':>8}"
    print(header)
    print("-" * len(header))
    for group, b in buckets.items():
        total_group = sum(b.values())
        print(
            f"{group:<16} {b['aligned']:>10} {b['running_day']:>12} "
            f"{b['interest']:>10} {b['propagation']:>12} {total_group:>8}"
        )
    print()

    if first_period_counter:
        print("First divergence by (kind, period):")
        for (kind, period), count in sorted(
            first_period_counter.items(), key=lambda kv: (kv[0][0], kv[0][1])
        ):
            print(f"  {kind:<12} period {period:>3}: {count} cases")
        print()

    pmt_mismatch_interest = sum(1 for _, _, _, _, m in interest_drift_cases if not m)
    pmt_match_interest = sum(1 for _, _, _, _, m in interest_drift_cases if m)
    print(
        f"Interest-drift cases: {len(interest_drift_cases)} total "
        f"({pmt_mismatch_interest} with PMT mismatch, {pmt_match_interest} with PMT match)"
    )
    print()

    pmt_mismatch_interest_drift = [c for c in interest_drift_cases if not c[4]]
    if pmt_mismatch_interest_drift:
        print(
            f"All {len(pmt_mismatch_interest_drift)} "
            "PMT-mismatch cases with period-1+ interest drift"
        )
        print("-" * 80)
        for idx, case, ours, period_num, _ in pmt_mismatch_interest_drift:
            theirs_entry = case["schedule"][period_num - 1]
            ours_entry = ours[period_num - 1]
            daily_from_fixture_interest = (
                Decimal(str(theirs_entry["interest"]))
                / Decimal(
                    str(case["schedule"][period_num - 2]["balance"])
                    if period_num > 1
                    else case["financed_amount"]
                )
            )
            print(
                f"idx={idx} N={len(case['due_dates'])} "
                f"ea={case['annual_interest_rate']} "
                f"P={case['financed_amount']:.2f} "
                f"expected_pmt={case['payment']} our_pmt={float(ours[0]['payment']):.2f}"
            )
            print(
                f"  first drift at period {period_num} (days={theirs_entry['running_day']})"
            )
            print(
                f"    fixture: interest={theirs_entry['interest']:>10}  "
                f"implied (interest/beginning)={float(daily_from_fixture_interest):>10.6f}"
            )
            print(
                f"    ours:    interest={float(ours_entry['interest']):>10.2f}  "
                f"difference={float(ours_entry['interest']) - float(theirs_entry['interest']):+.2f}"
            )
            print()

    later_interest_drift = [c for c in interest_drift_cases if c[4]]
    if later_interest_drift:
        pmt_match_periods: Dict[int, int] = {}
        for _, _, _, p, _ in later_interest_drift:
            pmt_match_periods[p] = pmt_match_periods.get(p, 0) + 1
        print(
            f"PMT-match cases with later-period interest drift: "
            f"{len(later_interest_drift)} cases"
        )
        print("  First-drift period distribution (top 10):")
        for period, count in sorted(
            pmt_match_periods.items(), key=lambda kv: -kv[1]
        )[:10]:
            print(f"    period {period:>3}: {count} cases")
        print()


if __name__ == "__main__":
    _run()
    _analyze_schedule_drift(_load_cases())
