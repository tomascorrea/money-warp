---
name: quality-assurance
description: Run quality assurance checks on the current chat session — pre-task validation, post-task checklist, and code review. Use when finishing a task, before committing, or when the user asks for a QA review.
---

# Quality Assurance

This skill defines the QA protocol for the project. It can be invoked explicitly ("run QA") or referenced by the dev workflow at key checkpoints.

## A. Chat-Mode Interpretation

The chat-start triage (`.cursor/rules/dev-workflow-activation.mdc`) determines the mode for each conversation:

| Mode | Dev workflow steps | Quality rules |
|------|-------------------|---------------|
| **Full** | All steps (plan, branch, commits, PR, release) | Enforced |
| **Quick** | Skipped | Enforced |

In **both** modes, every code change must satisfy the quality rules in `.cursor/rules/quality.mdc` and the checklists below.

## B. Pre-Task Validation

Before writing any code, verify:

1. **Understand the context** — Read relevant source files, tests, and documentation to understand the area being changed.
2. **Check architecture fit** — Confirm the planned change is consistent with the existing design and patterns.
3. **Identify affected tests** — Locate existing tests that cover the area. Know what needs to run after the change.
4. **Check for related docs** — If the project has documentation or knowledge files, note which ones may need updating.

## C. Post-Task Checklist

After completing a change, verify each item before committing:

- [ ] **Tests pass** — Run the project's test suite. No regressions.
- [ ] **No new lint errors** — Run the linter. Fix any errors introduced by the change.
- [ ] **Formatting clean** — Run the formatter. Output matches project standards.
- [ ] **Test quality** — New or modified tests follow the project's testing conventions and any installed testing rules.
- [ ] **Type hints** — All new functions and class attributes have type annotations.
- [ ] **No obvious comments** — Comments explain "why", not "what".

### Full-mode only

These additional checks apply when the full dev workflow is active:

- [ ] **Documentation updated** — If the change affects user-facing behavior, update relevant docs.
- [ ] **Knowledge files updated** — If the change reveals non-obvious design decisions or gotchas, update knowledge files (if the project uses them).

## D. Code Review Patterns

When reviewing code (your own or upon request), check for:

### Correctness
- Does the logic handle edge cases?
- Are error conditions handled explicitly, not silently swallowed?
- Are boundary values tested?

### Test Quality
- Each test covers a single behavior
- Tests are deterministic — no conditional logic inside test functions
- Assertions verify expected outcomes explicitly
- Mocks are used only for truly external dependencies
- Follow the project's testing rules for language-specific patterns

### Consistency
- Naming follows project conventions
- New code matches the patterns used in surrounding code
- No duplicated logic that should be extracted

### Common Mistakes
- Missing type hints on new functions
- Stale imports or unused variables
- Tests that pass trivially (always true assertions, unreachable code paths)
- Comments that narrate code instead of explaining intent
