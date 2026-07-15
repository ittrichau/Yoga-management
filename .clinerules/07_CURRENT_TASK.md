---
name: Current Task
alwaysApply: true
---

# Current Task

## Status Snapshot

- Last updated: 2026-07-15
- Current focus: UI polish, branding, confirmation dialogs for destructive actions, validation, search/filter, and backlog refinement.
- App status: Full core system completed; login page branding layout has been tightened while shared browser/navbar branding remains Bảo Ngọc.

## Active Task

- Task: None.
- Next recommended task: Verify login page layout locally across desktop/mobile heights, then verify shared branding across select-location, navbar, drawer, and browser tab/favicon.

## Recently Completed

- Adjusted `/login` branding layout: removed the extra `Fitness and yoga Bảo Ngọc` title under the logo, centered logo/subtitle reliably, reduced card padding, moved the auth card upward, and switched login shell sizing to `100dvh` to reduce unnecessary vertical scroll.
- Updated browser title to `Fitness and yoga Bảo Ngọc`, set favicon to `/static/bao_ngoc_logo.png`, and replaced shared login/navbar/drawer branding with the Bảo Ngọc logo and name.
- Audited delete/remove/deactivate flows and added confirmation dialogs before destructive UI actions: drink/ingredient/product/package template deactivation, user/location status changes, cart item removal on `/sales`, and package upgrade old-package deactivation.
- Updated user creation so adding a new user no longer requires manually selecting cơ sở; when left blank, the account is automatically assigned to all active locations for rotating teachers across both locations.

- Updated user creation so new users can be saved without manually selecting a cơ sở; when left blank, the account is automatically assigned to all active locations, matching rotating-teacher workflow.
- Tightened global page top spacing again by reducing `.page-container` top padding and the `/sales` page-specific top padding so pages sit closer to the navbar.
- Redesigned `/sales` transaction flow into a cart checkout: staff can add multiple drinks/products with quantities, see totals, remove cart rows, and checkout all items in one action while keeping transaction rows, stock/package updates, and audit log.
- Removed/rerouted redundant `/sales` explanatory notes, including the long customer audit-trace hint and product-sale instruction text.
- Reduced global page top spacing by lowering `.page-container` top padding for all pages while preserving mobile bottom-nav spacing.
- Clarified `/sales` product sale UI: fixed tab construction, renamed product tab to `Bán sản phẩm`, moved package payment inside the drink tab, and added clearer product sale instructions.
- Tightened `/sales` UI layout: reduced top whitespace, moved payment into a side card, made the retail product tab more explicit, and compacted the today transaction table to reduce horizontal scrolling.
- Redesigned `/sales` page into a clearer POS flow: customer selection, item tabs, product search/type filter, product preview, payment card, and today transaction table with generic item labels.
- Fixed `/sales` product sale flow to record `product_stock_adjustments` when retail products such as clothing/mats/accessories are sold from the UI.
- Fixed `/sales` navbar render order to match the shared drawer-safe layout.
- Fixed `/dashboard` NiceGUI crash `LeftDrawer inside Row` by moving shared `ui.left_drawer()` creation out of the header row and keeping dashboard navbar rendering before page content.
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

1. Verify login page layout locally across desktop/mobile heights: logo/subtitle centered, no extra brand title under logo, auth card sits higher, and no unnecessary vertical scroll.
2. Verify destructive-action confirmation dialogs locally across `/drinks`, `/ingredients`, `/products`, `/package-templates`, `/users`, `/locations`, `/sales`, and `/packages/upgrade`.
3. Verify all main pages for the tightened top spacing, deploy local fixes, then verify `/dashboard`, `/drinks`, and `/sales` on production.
4. Verify `/sales` cart checkout flow locally with multi-product, drink, package-drink, stock deduction, and today's transactions.
5. Improve `/packages` search/filter if still missing.
6. Improve validation UI and Vietnamese success/error messages.
7. Consider seeding a `Khách vãng lai` customer per location for walk-in retail sales while preserving audit traceability.
8. Enrich seed data.
9. Consider adding retail products into `package_items` for combo business cases.
10. Add personal password change flow.
11. Later backlog: dashboard charts, barcode/QR, print receipt, EN/VN, dark mode, optional sidebar.

## Verification Log

- 2026-07-15: Ran `python -m py_compile auth.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the login layout update.
- 2026-07-14: Ran `python -m py_compile main.py auth.py && git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the branding/title/logo update.
- 2026-07-14: Ran `python -m py_compile auth.py drink.py ingredient.py product.py package_template.py transaction.py package_upgrade.py package.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for destructive-action confirmation dialog updates.
- 2026-07-14: Ran `python -m py_compile auth.py database.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for optional/default-all-location user creation and role label updates.
- 2026-07-14: Ran `python -m py_compile auth.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the optional user-location assignment change.
- 2026-07-14: Ran `git diff --check`.
  - Command completed successfully with no whitespace errors reported for the CSS top-spacing changes.
- 2026-07-14: Ran `python -m py_compile transaction.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the `/sales` cart checkout changes.
- 2026-07-14: Ran `python -m py_compile transaction.py`.
  - Command completed successfully with no syntax errors reported for the `/sales` cart checkout changes.
- 2026-07-14: Ran `python -m py_compile transaction.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the global top spacing and `/sales` product tab UI changes.
- 2026-07-14: Ran `python -m py_compile transaction.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported.
- 2026-07-13: Ran `python -m py_compile transaction.py`.
  - Command completed successfully with no syntax errors reported.
- 2026-07-13: Ran `python -m py_compile auth.py dashboard.py`.
  - Command completed successfully with no syntax errors reported.
- 2026-07-13: Ran `python -c "from pathlib import Path; t=Path('auth.py').read_text(encoding='utf-8').splitlines(); print([i+1 for i,l in enumerate(t) if 'ui.left_drawer' in l]); print([i+1 for i,l in enumerate(t) if 'with ui.header' in l])"`.
  - Confirmed `ui.left_drawer` is now created before `ui.header` in `render_navbar()`.
- 2026-07-13: Ran `git --no-pager diff -- auth.py dashboard.py; git diff --check`.
  - Confirmed task diff moves `ui.left_drawer()` out of the nested header row in `auth.py`; no whitespace errors reported.
- 2026-07-13: Ran `python -m py_compile dashboard.py auth.py checkin.py customer.py drink.py ingredient.py package.py package_template.py package_upgrade.py product.py pt.py transaction.py`.
  - Command completed successfully with no syntax errors reported.
- 2026-07-13: Ran `git diff -- dashboard.py checkin.py customer.py drink.py ingredient.py package.py package_template.py package_upgrade.py product.py pt.py transaction.py`.
  - Confirmed earlier task diff only changes `dashboard.py` render order: `render_navbar()` now runs before `render()`.
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
