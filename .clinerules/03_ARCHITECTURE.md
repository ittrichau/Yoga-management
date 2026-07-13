---
name: Architecture
alwaysApply: true
---

# Architecture

## Project Structure

```text
Yoga_management_git/
├── main.py              # App startup, route registration, ui.run
├── database.py          # SQLite/PostgreSQL connection, schema, seed, migration
├── settings.py          # Config constants
├── auth.py              # Auth, users, locations, navbar
├── customer.py          # Customer CRUD, check-in API, birthday alerts
├── checkin.py           # Check-in session management
├── drink.py             # Drink management UI + API
├── ingredient.py        # Ingredient/inventory management UI + API
├── package.py           # Customer package management UI + API
├── package_template.py  # Package template management
├── package_upgrade.py   # Package upgrade workflow
├── product.py           # Retail product management
├── transaction.py       # Sales transactions
├── pt.py                # PT sessions & rate cards
├── audit.py             # Audit log viewer
├── dashboard.py         # Dashboard stats, fraud alerts, export CSV
├── static/style.css     # Custom CSS
└── data/                # SQLite database storage, git-ignored
```

## Tech Stack

- Python 3.13+
- FastAPI
- NiceGUI / Quasar
- SQLite local / PostgreSQL production
- PyJWT
- bcrypt
- Pydantic

## Architecture Style

- Simple modular monolith.
- Business logic lives in domain files.
- No controller/service/repository/dto layers unless explicitly requested.
- Routes, APIs, and UI are often colocated in the same domain file.
- Prefer small targeted edits over broad refactors.

## Authentication Flow

```text
User → Login → JWT token → app.storage.user
                         ↓
                  Select location
                         ↓
       Page checks token + current location
                         ↓
        Redirect to /login or /select-location if missing
```

Current location is stored in:

- `app.storage.user["location_id"]`
- `app.storage.user["location_name"]`

## Database Overview

Core tables:

- `locations`
- `users`
- `user_locations`
- `customers`
- `drinks`
- `ingredients`
- `drink_recipes`
- `products`
- `product_stock_adjustments`
- `packages`
- `package_items`
- `package_templates`
- `package_sessions`
- `transactions`
- `inventory_adjustments`
- `pt_rates`
- `pt_sessions`
- `audit_logs`

Design rules:

- Multi-location data uses `location_id`.
- Important data uses soft delete with `is_active=0` where supported.
- Important actions are recorded in `audit_logs`.

## Role Hierarchy

```text
STAFF(1) < MANAGER(2) < OWNER(3)
```

## Key UI Routes

| Route                | Chức năng                   | Quyền    |
| -------------------- | --------------------------- | -------- |
| `/login`             | Đăng nhập                   | Public   |
| `/select-location`   | Chọn cơ sở làm việc         | Any      |
| `/dashboard`         | Bảng điều khiển             | Any      |
| `/customers`         | Quản lý khách hàng          | Any      |
| `/checkin`           | Check-in buổi tập           | Any      |
| `/sales`             | Bán hàng                    | Any      |
| `/drinks`            | Quản lý đồ uống             | Any      |
| `/ingredients`       | Quản lý nguyên liệu/tồn kho | Any      |
| `/products`          | Quản lý sản phẩm            | Any      |
| `/packages`          | Gói trả trước               | Any      |
| `/package-templates` | Mẫu gói                     | MANAGER+ |
| `/packages/upgrade`  | Nâng cấp gói                | MANAGER+ |
| `/pt`                | Ghi nhận PT                 | Any      |
| `/audit`             | Nhật ký hệ thống            | MANAGER+ |
| `/users`             | Quản lý người dùng          | OWNER    |
| `/locations`         | Quản lý cơ sở               | OWNER    |

## Key API Groups

- `/api/login`, `/api/me`, `/api/my-locations`
- `/api/users`, `/api/locations`
- `/api/customers`
- `/api/checkin/sessions`
- `/api/drinks`
- `/api/ingredients`
- `/api/products`
- `/api/packages`
- `/api/package-templates`
- `/api/transactions`
- `/api/pt-rates`, `/api/pt-sessions`
- `/api/audit/logs`
- `/api/dashboard/*`

Check permissions and location scoping when modifying any API.

## Key Design Decisions

- Multi-location access through `locations` and `user_locations`.
- User must select a location before working with operational data.
- Soft delete is preferred over hard delete for business data.
- Audit trail links action → entity → user → location.
- Customer codes are generated per location using `HVxxxxxx`.
- SQLite is used locally when `DATABASE_URL` is absent.
- PostgreSQL is used in production when `DATABASE_URL` exists.
