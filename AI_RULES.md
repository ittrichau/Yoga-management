---
name: AI Rules
alwaysApply: true
---

# AI Rules

## Goal

Build and maintain a Yoga/Gym Management System optimized for simple, safe AI-assisted development.

## Tech Stack

- Python 3.13+
- FastAPI
- NiceGUI / Quasar
- SQLite local / PostgreSQL production
- bcrypt
- PyJWT

## General Rules

1. Do not over-engineer.
2. Do not use Clean Architecture, DDD, or Microservices for this project.
3. Do not create unnecessary files or abstraction layers.
4. Do not refactor unrelated code.
5. Do not modify files outside the current task scope.
6. Prefer direct edits in the existing business-domain files.
7. Keep UI Vietnamese unless the task explicitly asks otherwise.
8. Preserve multi-location scoping and role-based permissions.
9. Important business actions must keep or add audit logging.
10. Important data should use soft delete where the project already follows that pattern.

## File Rules

Do NOT create these layers unless explicitly requested:

- controllers
- services
- repositories
- dto
- interfaces
- mappers
- validators

Use existing business-domain files instead, for example:

- `customer.py`
- `drink.py`
- `ingredient.py`
- `product.py`
- `transaction.py`
- `package.py`
- `audit.py`
- `auth.py`

## File Size Rules

- Prefer small, focused changes.
- Large files are allowed because this project intentionally keeps logic inside domain files.
- Only split a file when the task explicitly requires it or when a small extraction clearly reduces risk.
- Do not perform broad file-splitting refactors during bug-fix or UI-polish tasks.

## Current Task Auto-Update Rule

After every implementation task that changes code, configuration, documentation, or rules:

1. Update `.clinerules/07_CURRENT_TASK.md`.
2. Move completed work into `Recently Completed`.
3. Set `Active Task` to the next task or `None`.
4. Update `Pending / Next` if priorities changed.
5. Record verification performed, for example `python -m py_compile ...`.
6. Keep `07_CURRENT_TASK.md` concise; do not duplicate architecture or full product context.

If the task changes backlog, roadmap, priorities, or acceptance criteria, also update `.clinerules/01_GOAL.md`.

## Response Rules

For every completed task, final response should include:

1. Implementation Plan
2. Files Modified
3. Changes Made
4. Verification
5. Current Task Updated
6. Next Suggested Task

## Terminal Rules

- Never run long-lived commands.
- Never execute `uvicorn`.
- Never execute `npm run dev`.
- Never execute `npm start`.
- Never keep a server running.
- Safe verification commands are allowed when useful, for example:
  - `python -m py_compile ...`
  - project tests
  - `git diff --check`
  - `git status --short`
- Do not install packages or run destructive commands unless explicitly needed and approved.
