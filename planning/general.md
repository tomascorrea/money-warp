# MoneyWarp - Current Active Tasks

## Current Status

**Latest Achievement:** ✅ **PriceScheduler Implementation Complete!**

Successfully implemented and validated the PriceScheduler against the reference implementation from [cartaorobbin/loan-calculator](https://github.com/cartaorobbin/loan-calculator). Key accomplishments:

- **Correct Algorithm**: Implemented Progressive Price Schedule (French amortization system)
- **Reference Validation**: Produces exact expected values matching the reference test
- **Clean OOP Design**: Proper use of `__init__`, instance variables, and method delegation
- **Comprehensive Testing**: 254 total tests passing, including 10 PriceScheduler validation tests
- **Daily Rate Support**: Correctly handles `InterestRate("3% d")` for 3% daily rates

**Test Results:**
- PMT calculation: ✅ $999.9997 (matches reference $1000.00)
- Interest allocation: ✅ Exact match [255.91, 233.58, 210.59, ...]
- Principal allocation: ✅ Exact match [744.09, 766.42, 789.41, ...]
- Balance progression: ✅ Exact match [8530.20 → 7786.11 → ... → 0.0]

## Project Definition & Initial Setup

## Architectural Decisions Summary

### Core Models Design
1. **Money Class**: High internal precision, 2-decimal "real money" representation
2. **CashFlow Structure**: Container with CashFlowItems for individual transactions
3. **Loan Model**: State machine generating cash flows on demand (expected/actual/remaining)
4. **Flexible Scheduling**: `due_dates: List[Date]` instead of rigid payment frequencies
5. **InterestRate Safety**: Explicit decimal/percentage handling with conversion methods
6. **Schedule Generation**: 3 items per payment (total + interest + principal breakdown)
7. **Interest Calculation**: Daily compounding based on exact days between payments
8. **Payment Strategy**: Fixed payment amounts for irregular schedules (initial approach)
9. **Disbursement Handling**: Automatically included in generated schedules

### Task Group 1: Environment Setup & Core Implementation (IN PROGRESS)
**Goal**: Set up development environment and implement core classes

#### Environment Setup
- [x] Setup pyenv with Python version specified in pyproject.toml
- [x] Create virtual environment using pyenv virtualenv
- [x] Setup direnv with .envrc to auto-activate environment
- [x] Install dependencies with poetry install
- [x] Setup pre-commit hooks
- [x] Verify development environment is working

#### Core Class Implementation  
- [x] Implement Money class with high-precision internal representation
- [x] Implement InterestRate class with explicit conversion methods
- [x] Implement CashFlowItem class for individual transactions
- [x] Implement CashFlow class as container for CashFlowItems
- [x] Implement SQLAlchemy-style query interface for CashFlow filtering
- [x] Implement Loan class with PaymentScheduler separation of concerns
- [x] Implement PMT calculation function in PaymentScheduler
- [x] Implement amortization schedule generation with daily compounding
- [ ] Add helper functions for date generation (monthly, bi-weekly, etc.)

#### Testing & Validation
- [x] Create comprehensive test suite for Money class (45 tests)
- [x] Create test suite for InterestRate conversions (81 tests)
- [x] Create test suite for CashFlow operations (84 tests)
- [x] Create test suite for CashFlowQuery filtering and operations
- [x] Create test suite for Loan calculations (34 tests)
- [x] Create test suite for PriceScheduler and PaymentSchedule dataclass (10 tests)
- [x] Validate PMT calculations against known examples
- [x] Test irregular payment schedules
- [x] Test proper interest/principal allocation in payments
- [x] Test scheduler architecture with configurable schedulers
- [x] **Validate PriceScheduler against reference implementation (cartaorobbin/loan-calculator)**
- [x] **Test Progressive Price Schedule (French amortization system) with exact expected values**

#### Documentation & Polish
- [ ] Update README with MoneyWarp description and examples
- [ ] Add docstrings to all public methods
- [ ] Create usage examples for each core class
- [ ] Document architectural decisions

### Key Decisions Made:
1. **Architecture Approach**: Will build upon loan-calculator concepts but with a more intuitive "time-warping" metaphor
2. **Core Focus**: Personal loan analysis with emphasis on cash flow modeling
3. **Development Strategy**: Start with core models (CashFlow, Loan, InterestRate), then build TimeMachine

### Architectural Decisions Completed:
1. **CashFlow Model**: Container with CashFlowItems (individual transactions)
2. **Loan Structure**: State machine that generates cash flows on demand (expected, actual, remaining)
3. **Flexible Scheduling**: Use `due_dates: List[Date]` instead of rigid payment frequencies
4. **Interest Rate Safety**: Dedicated `InterestRate` class with explicit decimal/percentage handling

### Next Priority Tasks:

**Remaining Core Implementation:**
- [ ] Add helper functions for date generation (monthly, bi-weekly, etc.)

**Documentation & Polish (In Progress):**
- [x] Update README with MoneyWarp description and examples
- [x] Add docstrings to all public methods ✅ (Already complete!)
- [x] Create usage examples for each core class (4/6 complete)
  - [x] Quick Start Guide
  - [x] Money & Precision examples
  - [x] Interest Rate examples  
  - [x] Cash Flow Analysis examples
  - [ ] Loan Analysis examples
  - [ ] Advanced Scenarios examples
- [ ] Document architectural decisions

**Future Enhancements:**
- [ ] Implement additional scheduler types (Constant, SAC, etc.)
- [ ] Add NPV, IRR, and other TVM functions
- [ ] Implement TimeMachine for "what if" scenarios
- [ ] Add support for multiple currencies

---
*Last updated: 2025-09-12*
