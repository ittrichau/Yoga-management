---
name: Current Task
alwaysApply: true
---

# Current Task

## Status Snapshot

- Last updated: 2026-07-22
- Current focus: Visually verify the final compact `/customers` desktop-table/mobile-card layout locally.
- App status: Full core system completed; the customer list implementation passed static verification, with browser verification still pending.

## Active Task

- Task: Verify the final `/customers` layout after removing STT/the separate action column and moving permission-aware edit/delete actions beside the customer name.
- Next recommended task: Verify `/customers` visually across desktop/mobile and STAFF/MANAGER/OWNER, including search, add/edit dialogs, birth-date picker, and soft-delete confirmation.

## Recently Completed

- Removed the previous customer-page CSS and replaced it with a new compact responsive layout based on the supplied reference: desktop table, mobile label-value cards, search toolbar, add button, and compact edit/delete actions.
- Rebuilt the `/customers` list markup with STT, customer code, name, phone, birth date, notes, and permission-aware actions while preserving search, location scoping, soft delete, dialogs, and audit behavior.
- Redesigned `/customers` with a structured page header, location/count summary, clearer search actions, avatar initials, customer-code badges, labeled contact information, safer compact delete action, and responsive mobile styling.
- Fixed the `/customers` add/edit birth-date picker by anchoring the date menu to its input and making both the field and calendar icon open the popup reliably.
- Redesigned `/customers`: replaced the table with responsive customer cards, displayed list sequence numbers instead of customer codes, moved search/search button/add button above the list, removed duplicate actions, and added empty states.
- Added OWNER/ADMIN customer soft-delete with a confirmation dialog, `location_id` scoping, preserved historical data, and audit logging.
- Split logo usage in `auth.py` so login and the shared top/header use `static/bao_ngoc_logo.png`, while only the drawer/menu uses `static/bao_ngoc_logo_small.png`.
- Enlarged the centered Bảo Ngọc header logo with responsive CSS width rules for desktop/mobile while keeping the existing 56px header height and centered alignment.
- Removed the large blank top gap below the shared header across pages by re-tuning NiceGUI/Quasar page-container/header spacing and testing the shared layout, including the `/sales` page-specific container.
- Renamed the dashboard UI from `Bảng điều khiển` to `Trang chính`, updated drawer/mobile nav labels, moved the top menu button to the left, and centered the Bảo Ngọc logo in the header while keeping the existing header height.
- Removed the `Fitness and yoga Bảo Ngọc` text from the left drawer brand area and widened the shared logo presentation in the header and drawer.
- Tightened `/login` CSS again: scoped the login body/page containers to `100dvh` with hidden overflow, reduced shell padding, and centered the logo/header via flex and Quasar image object-position rules to address residual scroll and logo/subtitle misalignment.
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

1. Verify all main pages locally across desktop/mobile: content should sit close to the header with no large blank area and no header/content overlap.
2. Verify shared header locally across desktop/mobile: left menu button, centered wider logo, unchanged header height, and right-side location/user/actions not overlapping.
3. Verify login page layout locally across desktop/mobile heights: logo/subtitle centered, no extra brand title under logo, auth card sits higher, and no unnecessary vertical scroll.
4. Verify destructive-action confirmation dialogs locally across `/drinks`, `/ingredients`, `/products`, `/package-templates`, `/users`, `/locations`, `/sales`, and `/packages/upgrade`.
5. Verify `/sales` cart checkout flow locally with multi-product, drink, package-drink, stock deduction, and today's transactions.
6. Improve `/packages` search/filter if still missing.
7. Improve validation UI and Vietnamese success/error messages.
8. Consider seeding a `Khách vãng lai` customer per location for walk-in retail sales while preserving audit traceability.
9. Enrich seed data.
10. Consider adding retail products into `package_items` for combo business cases.
11. Add personal password change flow.
12. Later backlog: dashboard charts, barcode/QR, print receipt, EN/VN, dark mode, optional sidebar.

## Verification Log

- 2026-07-22: Rechecked the interrupted `/customers` task and confirmed the pending changes remain limited to `customer.py` and `static/style.css`.
  - Reviewed the final five-column desktop markup, mobile label-value card CSS, permission-aware actions, search/empty states, add/edit close buttons, birth-date picker, location scoping, soft delete, and audit logging.
  - `python -m py_compile customer.py main.py auth.py` and `git diff --check` completed successfully.
  - A runtime import check could not complete because the active Python environment is missing the installed `jwt` module; browser verification remains pending and no long-lived server was started per project rules.
- 2026-07-22: Ran `python -m py_compile customer.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git --no-pager diff --stat -- customer.py static/style.css .clinerules/07_CURRENT_TASK.md`.
  - Command completed successfully with no Python syntax or whitespace errors reported for the new customer desktop-table/mobile-card layout.
- 2026-07-22: Ran `python -m py_compile customer.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git --no-pager diff --stat -- customer.py static/style.css`.
  - Command completed successfully with no syntax or whitespace errors reported for the customer page visual redesign.
- 2026-07-22: Ran `python -m py_compile customer.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git --no-pager diff -- customer.py`.
  - Command completed successfully with no syntax or whitespace errors reported for the customer birth-date popup fix.
- 2026-07-22: Ran `python -m py_compile customer.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the customer page card redesign and soft-delete update.
- 2026-07-15: Switched the shared navigation/sidebar header brand image in `auth.py` to `static/bao_ngoc_logo_small.png` only, leaving other branding usages unchanged.
- 2026-07-15: Enlarged the shared centered header logo in `static/style.css` using responsive width rules for normal, mobile, and very small phone breakpoints.
- 2026-07-15: Updated global CSS spacing to remove the large blank top gap below the shared header across all pages.
- 2026-07-15: Ran `python -m py_compile auth.py dashboard.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the global top spacing update.
- 2026-07-15: Ran `python -m py_compile auth.py dashboard.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the dashboard/header rename and layout update.
- 2026-07-15: Ran `git diff --check`.
  - Command completed successfully with no whitespace errors reported for the login CSS centering/scroll update.
- 2026-07-15: Updated shared branding so the drawer no longer shows `Fitness and yoga Bảo Ngọc` and the logo is wider in the header/drawer.
- 2026-07-15: Ran `python -m py_compile auth.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git diff --check`.
  - Command completed successfully with no syntax or whitespace errors reported for the header/drawer logo polish.
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
