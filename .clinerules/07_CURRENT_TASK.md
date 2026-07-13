---
name: Current Task
alwaysApply: true
---

# Current Task

## Status Snapshot

- Last updated: 2026-07-13
- Current focus: UI polish, popup close buttons, validation, search/filter, and backlog refinement.
- App status: Full core system completed; drink page production schema mismatch has been fixed.

## Active Task

- Task: None.
- Next recommended task: Deploy the drink schema fix, then verify `/drinks` on production.

## Recently Completed

- Fixed `/drinks` production error `OperationalError: no such column: price` by using `drinks.price_per_serving` consistently and adding safe schema migration/backfill for drink fields.
- Cleaned up rule files and enforced automatic `.clinerules/07_CURRENT_TASK.md` updates after implementation tasks.
- Completed Phase 2 Full System: auth, customer, check-in, sales, drinks, ingredients, products, packages, PT, audit, dashboard, users, locations.
- Completed customer code auto-generation per location: `HV000001`, `HV000002`, ...
- Completed drink page fixes: load, add/edit, soft delete, permissions, popup close.
- Completed ingredient/inventory fixes: adjust, history, OWNER permission, audit log, popup close.
- Completed audit log fixes: query/filter/user/time/detail popup.
- Completed package management, package templates, package upgrade flow.
- Completed Responsive Mobile UI Phase 3: mobile navbar, responsive CSS, full-width dialogs, table scroll, dashboard grid, form/button polish.

## Pending / Next

1. Deploy the drink schema fix, then verify `/drinks` on production.
2. Check/add popup close icon for remaining files:
   - `package.py`
   - `auth.py`
   - `transaction.py`
   - `product.py`
3. Improve `/packages` search/filter if still missing.
4. Improve validation UI and Vietnamese success/error messages.
5. Enrich seed data.
6. Consider adding retail products into `package_items` for combo business cases.
7. Add personal password change flow.
8. Later backlog: dashboard charts, barcode/QR, print receipt, EN/VN, dark mode, optional sidebar.

## Verification Log

- 2026-07-13: Ran `python -m py_compile drink.py database.py`.
  - Command completed successfully with no syntax errors reported.
- 2026-07-13: Ran `git diff --check; git status --short`.
  - `git diff --check` reported line-ending warnings only; no whitespace errors reported.
  - Git reported task-modified files: `database.py`, `drink.py`, `.clinerules/07_CURRENT_TASK.md`.
  - Git also showed pre-existing/non-task modified files: rule files, `AI_RULES.md`, `audit.py`, `auth.py`, `ingredient.py`, `package_template.py`, `static/style.css`.

## Auto-update Rule

After every implementation task, update this file:

- Move completed work into `Recently Completed`.
- Update `Active Task` to the next task or `None`.
- Update `Pending / Next` when priorities change.
- Record verification command/result in `Verification Log`.
- Keep this file concise; do not duplicate architecture, full route lists, or full product context.
