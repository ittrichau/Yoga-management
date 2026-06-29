"# Current Task

## Tổng quan

Dự án đã hoàn thành **Phase 1 - MVP** với đầy đủ các chức năng core:

- Database SQLite với 7 tables
- Authentication (JWT + bcrypt)
- Customer CRUD + check-in
- Product CRUD + danh mục
- Inventory management + adjust (OWNER)
- Nutrition transactions + auto-deduct stock
- Audit log viewer
- Dashboard stats + fraud alerts

## Đã hoàn thành

### Core (100%)

- [x] SQLite schema (users, customers, products, inventory_adjustments, nutrition_transactions, audit_logs)
- [x] Seed user mặc định (admin/admin123 - OWNER)
- [x] JWT authentication với FastAPI + NiceGUI
- [x] bcrypt password hashing
- [x] Role-based access control (STAFF/MANAGER/OWNER)
- [x] Soft delete cho customers, products, users
- [x] Audit log cho mọi hành động
- [x] Auto-deduct inventory khi tạo giao dịch dinh dưỡng

### UI (100%)

- [x] Trang login
- [x] Trang dashboard với thống kê
- [x] Trang quản lý khách hàng
- [x] Trang quản lý sản phẩm
- [x] Trang quản lý tồn kho
- [x] Trang tạo giao dịch dinh dưỡng
- [x] Trang audit log
- [x] Trang quản lý user (OWNER)
- [x] Cảnh báo stock thấp
- [x] Export CSV

### Bảo trì (100%)

- [x] AI_RULES.md
- [x] PROJECT_CONTEXT.md (tiếng Việt)
- [x] ARCHITECTURE.md
- [x] CURRENT_TASK.md

## Cần làm tiếp theo

### Ưu tiên cao ✅

- [x] **Dịch toàn bộ giao diện sang tiếng Việt** (auth.py, customer.py, product.py, inventory.py, nutrition.py, audit.py, dashboard.py)
- [x] Thêm navbar chung + nút đăng xuất (render_navbar trong auth.py)
- [x] Sửa lỗi duplicate code trong inventory.py và audit.py
- [x] Sửa lỗi thiếu function definition trong auth.py (deactivate_user)

### Ưu tiên trung bình

- [ ] Seed dữ liệu mẫu (khách hàng, sản phẩm demo)
- [ ] Validation UI đẹp hơn (hiển thị lỗi/ thành công)
- [ ] Responsive mobile
- [ ] Đổi mật khẩu cá nhân

### Có thể làm sau

- [ ] Multi-language support (EN/VN)
- [ ] Dark mode
- [ ] Charts cho dashboard (biểu đồ doanh thu, xu hướng)
- [ ] Barcode/QR code cho sản phẩm
- [ ] Print receipt cho giao dịch

## User mặc định

| Username | Password | Role  |
| -------- | -------- | ----- |
| admin    | admin123 | OWNER |

## Tech Stack

- Python 3.13+
- FastAPI
- NiceGUI
- SQLite (WAL mode)
- bcrypt
- PyJWT
- Pydantic
  "
