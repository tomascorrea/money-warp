# MoneyWarp - Current Active Tasks

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
- [ ] Setup pyenv with Python version specified in pyproject.toml
- [ ] Create virtual environment using pyenv virtualenv
- [ ] Setup direnv with .envrc to auto-activate environment
- [ ] Install dependencies with poetry install
- [ ] Setup pre-commit hooks
- [ ] Verify development environment is working

#### Core Class Implementation  
- [ ] Implement Money class with high-precision internal representation
- [ ] Implement InterestRate class with explicit conversion methods
- [ ] Implement CashFlowItem class for individual transactions
- [ ] Implement CashFlow class as container for CashFlowItems
- [ ] Implement basic Loan class structure
- [ ] Implement PMT calculation function
- [ ] Implement amortization schedule generation with daily compounding
- [ ] Add helper functions for date generation (monthly, bi-weekly, etc.)

#### Testing & Validation
- [ ] Create comprehensive test suite for Money class
- [ ] Create test suite for InterestRate conversions
- [ ] Create test suite for CashFlow operations
- [ ] Create test suite for Loan calculations
- [ ] Create test suite for schedule generation
- [ ] Validate PMT calculations against known examples
- [ ] Test irregular payment schedules

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

### Next Steps:
1. Analyze the loan-calculator reference code structure
2. Design the core module architecture
3. Implement basic financial functions

---
*Last updated: 2025-09-12*
