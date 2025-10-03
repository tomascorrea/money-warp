# Late Payment Fines Implementation Plan

## Overview

This document outlines the implementation plan for adding late payment fine functionality to the `Loan` class in the money-warp project.

## Business Requirements

### Fine Rules
- **Fine Rate**: Configurable parameter (default 2% of missed payment amount)
- **Timing**: Applied immediately when payment becomes late (after grace period)
- **Accumulation**: One-time fine per missed payment (not daily)
- **Grace Period**: Configurable (default 0 days)
- **Balance Impact**: Fines are added to the loan balance
- **Payment Priority**: Fines → Interest → Principal

### Implementation Approach
- **Option A**: Extend current `Loan` class (chosen approach)
- Keep implementation simple and follow existing patterns
- Maintain backward compatibility

## Task Breakdown

### Phase 1: Core Infrastructure (Foundation)

#### Task 1.1: Add new parameters to `Loan.__init__()`
- [x] Add `late_fee_rate` parameter (default 2%)
- [x] Add `grace_period_days` parameter (default 0)
- [x] Add validation for parameters
- [x] Update docstring

**Acceptance Criteria:**
- Parameters have appropriate defaults
- Validation prevents negative values
- Docstring includes examples

#### Task 1.2: Add new state tracking attributes
- [x] Add `fines_applied: Dict[datetime, Money]` instance variable
- [x] Initialize in `__init__()`

**Acceptance Criteria:**
- Dictionary properly initialized as empty
- Type hints are correct

#### Task 1.3: Add new properties
- [x] Add `late_fee_rate` property
- [x] Add `grace_period_days` property
- [x] Add `total_fines` property
- [x] Add `outstanding_fines` property

**Acceptance Criteria:**
- Properties return correct types
- `total_fines` sums all applied fines
- `outstanding_fines` shows unpaid fine amount

### Phase 2: Fine Calculation Logic

#### Task 2.1: Implement `get_expected_payment_amount(due_date)`
- [x] Use scheduler to get expected payment for specific due date
- [x] Handle edge cases (invalid due dates, etc.)

**Acceptance Criteria:**
- Returns correct `Money` object for valid due dates
- Raises appropriate errors for invalid dates
- Works with all scheduler types

#### Task 2.2: Implement `is_payment_late(due_date, as_of_date)`
- [x] Check if payment is late considering grace period
- [x] Handle timezone considerations
- [x] Return boolean result

**Acceptance Criteria:**
- Returns `False` during grace period
- Returns `True` after grace period expires
- Handles edge cases (same day, etc.)

#### Task 2.3: Implement `calculate_late_fines(as_of_date)`
- [x] Iterate through all due dates
- [x] Check for late payments using `is_payment_late()`
- [x] Calculate and apply fines for new late payments
- [x] Return total new fines applied
- [x] Ensure fines are only applied once per due date

**Acceptance Criteria:**
- Fines calculated as percentage of expected payment
- No duplicate fines for same due date
- Returns `Money` object with new fines applied
- Updates `fines_applied` dictionary

### Phase 3: Balance and Payment Integration

#### Task 3.1: Update `current_balance` property
- [x] Include accumulated fines in balance calculation
- [x] Ensure fines are reduced by payments allocated to fines
- [x] Maintain existing balance logic for principal

**Acceptance Criteria:**
- Balance includes unpaid fines
- Balance decreases when fines are paid
- Existing principal logic unchanged

#### Task 3.2: Update `record_payment()` method
- [x] Call `calculate_late_fines()` before processing payment
- [x] Implement payment allocation priority: Fines → Interest → Principal
- [x] Track payments allocated to fines separately
- [x] Update existing interest/principal allocation logic

**Acceptance Criteria:**
- Fines are paid first from any payment
- Remaining amount goes to interest, then principal
- Payment tracking includes fine allocations
- Existing functionality preserved

#### Task 3.3: Update `is_paid_off` property
- [x] Consider outstanding fines when determining if loan is paid off
- [x] Loan is only paid off when principal AND fines are zero

**Acceptance Criteria:**
- Returns `False` if fines are outstanding
- Returns `True` only when both principal and fines are zero

### Phase 4: Cash Flow Integration

#### Task 4.1: Update `get_actual_cash_flow()` method
- [x] Include fine items in cash flow
- [x] Add fine application events as cash flow items
- [x] Add fine payment allocations as separate items

**Acceptance Criteria:**
- Fine applications appear as cash flow items
- Fine payments appear as separate items
- Categories are clearly labeled
- Existing cash flow logic preserved

#### Task 4.2: Consider fine impact on `generate_expected_cash_flow()`
- [x] Decide if expected cash flow should include potential fines
- [x] Document behavior in method docstring

**Acceptance Criteria:**
- Clear decision documented
- Behavior is consistent and logical
- Docstring explains the approach

### Phase 5: Testing

#### Task 5.1: Write fine parameter tests
- [x] Test default values
- [x] Test parameter validation
- [x] Test property access

**Test Files:**
- Add tests to `tests/test_loan.py`

**Test Patterns:**
- Function-based tests (no classes)
- Single assert per test
- Parametrized tests for multiple scenarios

#### Task 5.2: Write fine calculation tests
- [x] Test `get_expected_payment_amount()`
- [x] Test `is_payment_late()` with various scenarios
- [x] Test `calculate_late_fines()` with different cases

**Test Scenarios:**
- Valid and invalid due dates
- Grace period edge cases
- Multiple late payments
- Fine rate variations

#### Task 5.3: Write payment allocation tests
- [x] Test payment allocation priority (Fines → Interest → Principal)
- [x] Test partial payments covering only fines
- [x] Test overpayments that cover all categories

**Test Scenarios:**
- Payment exactly covers fines
- Payment covers fines + partial interest
- Payment covers everything with remainder

#### Task 5.4: Write integration tests
- [x] Test complete late payment scenarios
- [x] Test grace period functionality
- [x] Test balance calculations with fines
- [x] Test cash flow generation with fines

**Test Scenarios:**
- End-to-end late payment workflow
- Multiple payments with fines
- Complex scenarios with multiple late dates

#### Task 5.5: Write edge case tests
- [x] Test multiple late payments
- [x] Test payments made exactly on grace period boundary
- [x] Test very small fine amounts
- [x] Test fine calculations with zero interest rates

**Edge Cases:**
- Boundary conditions
- Extreme values
- Error conditions

### Phase 6: Documentation and Cleanup

#### Task 6.1: Update class docstring
- [x] Document new fine functionality
- [x] Add usage examples with fines

**Documentation Requirements:**
- Clear explanation of fine rules
- Code examples showing usage
- Integration with existing features

#### Task 6.2: Update method docstrings
- [x] Document new parameters and behavior
- [x] Add examples showing fine calculations

**Methods to Update:**
- `__init__()` - new parameters
- `record_payment()` - new allocation logic
- All new methods

#### Task 6.3: Update `__str__` and `__repr__` methods
- [x] Include fine information in string representations
- [x] Show outstanding fines in loan summary

**Display Requirements:**
- Show fine rate and grace period in repr
- Show outstanding fines in str
- Maintain readability

### Phase 7: Validation and Polish

#### Task 7.1: Run full test suite
- [x] Ensure all existing tests still pass
- [x] Verify no regressions in existing functionality

**Validation Steps:**
- Run complete test suite
- Check test coverage
- Verify performance impact

#### Task 7.2: Code review and refinement
- [x] Check for code quality and consistency
- [x] Ensure follows project patterns (no class-based tests, single asserts, etc.)
- [x] Verify error handling is appropriate

**Quality Checks:**
- Follow Python zen principles
- Maintain code consistency
- Proper error handling
- Clear variable names

## Progress Tracking

**Total Tasks**: 22 tasks across 7 phases

**Current Status**: Implementation Complete ✅

**Completion Date**: October 2, 2025

**Implementation Summary**: All 7 phases completed successfully with 22/22 tasks finished

## Dependencies

- Tasks must be completed in phase order
- Tasks within each phase can be done in parallel where logical
- Phase 5 (Testing) should run in parallel with implementation phases
- Phase 6 (Documentation) can start after Phase 3 is complete

## Risk Mitigation

### Potential Risks:
1. **Breaking Changes**: Ensure backward compatibility
2. **Performance Impact**: Monitor balance calculation performance
3. **Complex Edge Cases**: Thorough testing of boundary conditions

### Mitigation Strategies:
1. Extensive testing of existing functionality
2. Performance benchmarking
3. Comprehensive edge case testing

## Success Criteria

- [x] All existing tests continue to pass (401/401 tests passing)
- [x] New functionality works as specified (27 new tests added)
- [x] Code follows project patterns and quality standards
- [x] Documentation is complete and clear
- [x] Performance impact is minimal

---

**Document Version**: 2.0  
**Last Updated**: October 2, 2025  
**Status**: Implementation Complete ✅
