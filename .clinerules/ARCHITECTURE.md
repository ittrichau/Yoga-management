"# Architecture

## Project Structure

```
gym_nutrition/
├── README.md
├── AI_RULES.md
├── PROJECT_CONTEXT.md
├── ARCHITECTURE.md
├── CURRENT_TASK.md
├── requirements.txt
├── main.py              # App startup, route registration, navbar
├── database.py          # SQLite connection, schema, seed defaults
├── settings.py          # Config constants (DB_PATH, SECRET_KEY, etc.)
├── auth.py              # Authentication (JWT, bcrypt), authorization, user CRUD UI
├── customer.py          # Customer CRUD, check-in
├── product.py           # Product management, categories
├── inventory.py         # Inventory management, adjustments, history
├── nutrition.py         # Nutrition transaction creation, history
├── dashboard.py         # Dashboard stats, fraud alerts, stock overview
├── audit.py             # Audit log viewer
└── data/                # SQLite database storage (git-ignored)
    └── gym_nutrition.db
```

## Responsibilities

| File | Chức năng |
|------|-----------|
| **main.py** | Khởi động app, đăng ký route, navbar điều hướng |
| **database.py** | Kết nối SQLite, tạo schema, seed user mặc định |
| **settings.py** | Hằng số cấu hình (DB_PATH, SECRET_KEY, SUPER_USER) |
| **auth.py** | Xác thực JWT, phân quyền, trang login, quản lý user |
| **customer.py** | CRUD khách hàng, check-in, tìm kiếm |
| **product.py** | CRUD sản phẩm, lọc danh mục, kiểm tra tồn kho |
| **inventory.py** | Điều chỉnh tồn kho (OWNER), lịch sử adjust |
| **nutrition.py** | Tạo giao dịch dinh dưỡng, tự động trừ tồn kho |
| **dashboard.py** | Thống kê, cảnh báo fraud, tổng quan tồn kho |
| **audit.py** | Xem nhật ký kiểm toán, lọc theo entity/action |

## Tech Stack

- **Python 3.13+** 
- **FastAPI** - REST API backend
- **NiceGUI** - Giao diện UI
- **SQLite** - Cơ sở dữ liệu (WAL mode, foreign keys)
- **PyJWT** - JWT token authentication
- **bcrypt** - Mã hóa mật khẩu

## Authentication Flow

```
User → Login Form → bcrypt verify → JWT token → Lưu vào app.storage.user
                                                      ↓
                                            Mỗi page kiểm tra token
                                            Nếu không có → redirect /login
```

## Database Schema

7 tables:
- **users**: id, username, hashed_password, full_name, role (STAFF/MANAGER/OWNER), is_active
- **customers**: id, code, full_name, phone, email, notes, is_active, created_by
- **products**: id, name, category, scoops_per_serving, current_stock_scoops, min_stock_scoops, created_by
- **inventory_adjustments**: id, product_id, adjustment_type (add/remove/count_correct), quantity_scoops, reason
- **nutrition_transactions**: id, customer_id, product_id, scoops_used, notes, created_by
- **audit_logs**: id, user_id, action, entity_type, entity_id, details, ip_address

## Role Hierarchy

```
STAFF(1) < MANAGER(2) < OWNER(3)
```

## API Endpoints

| Method | Endpoint | Quyền |
|--------|----------|-------|
| POST | /api/login | Public |
| GET | /api/me | Any |
| GET/POST | /api/users | OWNER |
| PUT | /api/users/{id} | OWNER |
| GET/POST | /api/customers | Any |
| PUT | /api/customers/{id} | MANAGER+ |
| POST | /api/customers/{id}/checkin | Any |
| GET/POST | /api/products | MANAGER+ (create) |
| PUT/DELETE | /api/products/{id} | MANAGER+/OWNER |
| GET | /api/inventory/products | Any |
| POST | /api/inventory/adjust | OWNER |
| POST | /api/nutrition/transactions | Any |
| GET | /api/audit/logs | MANAGER+ |
| GET | /api/dashboard/stats | Any |
| GET | /api/dashboard/fraud-alerts | MANAGER+ |
| GET | /api/dashboard/transactions/export-csv | Any |
"