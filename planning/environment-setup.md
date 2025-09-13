# MoneyWarp - Environment Setup Guide

## Development Environment Requirements

### Tools Needed
- **pyenv**: Python version management
- **pyenv-virtualenv**: Virtual environment management  
- **direnv**: Automatic environment activation
- **poetry**: Dependency management (already configured)

## Setup Steps

### 1. Install pyenv (if not already installed)
```bash
# macOS with Homebrew
brew install pyenv pyenv-virtualenv

# Add to shell profile (~/.zshrc or ~/.bash_profile)
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

### 2. Install Python Version
```bash
# Check required Python version in pyproject.toml (>=3.9,<4.0)
pyenv install 3.11.5  # or latest 3.11.x
pyenv global 3.11.5   # or set as global default
```

### 3. Create Virtual Environment
```bash
cd /Users/tomas/Documents/workspace/repos/money-warp
pyenv virtualenv 3.11.5 money-warp
pyenv local money-warp  # Sets .python-version file
```

### 4. Install direnv (if not already installed)
```bash
# macOS with Homebrew
brew install direnv

# Add to shell profile (~/.zshrc)
eval "$(direnv hook zsh)"
```

### 5. Create .envrc File (Local Only)
```bash
# Create .envrc in project root (this file is local and not committed)
echo "# MoneyWarp development environment - LOCAL FILE" > .envrc
echo "layout python" >> .envrc
direnv allow .
```

### 6. Install Dependencies
```bash
# Should auto-activate environment when entering directory
poetry install  # Installs all dependencies including dev tools
```

### 7. Setup Pre-commit Hooks
```bash
poetry run pre-commit install
```

### 8. Verify Setup
```bash
# Check Python version
python --version  # Should show 3.11.5

# Check virtual environment
which python  # Should point to pyenv virtualenv

# Check poetry
poetry env info  # Should show correct environment

# Run tests to verify everything works
poetry run pytest
```

## Environment Files Created

After setup, you should have:
- `.python-version` - pyenv local Python version (committed)
- `.envrc` - direnv configuration (LOCAL ONLY - not committed)
- `poetry.lock` - locked dependencies (committed)
- `.gitignore` - updated to ignore .envrc

## Daily Workflow

```bash
# Enter project directory
cd /Users/tomas/Documents/workspace/repos/money-warp
# Environment auto-activates via direnv

# Run commands
poetry run pytest
poetry run black .
poetry run mypy money_warp

# Or activate shell
poetry shell
pytest
black .
mypy money_warp
```

## Troubleshooting

### Environment not activating
```bash
direnv reload
direnv allow .
```

### Poetry not finding Python
```bash
poetry env use $(pyenv which python)
poetry install
```

### Pre-commit issues
```bash
poetry run pre-commit clean
poetry run pre-commit install
```

---
*Setup guide for MoneyWarp development environment*
