---
name: feature-dev-workflow
description: Guides AI through a structured feature development lifecycle with planning, branching, building, committing, pull requests, and releases. Use when the user wants to start a new feature, build something new, create a release, or asks to follow the dev workflow.
---

# Feature Development Workflow

This skill defines the end-to-end workflow for developing a new feature. Follow these phases in order. Never skip planning; never create a PR without tests.

## Phase 1: Ideation and Planning

**Goal**: Understand what we're building before writing any code.

1. Discuss the feature idea with the user
2. Ask clarifying questions (one at a time, per user preference)
3. Switch to Plan mode and create a plan using `CreatePlan`
4. **Do NOT make any code changes until the plan is approved**
5. Wait for explicit user approval before proceeding to Phase 2

## Phase 2: Branch Creation

**Goal**: Isolate the work on a feature branch.

Once the plan is approved:

1. Ensure the repo has no uncommitted changes on the current branch:
   ```bash
   git status
   ```
2. Create and checkout a new branch:
   ```bash
   git checkout -b feat/<short-description>
   ```
   - Use kebab-case for the description (e.g. `feat/grid-labels`, `feat/png-export`)
   - Keep it short -- 2-4 words max
3. Confirm to the user that the branch is ready

## Phase 3: Build

**Goal**: Implement the feature incrementally, following the plan.

1. Create todos from the plan using `TodoWrite` to track progress
2. Work through each todo one at a time
3. Follow all project conventions (see `.cursor/rules/`)
4. After completing each todo:
   - Check lints with `ReadLints` on edited files
   - Fix any introduced lint errors
   - Mark the todo as completed
   - Proceed to Phase 4 (commit) before starting the next todo

## Phase 4: Incremental Commits

**Goal**: Keep a clean, reviewable commit history with small, focused commits.

After completing each todo/task from the plan:

1. Stage and commit the relevant changes:
   ```bash
   git add <files>
   git commit -m "Descriptive message here"
   ```
2. **Commit message style**: Use conventional commit format
   - Prefix with type: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
   - Examples: `feat: add grid label rendering`, `fix: icon path for AWS nodes`, `docs: update README with label docs`
   - Keep the subject concise and lowercase after the prefix
3. Only commit after verifying the change works (lints pass, no obvious breakage)
4. Return to Phase 3 for the next todo

## Phase 5: Finalize and Pull Request

**Goal**: Ensure quality, then open a PR for review.

When all todos are completed:

### Pre-PR checklist

Run through this checklist before creating the PR:

1. **Run tests**:
   ```bash
   poetry run pytest
   ```
   If any test fails, fix it and commit the fix before proceeding.

2. **Update documentation** (per project rules):
   - Update `README.md` if the feature adds user-facing functionality
   - Update `docs/` pages if the API changed or a new feature was added
   - Add an example if appropriate
   - Commit documentation updates separately: `docs: update docs for <feature>`

3. **Update knowledge files** (per project rules):
   - Create or update the relevant `knowledge/<feature>.md` file if the feature changes architecture, API surface, or reveals non-obvious learnings
   - Commit knowledge updates separately: `docs: update knowledge for <feature>`

4. **Review the full diff** against the base branch:
   ```bash
   git diff main...HEAD
   ```

### Create the Pull Request

**Strategy**: Try GitHub MCP first, fall back to `gh` CLI.

#### Option A: GitHub MCP

Check if a GitHub MCP server is available by looking in the MCP descriptors folder. If a server with pull request creation capabilities exists, use it:

```
CallMcpTool:
  server: <github-mcp-server-name>
  toolName: create_pull_request (or similar -- read the tool descriptor first)
  arguments:
    title: "<short feature summary>"
    body: "<PR body, see template below>"
    base: "main"
    head: "feat/<short-description>"
```

Always read the MCP tool descriptor before calling it to get the exact parameter names.

#### Option B: GitHub CLI fallback

If no GitHub MCP is available, use `gh`:

```bash
git push -u origin HEAD
gh pr create --title "<short feature summary>" --body "$(cat <<'EOF'
<PR body, see template below>
EOF
)"
```

### PR body template

```markdown
## Summary
- <1-3 bullet points describing what was built>

## Changes
- <list of notable implementation details>

## Test plan
- [ ] All existing tests pass (`poetry run pytest`)
- [ ] <specific things to verify for this feature>

## Docs
- <list of documentation updates made, or "No docs changes needed">
```

### After PR creation

- Share the PR URL with the user
- The feature workflow is complete unless the user requests a release

## Phase 6: Release

**Goal**: Publish a new version to PyPI by creating a GitHub Release.

After a PR is merged, ask the user if they'd like to create a new release. It can also happen at any later point if the user requests it.

### Prerequisites

- You must be on `main` with a clean working tree
- The PR must already be merged

### Steps

1. **Switch to main and pull latest**:
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Bump the version** in `pyproject.toml`:
   - Ask the user what the new version should be (e.g. `0.2.0`, `1.0.0`)
   - Use `poetry version <version>` to update the `version` field in `[tool.poetry]`
   - Follow semver: breaking changes = major, new features = minor, fixes = patch

3. **Commit and push the version bump**:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to <version>"
   git push origin main
   ```

4. **Create the GitHub Release** using `gh`:
   ```bash
   gh release create v<version> --title "v<version>" --generate-notes
   ```
   - Always prefix the tag with `v` (e.g. `v0.2.0`)
   - `--generate-notes` auto-generates release notes from merged PRs
   - This triggers the `on-release-pypi.yml` workflow which builds and publishes to PyPI via OIDC

5. **Verify the publish**:
   - Share the release URL with the user
   - Remind them to check https://pypi.org/project/money-warp/ after a minute or two

## Phase Transitions Summary

```
Idea --> Plan (no code!) --> Branch --> Build/Commit loop --> Tests + Docs --> PR --> Release (optional)
```

Only move forward when the current phase is fully complete. If something fails (tests, lints), fix it in the current phase before advancing.
