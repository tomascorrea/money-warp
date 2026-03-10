---
name: quality-assurance
description: Run quality assurance checks on the current chat session -- chat-start triage, pre-task validation, post-task checklist, and code review. Use when finishing a task, before committing, or when the user asks for a QA review.
---

# Quality Assurance

This skill defines the QA protocol for money-warp. It covers four areas: chat-start triage, pre-task validation, post-task checklist, and code review patterns.

## A. Chat-Start Triage Protocol

The triage question itself lives in `.cursor/rules/chat-triage.mdc` (always applied). This section defines what each answer means in practice.

### What each mode means

**Full dev workflow** (`full`):
- Follow every rule in `development.mdc` strictly
- Mandatory planning phase before any code changes
- Feature branches, incremental commits, PR process
- Knowledge and docs updates required after feature work

**Quick task / exploration** (`quick`):
- Skip structured workflow steps: no mandatory planning phase, no feature branches, no PR process, no release steps
- All code quality rules still apply (see "Always Enforced" below)

### Always Enforced (both modes)

These rules apply regardless of the chosen mode:

- `Money` type for all monetary amounts (never raw `Decimal`, `float`, or `int`)
- `scipy.optimize` for root-finding and numerical solving (never hand-rolled loops)
- Type hints on all functions and classes
- Code formatting: Black, isort, Ruff
- Test patterns from `quality.mdc`: function-based tests, single concept per test, parametrize, exact values, no mocks, fixtures over helpers
- No imports inside functions or methods
- Docstrings on public API

### Workflow-Only (skipped in quick mode)

These are enforced only in full dev workflow mode:

- Mandatory plan-before-code phase with `CreatePlan`
- Feature branch creation (`feat/`, `fix/`, etc.)
- Incremental commits after each task
- PR creation with summary and test plan
- Release process (version bump, GitHub release)
- Knowledge file updates after feature completion
- Docs updates after API changes

## B. Pre-Task Validation

Before making any code changes, run through this checklist:

1. **Read knowledge files**: Read the relevant `knowledge/*.md` files to understand the area you are about to change. At minimum, read `knowledge/architecture.md`.

2. **Understand existing code**: Read the source files you plan to modify. Never edit a file you have not read first.

3. **Check architecture fit**: Verify the planned change aligns with the design described in `knowledge/architecture.md`. If it does not, discuss with the user before proceeding.

4. **Identify affected tests**: Search for existing tests that exercise the code you are changing. These tests must still pass after your changes.

5. **Check for related knowledge**: If the feature area has a knowledge file (e.g., `knowledge/loan.md` for loan changes), read it for gotchas and design decisions that might affect your approach.

## C. Post-Task Checklist

After completing a task, run through every item below. Do not skip any.

### C1. Tests pass

```bash
poetry run pytest
```

All tests must pass. If any fail, fix them before proceeding. Do not ignore failures.

### C2. No new lint errors

Run `ReadLints` on every file you edited. Fix any lint errors you introduced. Pre-existing lints that are unrelated to your changes can be left alone.

### C3. Formatting is clean

```bash
poetry run black --check .
poetry run isort --check .
```

If either reports changes needed, run the formatters and include the result in your changes.

### C4. Money type usage

If you wrote or modified any code that deals with monetary amounts, verify:
- All function parameters and return types that represent money use `Money`, not `Decimal`
- `Money.raw_amount` is only used for internal arithmetic, never exposed to callers
- Results are wrapped back into `Money` before returning

### C5. No hand-rolled solvers

If you wrote any root-finding or convergence logic, verify it uses `scipy.optimize` (fsolve, brentq, etc.) instead of manual iteration loops.

### C6. Test quality

If you wrote or modified tests, verify they follow `quality.mdc`:
- Function-based (no class-based test cases)
- Single concept per test (multiple asserts on the same result are fine)
- Parametrized for multiple input/output combinations
- Assert exact literal values, not computed results
- No conditional logic or loops inside tests
- Descriptive names: `test_[component]_[action]_[scenario]`
- No mocks unless absolutely necessary
- Prefer fixtures over helper functions

### C7. Knowledge and docs (full workflow mode only)

If a new feature was added or architecture changed:
- Create or update the relevant `knowledge/*.md` file
- Update `docs/` if the API surface changed
- Update `README.md` if user-facing functionality changed

## D. Code Review Patterns

When reviewing code changes (your own or when the user asks for a review), check for these common issues:

### D1. Project conventions

- Type hints on all functions and classes
- Docstrings on public functions, classes, and modules (Google or NumPy style)
- snake_case for functions/variables, PascalCase for classes
- Line length <= 88 characters
- Imports at module level (never inside functions or methods)
- Imports grouped and sorted with isort

### D2. Test quality

- No class-based test cases (`class TestX:` is forbidden)
- Single concept per test (multiple asserts on the same result are fine)
- `pytest.mark.parametrize` for multiple scenarios
- Exact literal values in assertions (no calculations in tests)
- No conditional logic or loops inside tests
- Descriptive names: `test_[component]_[action]_[scenario]`
- No mocks unless absolutely necessary
- Fixtures for reusable setup (not helper functions)

### D3. Common mistakes to catch

- Raw `Decimal`, `float`, or `int` used where `Money` should be
- Hand-rolled iteration loops for root-finding instead of `scipy`
- `pip install` instead of `poetry add`
- Imports inside functions or methods
- Vague assertions (`>`, `<`, `!=`) where exact values are known
- Missing type hints or docstrings on public API

### D4. Knowledge sync

- If the change affects a feature area that has a `knowledge/*.md` file, verify the knowledge file is still accurate
- If a new feature area was introduced, verify a knowledge file was created
- If docs describe the changed API, verify docs are updated
