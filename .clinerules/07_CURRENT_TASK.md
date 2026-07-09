---
name: Current Task
alwaysApply: true
---

# Current Task

## Tổng quan

Dự án đã hoàn thành **Phase 2 - Full System** với đầy đủ các chức năng:

- Database SQLite/PostgreSQL với 18 tables
- Authentication (JWT + bcrypt) + đa cơ sở (locations)
- Customer CRUD + tự động sinh mã KH (HVxxxxxx)
- Check-in buổi tập gắn với gói tập
- Drink management (đồ uống) + recipe
- Ingredient/inventory management + adjust (OWNER)
- Product management (sản phẩm bán lẻ: thảm, áo, phụ kiện)
- Transaction/Sales (bán hàng: đồ uống, sản phẩm, gói)
- Package management (gói trả trước) + package templates + upgrade
- PT sessions & rate cards
- Audit log viewer (MANAGER+)
- Dashboard stats, fraud alerts, birthday alerts, export CSV
- User & Location management (OWNER)
- Navbar chung với location switcher

## Đã hoàn thành

### Core (100%)

- [x] SQLite/PostgreSQL schema với 18 tables
- [x] Seed user mặc định (admin/admin123 - OWNER) + giangvien1/123456 (STAFF)
- [x] Seed 2 locations (Cơ sở 1, Cơ sở 2)
- [x] Seed sample: customers, drinks, ingredients, products, package_templates, pt_rates
- [x] JWT authentication với FastAPI + NiceGUI
- [x] bcrypt password hashing
- [x] Role-based access control (STAFF/MANAGER/OWNER)
- [x] Multi-location support (locations, user_locations)
- [x] Soft delete cho customers, drinks, ingredients, products, packages
- [x] Audit log cho mọi hành động quan trọng
- [x] Auto-deduct inventory khi tạo giao dịch
- [x] Tự động sinh mã khách hàng (HVxxxxxx) không trùng

### UI (100%)

- [x] Trang login + select-location
- [x] Trang dashboard với thống kê, fraud alerts, birthday alerts
- [x] Trang quản lý khách hàng (CRUD, search, auto mã KH)
- [x] Trang check-in buổi tập
- [x] Trang bán hàng (transaction)
- [x] Trang quản lý đồ uống (drink)
- [x] Trang quản lý nguyên liệu/tồn kho (ingredient)
- [x] Trang quản lý sản phẩm (product)
- [x] Trang quản lý gói trả trước (package)
- [x] Trang mẫu gói (package-template)
- [x] Trang nâng cấp gói (package-upgrade)
- [x] Trang ghi nhận PT
- [x] Trang audit log (MANAGER+)
- [x] Trang quản lý user (OWNER)
- [x] Trang quản lý cơ sở (OWNER)
- [x] Navbar chung + mobile hamburger menu + nút đăng xuất
- [x] Location switcher với badge hiển thị cơ sở hiện tại
- [x] Export CSV
- [x] Toàn bộ UI tiếng Việt

### Maintenance (100%)

- [x] AI_RULES.md
- [x] PROJECT_CONTEXT.md (tiếng Việt)
- [x] ARCHITECTURE.md
- [x] UI_UX_GOAL.md
- [x] RAILWAY_DEPLOY.md
- [x] CURRENT_TASK.md
- [x] GOAL.md

## Cần làm tiếp theo

### Đang làm - Responsive Mobile UI (Phase 3)

- [x] Task 1: Navbar mobile - Thêm mobile bottom nav bar (`auth.py`), compact header
- [x] Task 2: CSS mobile enhancements - Media queries cho xs/sm breakpoints (`style.css`)
- [x] Task 2b: Dialog full-width - Thêm `max-w-full` cho tất cả dialog (customer, drink, ingredient, auth, product, pt)
- [x] Task 3: Table responsive - Thêm horizontal scroll cho table trên mobile
- [x] Task 4: Dashboard grid - Đổi stat cards dùng grid responsive
- [x] Task 5: Page-by-page mobile polish - Sửa từng page: form stacking, button sizing

### Kết luận Bootstrap vs Quasar

NiceGUI dùng Quasar Framework (tương đương Bootstrap về responsive). Không cần nhúng Bootstrap vì:

1. Xung đột CSS giữa Bootstrap và Quasar
2. Quasar có đủ grid 12-column, breakpoints xs/sm/md/lg/xl
3. NiceGUI đã export đầy đủ Quasar components (table, card, dialog, grid)

### Ưu tiên cao (bugs & fixes)

- [ ] Sửa lỗi page đồ uống (drink.py) - kiểm tra load, thêm/sửa/xóa
- [ ] Sửa lỗi nguyên liệu/tồn kho (ingredient.py) - kiểm tra adjust, lịch sử
- [ ] Sửa lỗi trang nhật ký (audit.py) - kiểm tra filter, phân quyền
- [ ] Kiểm tra tất cả popup đều có nút đóng (icon close)

### Ưu tiên trung bình

- [ ] Seed dữ liệu mẫu phong phú hơn
- [ ] Validation UI đẹp hơn (hiển thị lỗi/thành công)
- [x] Responsive mobile improvements (Phase 3 hoàn thành: mobile navbar, CSS mobile, dialog full-width, table scroll, dashboard grid, form/button polish)
- [ ] Đổi mật khẩu cá nhân
- [ ] Thêm sản phẩm vào package_items

### Có thể làm sau

- [ ] Multi-language support (EN/VN)
- [ ] Dark mode
- [ ] Charts cho dashboard (biểu đồ doanh thu, xu hướng)
- [ ] Barcode/QR code cho sản phẩm
- [ ] Print receipt cho giao dịch
- [ ] Chuyển từ top navbar sang left sidebar

## User mặc định

| Username   | Password | Role  |
| ---------- | -------- | ----- |
| admin      | admin123 | OWNER |
| giangvien1 | 123456   | STAFF |

## Tech Stack

- Python 3.13+
- FastAPI
- NiceGUI (Quasar components)
- SQLite (WAL mode, local dev) / PostgreSQL (production)
- bcrypt
- PyJWT
- Pydantic

## File structure hiện tại (16 files)

| File                | Lines | Chức năng                                         |
| ------------------- | ----- | ------------------------------------------------- |
| main.py             | 78    | App startup, register 14 routers                  |
| database.py         | 828   | Schema 18 tables, seed, migration                 |
| settings.py         | 14    | Config constants                                  |
| auth.py             | 1014  | Auth, users, locations, navbar                    |
| customer.py         | 526   | Customer CRUD + auto code                         |
| checkin.py          | ~500  | Check-in session management                       |
| drink.py            | ~311  | Drink CRUD                                        |
| ingredient.py       | ~600  | Ingredient CRUD + adjust                          |
| package.py          | ~800  | Customer package management                       |
| package_template.py | ~500  | Package template CRUD                             |
| package_upgrade.py  | ~400  | Package upgrade workflow                          |
| product.py          | ~600  | Product CRUD + adjust                             |
| transaction.py      | ~900  | Sales transaction creation                        |
| pt.py               | ~700  | PT sessions & rates                               |
| audit.py            | ~400  | Audit log viewer                                  |
| dashboard.py        | ~600  | Dashboard stats, export CSV, responsive stat grid |
