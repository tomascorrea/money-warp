# Development Environment

## Required Tools

- **pyenv** + **pyenv-virtualenv** — Python version and virtualenv management
- **direnv** — automatic environment activation on `cd`
- **Poetry** — dependency management (configured in `pyproject.toml`)
- **pre-commit** — git hooks for formatting and linting

## Setup

```bash
# Install Python version (check pyproject.toml for constraint, currently >=3.9)
pyenv install 3.11.5
pyenv virtualenv 3.11.5 money-warp
pyenv local money-warp          # writes .python-version

# direnv (auto-activates environment)
echo "layout python" > .envrc   # .envrc is gitignored
direnv allow .

# Install deps and hooks
poetry install
poetry run pre-commit install
```

## Verification

```bash
python --version                # 3.11.x
poetry env info                 # correct virtualenv
poetry run pytest               # all tests pass
```

## Daily Workflow

```bash
poetry run pytest                         # run tests
poetry run black .                        # format
poetry run isort .                        # sort imports
poetry run ruff check .                   # lint
poetry run mypy money_warp                # type check
poetry run pre-commit run --all-files     # all checks
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Environment not activating | `direnv reload && direnv allow .` |
| Poetry can't find Python | `poetry env use $(pyenv which python) && poetry install` |
| Pre-commit issues | `poetry run pre-commit clean && poetry run pre-commit install` |
| Import errors | Check `PYTHONPATH` and that the virtualenv is active |
| Poetry lock conflicts | `poetry lock --no-update` |
