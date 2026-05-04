---
name: fix-bug
description: Fix bugs using a strict TDD workflow. Use when the user reports a bug, asks to fix a bug, debug an issue, or says things like "fix this bug", "this is broken", "test and fix", or "why is this failing". Enforces test-first discipline — a failing test must exist before any fix is applied.
---

# Fix Bug (TDD)

Fix bugs by writing a failing test first, then making the minimal code change to pass it. **No fix is allowed until a failing test proves the bug exists.**

---

## GitHub API Access

If the bug comes from a GitHub issue, determine which access method is available:

1. **GitHub MCP** (preferred): Check if a GitHub MCP server is configured by scanning the mcps folder for a server matching `github` or containing `github` in its name. If found, verify with a `get_me` call.
2. **gh CLI** (fallback): Run `gh auth status` to verify authentication.

Resolve `owner` and `repo` from the git remote:

```bash
git remote get-url origin
```

Skip this section if the bug comes from Linear or a direct description.

---

## Phase 1: Understand the Bug

Gather enough context to reproduce the problem. Ask the user **one question at a time** if anything is unclear.

### 1.1 Determine the bug source

The bug report can come from different sources. Detect which one based on what the user provides:

| User provides | Source type |
|---------------|-------------|
| A GitHub issue URL or `#<number>` | GitHub issue |
| A Linear issue ID (e.g., `ENG-123`, `LIN-42`) or URL | Linear issue |
| A description, error log, or stack trace | Direct report |

**GitHub issue** — Fetch the issue details:

Via MCP (if a GitHub MCP server is available):

```
CallMcpTool: server=github, toolName=issue_read
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "method": "get" }
```

Via CLI (fallback):

```bash
gh issue view <number> --json title,body,labels,comments
```

**Linear issue** — Fetch the issue details:

```
CallMcpTool: server=plugin-linear-linear, toolName=get_issue
arguments: { "id": "<issue-id>" }
```

**Direct report** — Use the description as-is.

### 1.2 Extract the bug facts

Regardless of the source, extract these three items:

- **What is happening** — the actual (broken) behavior
- **What should happen** — the expected (correct) behavior
- **How to trigger it** — steps, input, or conditions that reproduce the bug

If any of these are missing from the issue or description, ask the user to clarify.

### 1.3 Read the affected code

Read the source file(s) involved. Trace the execution path from the entry point (route, CLI command, function call) through to where the bug manifests.

### 1.4 Identify the root cause area

Narrow down the specific function, method, or code block that is responsible. State your hypothesis to the user before proceeding:

> "The bug appears to be in `<function>` — it does X when it should do Y because of Z. I'll write a test that proves this."

Wait for the user to confirm or correct the hypothesis.

---

## Phase 2: Discover Test Infrastructure

Before writing the test, understand the project's testing conventions.

### 2.1 Detect the test runner

Look for configuration files that indicate the test framework:

| Signal | Test runner |
|--------|-------------|
| `pytest.ini`, `pyproject.toml [tool.pytest]`, `conftest.py` | pytest |
| `package.json` with `test` script, `jest.config.*`, `vitest.config.*` | jest / vitest |
| `Cargo.toml` | cargo test |
| `go.mod` | go test |
| `mix.exs` | mix test |
| `build.gradle`, `pom.xml` | JUnit |

If multiple signals exist, prefer the one closest to the affected module.

### 2.2 Find existing tests for the module

Search for test files that correspond to the buggy module:

- Same directory (`test_*.py`, `*.test.ts`, `*_test.go`, etc.)
- Mirror directory (`tests/`, `__tests__/`, `spec/`)

### 2.3 Read test conventions

Read 1-2 existing test files to understand:

- Naming patterns (function names, file names)
- Available fixtures, helpers, or test utilities
- How test data is set up (factories, fixtures, builders, inline)
- Import style and organization

Match these conventions when writing the new test.

---

## Phase 3: Write the Failing Test (RED)

This is the critical phase. The test must fail against the current code.

### 3.1 Write the test

Create a test that:

- Asserts the **correct/expected** behavior (not the buggy behavior)
- Is minimal — tests only the specific bug, not unrelated concerns
- Has a descriptive name: `test_<what>_<expected_outcome>` or equivalent for the language
- Follows the project's existing test conventions (from Phase 2)

Place the test in the appropriate test file. If no test file exists for the module, create one following the project's naming convention.

### 3.2 Run the test

Run **only** the new test:

```
<test-runner> <path-to-test-file>::<test-name>
```

### 3.3 Confirm the test fails

**HARD GATE — Do not proceed to Phase 4 until this is satisfied.**

The test MUST fail. Verify:

1. The test **ran** (did not error due to import/syntax issues)
2. The test **failed on the assertion** (not on setup or unrelated errors)
3. The failure message reflects the bug (e.g., "expected 200 but got 500", "expected True but got False")

If the test passes, it does not capture the bug. Go back to 3.1 and rethink:

- Is the hypothesis from Phase 1 correct?
- Is the test exercising the right code path?
- Are the test inputs triggering the buggy condition?

If the test errors (import failure, missing fixture, syntax error), fix the test infrastructure issue and re-run. Do not confuse test errors with test failures.

---

## Phase 4: Fix the Bug (GREEN)

Now — and only now — fix the code.

### 4.1 Make the minimal fix

Change the **smallest amount of code** that makes the failing test pass. Resist the urge to refactor, clean up, or improve nearby code. Those are separate tasks.

### 4.2 Run the test again

Run the same test from Phase 3:

```
<test-runner> <path-to-test-file>::<test-name>
```

### 4.3 Confirm the test passes

The test MUST pass. If it still fails:

- Re-read the failure message
- Adjust the fix
- Re-run

Iterate until the test is green.

---

## Phase 5: Verify No Regressions

### 5.1 Run the broader test suite

Run all tests in the affected module or directory:

```
<test-runner> <path-to-test-directory>
```

If the test suite is small enough, run the full suite. If it is large, run at minimum the tests for the affected module and any closely related modules.

### 5.2 Handle failures

If any existing tests broke:

- Determine if the fix changed correct behavior (the fix is wrong) or if the old test was asserting buggy behavior (the test needs updating)
- Fix the issue and re-run
- Do not suppress or delete existing tests without explaining why to the user

### 5.3 Report results

Tell the user:

- The test that was written and what it verifies
- The fix that was applied and why
- The test suite results (all passing, or any issues found)

---

## Anti-Patterns

- **Fixing before testing** — Never change the buggy code before a failing test exists. This is the cardinal rule.
- **Testing the buggy behavior** — The test must assert the correct behavior, not `assert result == wrong_value`.
- **Overly broad tests** — Write a focused test for the specific bug. A test that checks 10 things is hard to trust.
- **Big-bang fixes** — Make the smallest change possible. Refactoring is a separate step.
- **Confusing errors with failures** — A test that errors on import is not a "failing test." Fix the error, then check the assertion.
- **Skipping the test run** — Always run the test. Never assume it fails or passes based on reading the code.
