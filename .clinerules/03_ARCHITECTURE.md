---
name: Architecture
alwaysApply: true
---

# Architecture

## Project Structure

```
Yoga_management_git/
├── AI_RULES.md
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── main.py              # App startup, route registration, navbar
├── database.py          # SQLite/PostgreSQL connection, schema, seed defaults, migration
├── settings.py          # Config constants (DB_PATH, SECRET_KEY, STORAGE_SECRET, etc.)
├── auth.py              # Authentication (JWT, bcrypt), authorization, navbar, login, users & locations UI
├── customer.py          # Customer CRUD, check-in API, birthday alerts
├── checkin.py           # Check-in session management with package integration
├── drink.py             # Drink management UI + API (formerly product.py nutrition)
├── ingredient.py        # Ingredient/inventory management UI + API (formerly inventory.py)
├── package.py           # Customer package management UI + API
├── package_template.py  # Package template management (BASIC, FAT_LOSS, COMBO)
├── package_upgrade.py   # Package upgrade workflow
├── product.py           # Product management (mat, clothing, accessory, other) - retail items
├── transaction.py       # Sales transaction creation (drinks, products, package items)
├── pt.py                # Personal trainer sessions & rate cards
├── audit.py             # Audit log viewer
├── dashboard.py         # Dashboard stats, fraud alerts, stock overview, export CSV
├── static/
│   └── style.css        # Custom CSS
└── data/                # SQLite database storage (git-ignored)
    └── gym_nutrition.db
```

## Responsibilities

| File                    | Chức năng                                                                           |
| ----------------------- | ----------------------------------------------------------------------------------- |
| **main.py**             | Khởi động app, đăng ký 14 router, serve static files, ui.run                        |
| **database.py**         | Kết nối SQLite/PostgreSQL, tạo schema 18 tables, seed data, migration               |
| **settings.py**         | Hằng số cấu hình (DB_PATH, DATABASE_URL, SECRET_KEY, SUPER_USER, etc.)              |
| **auth.py**             | JWT + bcrypt auth, phân quyền, navbar, login, users CRUD, locations CRUD            |
| **customer.py**         | CRUD khách hàng (auto-gen mã HVxxxxxx), check-in API, birthday alerts               |
| **checkin.py**          | Check-in buổi tập, gắn với gói tập (packages/package_sessions)                      |
| **drink.py**            | CRUD đồ uống (MANAGER+), soft delete (OWNER), công thức nguyên liệu                 |
| **ingredient.py**       | CRUD nguyên liệu (MANAGER+), điều chỉnh tồn kho (OWNER), lịch sử adjust             |
| **package.py**          | Tạo & quản lý gói trả trước cho khách hàng, theo dõi buổi còn lại                   |
| **package_template.py** | Quản lý mẫu gói (BASIC/FAT_LOSS/COMBO), thời hạn, buổi, ly, giá                     |
| **package_upgrade.py**  | Nâng cấp gói cho khách hàng, tính tiền bù                                           |
| **product.py**          | CRUD sản phẩm bán lẻ (thảm, áo, phụ kiện), điều chỉnh tồn kho sản phẩm              |
| **transaction.py**      | Tạo giao dịch bán hàng (đồ uống, sản phẩm, gói), tính tiền                          |
| **pt.py**               | Quản lý PT sessions, PT rate cards (AT_GYM/OUTSIDE, PER_HOUR/PER_SESSION/PER_MONTH) |
| **audit.py**            | Xem nhật ký kiểm toán, lọc theo entity/action/user (MANAGER+)                       |
| **dashboard.py**        | Thống kê tổng quan, cảnh báo fraud, tồn kho thấp, sinh nhật sắp tới, export CSV     |

## Tech Stack

- **Python 3.13+**
- **FastAPI** - REST API backend
- **NiceGUI** - Giao diện UI (Quasar components)
- **SQLite** - Cơ sở dữ liệu local dev (WAL mode, foreign keys)
- **PostgreSQL** - Cơ sở dữ liệu production (Railway, psycopg2)
- **PyJWT** - JWT token authentication
- **bcrypt** - Mã hóa mật khẩu
- **Pydantic** - Data validation

## Authentication Flow

```
User → Login Form → bcrypt verify → JWT token → Lưu vào app.storage.user
                                                      ↓
                                            Chọn cơ sở (select-location)
                                                      ↓
                                            Mỗi page kiểm tra token + location_id
                                            Nếu không có → redirect /login hoặc /select-location
```

## Database Schema (18 tables)

### Core tables

- **locations**: id, name, address, is_active, created_at
- **users**: id, username, hashed_password, full_name, role (STAFF/MANAGER/OWNER), is_active, created_at, updated_at
- **user_locations**: user_id, location_id (PK composite - phân quyền đa cơ sở)

### Customer

- **customers**: id, location_id, code, full_name, phone, birth_date, notes, is_active, created_by, created_at, updated_at, current_package_id

### Drinks & Ingredients

- **drinks**: id, location_id, name, price (price_per_serving alias), description, recipe, is_active, created_by, created_at, updated_at
- **ingredients**: id, location_id, name, unit (muỗng/nắp/gói), current_stock, min_stock, is_active, created_by, created_at, updated_at
- **drink_recipes**: id, drink_id, ingredient_id, quantity_per_serving

### Products (retail)

- **products**: id, location_id, name, product_type (mat/clothing/accessory/other), price, sale_percent, current_stock, min_stock, is_active, created_by, created_at, updated_at
- **product_stock_adjustments**: id, location_id, product_id, adjustment_type, quantity, reason, created_by, created_at

### Packages

- **packages**: id, location_id, customer_id, package_template_id, name, total_amount, duration_days, start_date, end_date, total_sessions, remaining_sessions, is_active, created_by, created_at, updated_at
- **package_items**: id, package_id, drink_id, product_id, total_servings, remaining_servings, quantity
- **package_templates**: id, location_id, name, package_type (BASIC/FAT_LOSS/COMBO), description, duration_days, total_sessions, total_drinks, total_amount, is_active, created_by, created_at, updated_at
- **package_sessions**: id, package_id, checkin_date, checkin_time, transaction_id, created_by, created_at

### Transactions

- **transactions**: id, location_id, customer_id, drink_id, product_id, package_item_id, servings, quantity, amount, session_checkin, notes, created_by, created_at

### Inventory (ingredients)

- **inventory_adjustments**: id, location_id, ingredient_id, adjustment_type (add/remove/count_correct), quantity, reason, created_by, created_at

### PT

- **pt_rates**: id, location_id, name, location_type (AT_GYM/OUTSIDE), rate_type (PER_HOUR/PER_SESSION/PER_MONTH), price, is_active, created_at
- **pt_sessions**: id, location_id, customer_id, trainer_id, pt_rate_id, session_date, duration_hours, include_nutrition, drink_id, package_item_id, pt_amount, drink_amount, total_amount, notes, created_by, created_at

### Audit

- **audit_logs**: id, location_id, user_id, action, entity_type, entity_id, details, ip_address, created_at

## Role Hierarchy

```
STAFF(1) < MANAGER(2) < OWNER(3)
```

## Phân quyền chi tiết

### STAFF (Nhân viên)

- Xem dashboard, khách hàng, đồ uống, nguyên liệu, sản phẩm
- Tạo giao dịch bán hàng
- Check-in khách hàng
- Tạo khách hàng mới
- **Không** sửa/xóa giao dịch
- **Không** điều chỉnh tồn kho
- **Không** quản lý đồ uống, nguyên liệu, sản phẩm
- **Không** xem audit log

### MANAGER (Quản lý)

- Tất cả quyền STAFF
- Tạo/sửa đồ uống, nguyên liệu, sản phẩm
- Sửa thông tin khách hàng
- Xem audit log, fraud alerts
- Quản lý mẫu gói, nâng cấp gói
- **Không** điều chỉnh tồn kho nguyên liệu
- **Không** quản lý người dùng, cơ sở
- **Không** vô hiệu hóa đồ uống (chỉ OWNER)

### OWNER (Chủ sở hữu)

- Tất cả quyền MANAGER
- Điều chỉnh tồn kho nguyên liệu & sản phẩm
- Vô hiệu hóa đồ uống, nguyên liệu, sản phẩm
- Quản lý người dùng (CRUD, phân quyền, gán cơ sở)
- Quản lý cơ sở (CRUD, vô hiệu hóa)

## API Endpoints

| Method | Endpoint                               | Quyền    | File                |
| ------ | -------------------------------------- | -------- | ------------------- |
| POST   | /api/login                             | Public   | auth.py             |
| GET    | /api/me                                | Any      | auth.py             |
| GET    | /api/my-locations                      | Any      | auth.py             |
| GET    | /api/users                             | OWNER    | auth.py             |
| POST   | /api/users                             | OWNER    | auth.py             |
| PUT    | /api/users/{id}                        | OWNER    | auth.py             |
| PUT    | /api/users/{id}/deactivate             | OWNER    | auth.py             |
| GET    | /api/locations                         | OWNER    | auth.py             |
| POST   | /api/locations                         | OWNER    | auth.py             |
| PUT    | /api/locations/{id}                    | OWNER    | auth.py             |
| GET    | /api/customers                         | Any      | customer.py         |
| GET    | /api/customers/next-code               | Any      | customer.py         |
| GET    | /api/customers/{id}                    | Any      | customer.py         |
| POST   | /api/customers                         | Any      | customer.py         |
| PUT    | /api/customers/{id}                    | MANAGER+ | customer.py         |
| POST   | /api/customers/{id}/checkin            | Any      | customer.py         |
| GET    | /api/customers/upcoming-birthdays      | Any      | customer.py         |
| GET    | /api/drinks                            | Any      | drink.py            |
| POST   | /api/drinks                            | MANAGER+ | drink.py            |
| PUT    | /api/drinks/{id}                       | MANAGER+ | drink.py            |
| DELETE | /api/drinks/{id}                       | OWNER    | drink.py            |
| GET    | /api/ingredients                       | Any      | ingredient.py       |
| POST   | /api/ingredients                       | MANAGER+ | ingredient.py       |
| PUT    | /api/ingredients/{id}                  | MANAGER+ | ingredient.py       |
| DELETE | /api/ingredients/{id}                  | OWNER    | ingredient.py       |
| POST   | /api/ingredients/{id}/adjust           | OWNER    | ingredient.py       |
| GET    | /api/ingredients/{id}/adjustments      | Any      | ingredient.py       |
| GET    | /api/products                          | Any      | product.py          |
| POST   | /api/products                          | MANAGER+ | product.py          |
| PUT    | /api/products/{id}                     | MANAGER+ | product.py          |
| DELETE | /api/products/{id}                     | OWNER    | product.py          |
| POST   | /api/products/{id}/adjust              | OWNER    | product.py          |
| GET    | /api/packages                          | Any      | package.py          |
| POST   | /api/packages                          | Any      | package.py          |
| GET    | /api/package-templates                 | MANAGER+ | package_template.py |
| POST   | /api/package-templates                 | MANAGER+ | package_template.py |
| PUT    | /api/package-templates/{id}            | MANAGER+ | package_template.py |
| POST   | /api/packages/upgrade                  | MANAGER+ | package_upgrade.py  |
| GET    | /api/transactions                      | Any      | transaction.py      |
| POST   | /api/transactions                      | Any      | transaction.py      |
| GET    | /api/pt-rates                          | Any      | pt.py               |
| POST   | /api/pt-rates                          | MANAGER+ | pt.py               |
| GET    | /api/pt-sessions                       | Any      | pt.py               |
| POST   | /api/pt-sessions                       | Any      | pt.py               |
| GET    | /api/audit/logs                        | MANAGER+ | audit.py            |
| GET    | /api/dashboard/stats                   | Any      | dashboard.py        |
| GET    | /api/dashboard/fraud-alerts            | MANAGER+ | dashboard.py        |
| GET    | /api/dashboard/transactions/export-csv | Any      | dashboard.py        |
| GET    | /api/checkin/sessions                  | Any      | checkin.py          |
| POST   | /api/checkin/sessions                  | Any      | checkin.py          |

## UI Routes

| Route                | Chức năng                   | Quyền    | File                |
| -------------------- | --------------------------- | -------- | ------------------- |
| `/login`             | Đăng nhập                   | Public   | auth.py             |
| `/select-location`   | Chọn cơ sở làm việc         | Any      | auth.py             |
| `/`                  | Redirect về dashboard       | Any      | main.py             |
| `/dashboard`         | Bảng điều khiển             | Any      | dashboard.py        |
| `/customers`         | Quản lý khách hàng          | Any      | customer.py         |
| `/checkin`           | Check-in buổi tập           | Any      | checkin.py          |
| `/sales`             | Bán hàng                    | Any      | transaction.py      |
| `/drinks`            | Quản lý đồ uống             | Any      | drink.py            |
| `/ingredients`       | Quản lý nguyên liệu/tồn kho | Any      | ingredient.py       |
| `/products`          | Quản lý sản phẩm            | Any      | product.py          |
| `/packages`          | Gói trả trước               | Any      | package.py          |
| `/package-templates` | Mẫu gói                     | MANAGER+ | package_template.py |
| `/packages/upgrade`  | Nâng cấp gói                | MANAGER+ | package_upgrade.py  |
| `/pt`                | Ghi nhận PT                 | Any      | pt.py               |
| `/audit`             | Nhật ký hệ thống            | MANAGER+ | audit.py            |
| `/users`             | Quản lý người dùng          | OWNER    | auth.py             |
| `/locations`         | Quản lý cơ sở               | OWNER    | auth.py             |

## Business Flow

1. **Login** → `/login` → JWT token → store in app.storage.user
2. **Select Location** → `/select-location` → pick location → store location_id + location_name
3. **Dashboard** → `/dashboard` → overview of current location
4. **Daily operations**: Bán hàng, Check-in, Quản lý khách hàng, PT
5. **Management**: Đồ uống, Nguyên liệu, Sản phẩm, Gói tập, Mẫu gói
6. **Admin**: Audit log, Users, Locations

## Key Design Decisions

- **Multi-location**: Mọi entity đều có `location_id`, user được gán vào locations qua bảng `user_locations`
- **Soft delete**: customers, drinks, ingredients, products, packages dùng `is_active=0` thay vì DELETE
- **Audit trail**: Mọi thao tác quan trọng đều ghi vào `audit_logs` với location_id, user_id, action, entity_type, entity_id, details
- **Auto-generate customer code**: Format `HVxxxxxx` (6 digits), unique per location
- **Location-scoped data**: Mỗi user chỉ thấy dữ liệu của cơ sở đang chọn
- **Dual DB support**: SQLite cho local dev, PostgreSQL cho production (Railway) - tự detect qua `DATABASE_URL` env
