---
name: dev-workflow
description: Automate the full development cycle from issue to pull request using GitHub Issues. Use when the user wants to work on a feature, fix a bug, start a dev task, or says things like "let's work on", "implement", or "fix".
---

# Dev Workflow (GitHub Issues)

Guide the developer through the full cycle: issue -> branch -> plan -> implement -> PR -> release.

## GitHub API Access

Before performing any GitHub operations, determine which access method is available:

1. **GitHub MCP** (preferred): Check if a GitHub MCP server is configured by scanning the mcps folder for a server matching `github` or containing `github` in its name. If found, verify with a `get_me` call. Note the server name for all subsequent MCP calls.
2. **gh CLI** (fallback): Run `gh auth status` to verify authentication.

If neither is available, use `AskQuestion` to block the workflow:

```
prompt: "GitHub authentication is required but not configured. Please set up a GitHub MCP server or run `gh auth login`, then continue."
options:
  - id: retry
    label: "I've authenticated — retry"
```

After the user selects retry, re-run the authentication checks above. If still failing, present the same `AskQuestion` again.

Also resolve `owner` and `repo` from the git remote:

```bash
git remote get-url origin
```

Parse `owner/repo` from the URL. Store these values — GitHub MCP tools require them as explicit parameters.

Use the detected method consistently for all GitHub operations below. Each operation shows both methods: **MCP** first, then **CLI**.

## Resume (Continuing from a Previous Chat)

If resuming an in-progress workflow (the user selected "Continue current work" from the chat triage), follow these steps instead of starting from Step 1:

1. Get the current branch name:

```bash
git branch --show-current
```

2. Extract the issue number from the branch name. Branches follow the pattern `<type>/<issue-number>-<slug>` (e.g., `fix/42-login-timeout` → issue `42`).

3. Fetch the issue details and comments:

**Via MCP:**

```
CallMcpTool: server=github, toolName=issue_read
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "method": "get" }
```

Then fetch comments:

```
CallMcpTool: server=github, toolName=issue_read
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "method": "get_comments" }
```

**Via CLI:**

```bash
gh issue view <number> --json title,body,labels,number,comments
```

4. Search the issue comments for an **Implementation Plan**. If found:
   - Parse the plan tasks
   - Cross-reference with the git log (`git log main..HEAD --oneline`) to determine which tasks are likely completed
   - Create TodoWrite entries: mark completed tasks as `completed`, set the next unfinished task to `in_progress`, rest as `pending`
   - Tell the user what was found and which task you'll resume from
   - Continue from **Step 5: Execute**

5. If no plan is found in the comments:
   - Tell the user the issue context and that no plan was stored yet
   - Continue from **Step 3: Plan**

---

## Step 1: Issue

Use AskQuestion:

```
prompt: "Do you already have a GitHub issue for this work?"
options:
  - Yes, I have an issue URL
  - No, let's create one
```

### If the user has an issue

Ask for the issue URL or number. Fetch the issue details:

**Via MCP:**

```
CallMcpTool: server=github, toolName=issue_read
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "method": "get" }
```

**Via CLI:**

```bash
gh issue view <number> --json title,body,labels,number
```

Parse the title, description, and labels for context.

### If the user does not have an issue

Discuss the work with the user to define:
- **Title**: concise summary
- **Description**: what needs to happen and why
- **Labels**: bug, feature, enhancement, etc.

When the issue is well-defined, create it:

**Via MCP:**

```
CallMcpTool: server=github, toolName=issue_write
arguments: { "owner": "<owner>", "repo": "<repo>", "method": "create", "title": "<title>", "body": "<description>", "labels": ["<label1>", "<label2>"] }
```

**Via CLI:**

```bash
gh issue create --title "<title>" --body "<description>" --label "<labels>"
```

Capture the issue number from the output.

## Step 2: Branch

Determine the branch type from labels or context:
- `bug` label -> `bug/`
- `feature` or `enhancement` label -> `feat/`
- otherwise -> `task/`

Create a slug from the issue title (lowercase, hyphens, max 40 chars).

```bash
git checkout -b <type>/<issue-number>-<slug>
git push -u origin HEAD
```

Example: `bug/42-login-timeout`

## Step 3: Plan

Tell the user: "Switching to plan mode to design the implementation."

Use the SwitchMode tool to enter plan mode. Then create an implementation plan by:
1. Reading the issue description
2. Exploring the relevant parts of the codebase
3. Drafting a step-by-step plan with specific files and changes

The plan should include:
- A summary of the approach
- Ordered list of tasks (each should be a concrete, testable unit of work)
- Files to create or modify per task
- Test strategy

Wait for the user to review and approve the plan.

## Step 4: Store Plan

Once the plan is approved:

1. Post the plan as a comment on the issue:

**Via MCP:**

```
CallMcpTool: server=github, toolName=add_issue_comment
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "body": "## Implementation Plan\n\n<the approved plan>" }
```

**Via CLI:**

```bash
gh issue comment <number> --body "$(cat <<'EOF'
## Implementation Plan

<paste the approved plan here>

EOF
)"
```

2. Create TodoWrite entries for each task in the plan. Set the first task to `in_progress`, the rest to `pending`.

## Step 5: Execute

Switch back to agent mode using the SwitchMode tool.

### Bug fix TDD discipline

If the issue has a `bug` label (or was created via the "Fix a bug" triage), apply TDD discipline during implementation:

1. **Understand the bug** — extract what is happening, what should happen, and how to trigger it. Read the affected code and identify the root cause. State a hypothesis to the user before proceeding.
2. **Write a failing test first** — the test must assert the correct/expected behavior, be minimal, and follow the project's existing test conventions. Run it and confirm it **fails on the assertion** (not on setup errors). Do not proceed to the fix until the test fails.
3. **Make the minimal fix** — change the smallest amount of code that makes the failing test pass. Resist refactoring or improving nearby code.
4. **Verify no regressions** — run the broader test suite for the affected module. If existing tests broke, determine whether the fix changed correct behavior or the old test was asserting buggy behavior.

### Standard execution

Work through the tasks sequentially:
1. Pick the current `in_progress` task
2. Implement the changes (following TDD discipline above if this is a bug fix)
3. Run tests if applicable
4. Mark the task as `completed` in TodoWrite
5. Move the next task to `in_progress`

After completing each task, post a progress comment on the issue:

**Via MCP:**

```
CallMcpTool: server=github, toolName=add_issue_comment
arguments: { "owner": "<owner>", "repo": "<repo>", "issue_number": <number>, "body": "Completed: <task description>" }
```

**Via CLI:**

```bash
gh issue comment <number> --body "Completed: <task description>"
```

## Step 6: Sync

Throughout execution, keep the issue and TodoWrite aligned:
- When a task is completed locally, comment on the issue
- If the plan needs adjustment mid-execution, update both the TodoWrite list and post an updated plan comment on the issue
- If new tasks emerge, add them to both TodoWrite and the issue

After all implementation tasks are complete, post a completion summary on the issue before proceeding.

## Step 7: Update Knowledge

Before creating the PR, update the project's knowledge files:

1. Check if the changes affect a feature area that has an existing `knowledge/*.md` file — if so, read the file and update any sections that are now stale. Rewrite sections to reflect the current state rather than appending notes.
2. If a new feature area was introduced and no knowledge file exists, create one following the structure in `.cursor/rules/knowledge.mdc` (Overview, Design Decisions, API Surface, Key Learnings / Gotchas).
3. If the changes affect the overall architecture, update `knowledge/architecture.md`.
4. Commit knowledge updates separately:

```bash
git add knowledge/
git commit -m "docs: update knowledge for <feature>"
```
## Step 8: Verify

Before creating the PR, run the full test suite and linter to confirm nothing is broken:

1. Run the project's test suite (e.g., `pytest`, `go test`, `flutter test`). **All tests must pass.**
2. Run the project's linter/formatter checks (e.g., `ruff check .`, `black --check .`).
3. If tests or lints fail, fix the issues and re-run until green.
4. Do **not** proceed to the PR step with failing tests.

## Step 9: Pull Request

When all tasks are complete and tests pass:

1. Ensure all changes are committed
2. Push the branch: `git push`
3. Create the PR:

**Via MCP:**

```
CallMcpTool: server=github, toolName=create_pull_request
arguments: { "owner": "<owner>", "repo": "<repo>", "title": "<issue-title>", "body": "## Summary\n<1-3 bullet points>\n\nCloses #<issue-number>\n\n## Test plan\n<checklist>", "head": "<branch-name>", "base": "main" }
```

**Via CLI:**

```bash
gh pr create --title "<issue-title>" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points describing what was done>

Closes #<issue-number>

## Test plan
<checklist of how to verify the changes>

EOF
)"
```

4. Tell the user the PR is ready for review and provide the PR URL.

## Step 10: Code Review

After the PR is created, check if a code-review skill is available at `.cursor/skills/code-review/SKILL.md`.

If the skill exists:

1. Read the skill file.
2. Launch a `Task` subagent (`subagent_type="generalPurpose"`) with:
   - The full contents of the code-review skill as the prompt instructions
   - The PR number, owner, and repo already known from the workflow
   - A directive to skip Phase 1 (PR selection) — the PR number is already known, start from Phase 1.2
3. Wait for the subagent to complete.
4. Display the subagent's summary to the user (link to PR, number of inline comments posted by severity).

If the subagent fails or times out, inform the user that the automated review could not be completed and suggest running it manually later (e.g., "review this PR").

If the skill does not exist, skip this step.

## Step 11: Review & Merge

Before presenting the options, check if a code-review skill is available at `.cursor/skills/code-review/SKILL.md`.

Use the **`AskQuestion`** tool. If the code-review skill exists, include the "Run code review" option; otherwise omit it:

```
prompt: "What would you like to do next?"
options:
  - Run code review  # only include if code-review skill exists
  - Check review status now
  - PR is approved, please merge
  - Come back later — I'll request a review myself
```

### If "Run code review"

1. Read the code-review skill from `.cursor/skills/code-review/SKILL.md`.
2. Launch a `Task` subagent (`subagent_type="generalPurpose"`) with:
   - The full contents of the code-review skill as the prompt instructions
   - The PR number, owner, and repo already known from the workflow
   - A directive to skip Phase 1 (PR selection) — the PR number is already known, start from Phase 1.2
3. Wait for the subagent to complete.
4. Display the subagent's summary to the user (link to PR, number of inline comments posted by severity).

If the subagent fails or times out, inform the user that the review could not be completed and suggest running it manually later (e.g., "review this PR").

After the review completes (or fails), present the Step 11 AskQuestion again so the user can check status, merge, or take other actions.

### If "Check review status now"

1. Check CI status and review state:

**Via MCP:**

```
CallMcpTool: server=github, toolName=pull_request_read
arguments: { "owner": "<owner>", "repo": "<repo>", "pullNumber": <number>, "method": "get_check_runs" }
```

```
CallMcpTool: server=github, toolName=pull_request_read
arguments: { "owner": "<owner>", "repo": "<repo>", "pullNumber": <number>, "method": "get_reviews" }
```

**Via CLI:**

```bash
gh pr checks
gh pr view --json reviewDecision,reviews,statusCheckRollup
```

2. Summarize the current state:
   - CI checks: passing / failing / pending
   - Review status: approved / changes requested / pending / no reviewers

3. **If checks pass and reviews are approved**, use **AskQuestion**:

```
prompt: "PR is approved and checks pass. Merge it?"
options:
  - Yes, squash and merge
  - Yes, merge commit
  - Yes, rebase and merge
  - No, not yet
```

4. If the user selects a merge strategy:

**Via MCP:**

```
CallMcpTool: server=github, toolName=merge_pull_request
arguments: { "owner": "<owner>", "repo": "<repo>", "pullNumber": <number>, "merge_method": "<squash|merge|rebase>" }
```

Then switch to main locally:

```bash
git checkout main && git pull
```

**Via CLI:**

```bash
gh pr merge --<strategy> --delete-branch
git checkout main && git pull
```

5. If checks are failing or reviews are not yet approved, tell the user what is pending and suggest coming back later.

### If "PR is approved, please merge"

Use **AskQuestion**:

```
prompt: "Which merge strategy?"
options:
  - Squash and merge
  - Merge commit
  - Rebase and merge
```

Then merge:

**Via MCP:**

```
CallMcpTool: server=github, toolName=merge_pull_request
arguments: { "owner": "<owner>", "repo": "<repo>", "pullNumber": <number>, "merge_method": "<squash|merge|rebase>" }
```

Then switch to main locally:

```bash
git checkout main && git pull
```

**Via CLI:**

```bash
gh pr merge --<strategy> --delete-branch
git checkout main && git pull
```

### If "Come back later"

Tell the user they can resume this step by asking to check the PR status or merge. End the current session here — the Release step runs after the PR is merged.

## Step 12: Release

> This step only applies to projects with a release flow.

After the PR is merged:

### 12.1 Determine the next version

1. Detect the latest release tag:

**Via MCP:**

```
CallMcpTool: server=github, toolName=list_releases
arguments: { "owner": "<owner>", "repo": "<repo>", "perPage": 1 }
```

**Via CLI:**

```bash
gh release list --limit 1
```

2. Determine the next version using semantic versioning:
   - Bug fix -> patch bump (1.0.0 -> 1.0.1)
   - Feature -> minor bump (1.0.0 -> 1.1.0)
   - Breaking change -> major bump (1.0.0 -> 2.0.0)

   Use the issue labels and nature of changes to decide.

### 12.2 Bump the version in source files

The version in source files **must** match the release tag. Skipping this step causes CI publish failures (e.g., PyPI rejects duplicate versions).

1. Detect where the version is defined. Check in order:
   - `pyproject.toml` — look for a static `version = "x.y.z"` under `[project]` or `[tool.poetry]`
   - `version.py` or `src/<package>/__version__.py` — a standalone version file
   - `src/<package>/__init__.py` — a `__version__` variable

2. Update **all** version sources found to the new version number.

3. Confirm with the user before committing:

Use **AskQuestion**:

```
prompt: "Release v<new-version> (current: v<current-version>). Bump version and create release?"
options:
  - Yes, bump and release
  - Change the version number
  - Skip release for now
```

If "Change the version number", ask for the desired version. If "Skip release for now", stop here.

4. Commit and push the version bump:

```bash
git add -A
git commit -m "bump: v<version>"
git push
```

### 12.3 Create the release

> No GitHub MCP equivalent exists for release creation — use `gh` CLI regardless of the detected method.

```bash
gh release create v<version> --generate-notes --title "v<version>"
```

### 12.4 Verify the release pipeline

After creating the release, check that the triggered CI workflow succeeds:

**Via MCP:**

```
CallMcpTool: server=github, toolName=actions_list
arguments: { "owner": "<owner>", "repo": "<repo>", "method": "list_workflow_runs", "per_page": 1 }
```

**Via CLI:**

```bash
gh run list --limit 1 --json name,status,conclusion,url
```

If the workflow is still running, wait and re-check. If it fails, tell the user immediately with the run URL — do not wait for them to discover it.

Tell the user the release has been created and whether the publish pipeline succeeded.

## Step 13: End

Summarize what was accomplished:
- Issue number and title
- Branch name
- Number of commits
- PR URL
- Release version (if applicable)
