# AGENTS.md — Development Rules for AI Coding Agents

This file is read by Codex and other AI coding agents. Follow all rules here without needing to be reminded.

> Indonesian-language bot project. Code must be in English. User-facing messages may be in Indonesian.

---

## Project Summary

Telegram bot that monitors and controls a server using natural language. AI model (Qwen via Ollama) runs locally on the VPS — no data leaves the machine.

**Stack:** Python 3.13 · python-telegram-bot · Ollama · Docker · GitHub Actions

---

## Architecture: Hexagonal (Ports & Adapters)

This project follows **Hexagonal Architecture**. The domain must have zero dependencies on frameworks, external libraries, or infrastructure.

### Layer Rules (strictly enforced)

| Layer | Location | Rule |
|---|---|---|
| Domain | `app/domain/` | No external imports. Pure Python only. |
| Ports | `app/ports/` | `typing.Protocol` classes only. No implementation. |
| Adapters | `app/adapters/` | One adapter per external dependency. Only imported from `main.py`. |
| Actions | `app/actions/` | One class per action. No intent logic here. |
| Config | `app/config.py` | All env vars in one place. Read once at startup. |
| Entrypoint | `app/main.py` | Dependency injection wiring only. |

### Dependency Direction

```
main.py → adapters → ports ← domain
main.py → actions → domain
```

Adapters depend on ports. Domain never depends on adapters. Violating this is a breaking architecture error.

---

## Mandatory Code Standards

### Type Annotations

Every function signature must have full type annotations. No exceptions.

```python
# Correct
def classify(self, text: str) -> Intent: ...

# Wrong — missing types
def classify(self, text): ...
```

### Data Classes

Use `@dataclass(frozen=True)` for value objects in the domain.

```python
@dataclass(frozen=True)
class Intent:
    action: str
    confidence: float = 1.0
```

### Exceptions

Define specific exception classes. Never raise bare `Exception`.

```python
# Correct
class AIProviderUnavailableError(Exception): ...
raise AIProviderUnavailableError("Ollama not reachable")

# Wrong
raise Exception("AI not available")
```

### Subprocess

Never use `shell=True`. Always pass a list of arguments.

```python
# Correct
subprocess.run(["git", "status", "--short"], ...)

# Wrong — shell injection risk
subprocess.run("git status", shell=True, ...)
```

### Comments

Write comments only for **why**, never for **what**. If the code needs a comment to explain what it does, rename or restructure instead.

### Naming

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Adapters: suffix `Adapter` (e.g. `OllamaAdapter`)
- Actions: suffix `Action` (e.g. `DiskAction`)
- Exceptions: suffix `Error` (e.g. `CommandNotAllowedError`)

---

## Adding a New Action

Every new action must implement the `Action` protocol:

```python
# app/actions/<domain>.py
from dataclasses import dataclass
from app.domain.entities import ActionResult

@dataclass
class NewAction:
    def execute(self, params: dict | None = None) -> ActionResult:
        ...

    @property
    def name(self) -> str:
        return "action_name"   # must match key in intent classifier

    @property
    def description(self) -> str:
        return "One sentence for the AI intent prompt."
```

Register it in `main.py` via `ActionRegistry`. Never hardcode action names elsewhere.

---

## Testing Requirements

Every new feature or bug fix must include tests.

```
tests/
├── domain/      — no mocks, pure unit tests
├── actions/     — mock system calls
└── adapters/    — mock HTTP / subprocess
```

Test naming: `test_<condition>_<expected_result>`

Run before every commit:
```bash
pytest tests/ -v
ruff check app/
mypy app/
```

---

## Git Workflow & PR Conventions

### Branch Naming

Format: `<type>/<short-description-with-dashes>`

| Type | When to use |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `refactor/` | Code restructuring without behaviour change |
| `chore/` | Maintenance: deps, config, CI |
| `docs/` | Documentation only |
| `test/` | Adding or fixing tests |
| `hotfix/` | Urgent production fix |

Valid examples:
```
feat/docker-stats-action
fix/ollama-timeout-handling
refactor/split-intent-classifier
```

Invalid — will be rejected by CI:
```
update-bot          # no type prefix
feature-docker      # must be feat/, not feature-
Fix/something       # uppercase not allowed
```

### PR Title Format (Conventional Commits)

```
<type>(<optional-scope>): <short description in lowercase>
```

- scope is optional — use the module name being changed
- description in lowercase, no trailing period
- max 72 characters

Valid:
```
feat: add docker stats monitoring action
fix: handle ollama timeout gracefully
refactor(domain): extract intent classifier to separate module
chore: upgrade python-telegram-bot to 22.8
test: unit tests for ServerStatusAction
```

Invalid — will be rejected by CI:
```
Update bot.py                      # no type prefix
feat: Add Docker Stats Action.     # uppercase and trailing period
fixed the bug in ollama adapter    # no type prefix
```

### Merge Rules

- Never push directly to `main` — all changes must go through a PR
- PR must pass all automated checks (branch name, PR title, lint, type-check, tests)
- One PR = one concern — do not mix feat and refactor in the same PR

---

## Hard Rules

1. Do not add features not explicitly requested
2. Do not modify architecture without explicit approval
3. Do not hardcode any credentials or secrets — use `config.py` which reads from env
4. Do not import adapters from domain layer
5. Do not create new files when extending an existing one is sufficient
6. Do not use `eval`, `exec`, or dynamic attribute setting
7. Do not catch bare `Exception` — catch specific exception types
