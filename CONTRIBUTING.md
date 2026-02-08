# Contributing to Discord Music Bot

Thank you for contributing to the Discord Music Bot! This document provides guidelines for maintaining code quality.

## Table of Contents
- [Setup](#setup)
- [Code Quality Rules](#code-quality-rules)
- [Message Constants](#message-constants)
- [Testing](#testing)
- [Pre-commit Hooks](#pre-commit-hooks)

---

## Setup

### Development Environment

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd DiscordMusicPlayer
   ```

2. **Create virtual environment:**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev,test]"
   ```

4. **Install pre-commit hooks:**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

5. **Run tests:**
   ```bash
   pytest
   ```

---

## Code Quality Rules

### **CRITICAL: No Magic Strings!**

This codebase has **ZERO tolerance for hardcoded string literals** in production code. All messages must use constants from `src/domain/shared/messages.py`.

#### What are "magic strings"?

Magic strings are hardcoded string literals scattered throughout code:

```python
# ❌ BAD - Magic strings
logger.info("Database initialized")
raise ValueError("Invalid guild ID")
await ctx.send("✅ Track added to queue")
```

```python
# ✅ GOOD - Using constants
from domain.shared.messages import ErrorMessages, LogTemplates, DiscordUIMessages

logger.info(LogTemplates.DATABASE_INITIALIZED, db_path)
raise ValueError(ErrorMessages.INVALID_GUILD_ID)
await ctx.send(DiscordUIMessages.SUCCESS_TRACK_ADDED)
```

#### Why?

- **Maintainability**: Change message once, updates everywhere
- **Consistency**: Same message across codebase
- **I18n ready**: Easy to translate later
- **Type safety**: IDE autocomplete prevents typos
- **Searchability**: Easy to find all usages

#### Enforcement

Automated checks will catch:
- ✅ `logger.info(f"...")` → Must use `LogTemplates`
- ✅ `raise ValueError("...")` → Must use `ErrorMessages`
- ✅ Hardcoded Discord messages → Must use `DiscordUIMessages`

See [MESSAGES_GUIDE.md](MESSAGES_GUIDE.md) for detailed usage instructions.

---

## Message Constants

### Quick Reference

| Class | Purpose | Example |
|-------|---------|---------|
| `ErrorMessages` | Exception messages | `INVALID_GUILD_ID` |
| `LogTemplates` | Logging statements | `DATABASE_INITIALIZED` |
| `DiscordUIMessages` | User-facing Discord messages | `SUCCESS_TRACK_ADDED` |
| `EmojiConstants` | Emoji symbols | `SUCCESS`, `PLAY` |

### Adding a New Constant

1. **Determine the right class:**
   - User sees it? → `DiscordUIMessages`
   - Exception? → `ErrorMessages`
   - Logging? → `LogTemplates`
   - Emoji? → `EmojiConstants`

2. **Add to `src/domain/shared/messages.py`:**
   ```python
   class DiscordUIMessages:
       # Group with similar messages
       ACTION_PLAYLIST_IMPORTED = "📥 Imported {count} tracks from playlist"
   ```

3. **Use it:**
   ```python
   from domain.shared.messages import DiscordUIMessages

   await interaction.response.send_message(
       DiscordUIMessages.ACTION_PLAYLIST_IMPORTED.format(count=len(tracks))
   )
   ```

See [MESSAGES_GUIDE.md](MESSAGES_GUIDE.md) for complete documentation.

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_domain_music.py

# Run verbose
pytest -vv
```

### Test Requirements

- All new code must have tests
- Maintain 100% test pass rate (currently 483/483)
- Tests can use string literals (pre-commit allows it in tests/)

---

## Pre-commit Hooks

### What are pre-commit hooks?

Automated checks that run before each commit to maintain code quality.

### Installed hooks:

1. **Ruff linter** - Catches code quality issues including:
   - Magic string usage (`G004` - f-strings in logging)
   - Exception string literals (`EM` rules)
   - Code style issues

2. **Code formatters** - Auto-format code
3. **File checks** - Trailing whitespace, YAML syntax, etc.

### Setup

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Bypassing hooks (emergency only)

```bash
# Only in emergencies - will be caught in CI
git commit --no-verify -m "Emergency fix"
```

---

## Code Style

### Python Version
- **Required**: Python 3.11+
- Use modern features (match/case, | for unions, etc.)

### Import Organization
```python
# Standard library
import asyncio
import logging

# Third-party
import discord
from discord.ext import commands

# Local
from domain.shared.messages import LogTemplates
from config.settings import Settings
```

### Naming Conventions
- **Constants**: `SCREAMING_SNAKE_CASE`
- **Classes**: `PascalCase`
- **Functions/variables**: `snake_case`
- **Private**: `_leading_underscore`

### Type Hints
- Always use type hints
- Use `from __future__ import annotations` for forward references

```python
from __future__ import annotations

def process_track(track: Track, guild_id: int) -> Track | None:
    ...
```

---

## Architecture

### DDD (Domain-Driven Design)

```
src/
├── domain/          # Business logic, entities, value objects
├── application/     # Use cases, services
├── infrastructure/  # External integrations (Discord, database, AI)
└── config/          # Settings, DI container
```

### Layers
- **Domain**: Pure business logic, no external dependencies
- **Application**: Orchestrates domain logic
- **Infrastructure**: External services (Discord, database, yt-dlp)

### Dependency Rule
- Domain depends on nothing
- Application depends on domain
- Infrastructure depends on domain and application

---

## Pull Request Guidelines

### Before submitting:

- [ ] All tests pass (`pytest`)
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] No magic strings (all use constants from `messages.py`)
- [ ] New constants added to appropriate class
- [ ] Code follows DDD architecture
- [ ] Type hints on all functions
- [ ] Docstrings on public APIs

### PR Description Template

```markdown
## Summary
Brief description of changes

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring
- [ ] Documentation

## Testing
- [ ] Added tests
- [ ] All tests pass (483/483)
- [ ] Manually tested

## Message Constants
- [ ] Used existing constants
- [ ] Added new constants (list them)
- [ ] No magic strings

## Checklist
- [ ] Pre-commit hooks pass
- [ ] Code follows DDD architecture
- [ ] Documentation updated
```

---

## Common Mistakes

### ❌ DON'T

```python
# Magic strings
logger.info("Track started playing")
raise ValueError("Invalid ID")
await ctx.send("Error occurred")

# F-strings in logging
logger.debug(f"Processing {item}")

# Missing type hints
def process(data):
    ...
```

### ✅ DO

```python
# Use constants
logger.info(LogTemplates.TRACK_STARTED, track_id)
raise ValueError(ErrorMessages.INVALID_ID)
await ctx.send(DiscordUIMessages.ERROR_GENERIC)

# %s in logging (deferred evaluation)
logger.debug(LogTemplates.PROCESSING_ITEM, item_id)

# Type hints
def process(data: dict[str, Any]) -> Track | None:
    ...
```

---

## Questions?

- Check [MESSAGES_GUIDE.md](MESSAGES_GUIDE.md) for message constants
- Look at existing code for examples
- All code follows these patterns consistently

## License

See [LICENSE](LICENSE) file for details.
