---
name: Project Context
alwaysApply: true
---

# Yoga/Gym Management System

Hệ thống quản lý phòng tập Yoga/Gym, chống gian lận nhân viên. Hỗ trợ đa cơ sở.

## Mục đích

Quản lý toàn diện hoạt động phòng tập Yoga/Gym:

- Quản lý khách hàng, check-in, gói tập trả trước
- Quản lý đồ uống dinh dưỡng, nguyên liệu, tồn kho
- Quản lý sản phẩm bán lẻ (thảm, áo, phụ kiện)
- Quản lý giao dịch bán hàng
- Quản lý PT (Personal Trainer) sessions & rate cards
- Ngăn chặn gian lận từ nhân viên
- Audit log toàn bộ hành động quan trọng

## Nguyên tắc Kinh doanh

1. Mọi đồ uống dinh dưỡng phải thuộc về một khách hàng.
2. Quản lý tồn kho bằng số muỗng (scoops), không phải tiền.
3. Nhân viên KHÔNG được sửa hoặc xóa giao dịch.
4. Chỉ OWNER mới được điều chỉnh tồn kho nguyên liệu.
5. Mọi hành động phải tạo Audit Log.
6. Dữ liệu không được xóa (soft delete với is_active=0).
7. Tất cả dữ liệu được phân tách theo cơ sở (location_id).

## Phân quyền

### STAFF (Nhân viên)

**Có thể:**

- Xem dashboard, khách hàng, đồ uống, nguyên liệu, sản phẩm
- Tạo khách hàng mới (auto-gen mã HVxxxxxx)
- Check-in khách hàng
- Tạo giao dịch bán hàng (đồ uống, sản phẩm, gói)
- Ghi nhận PT sessions

**Không thể:**

- Sửa hoặc xóa giao dịch
- Điều chỉnh tồn kho nguyên liệu
- Tạo/sửa/xóa đồ uống, nguyên liệu, sản phẩm
- Xem audit log
- Vô hiệu hóa đồ uống/nguyên liệu/sản phẩm
- Quản lý người dùng, cơ sở

### MANAGER (Quản lý)

**Có thể:**

- Tất cả quyền STAFF
- Tạo/sửa đồ uống, nguyên liệu, sản phẩm
- Sửa thông tin khách hàng
- Xem audit log
- Xem fraud alerts
- Quản lý mẫu gói (package templates)
- Thực hiện nâng cấp gói

**Không thể:**

- Điều chỉnh tồn kho nguyên liệu (chỉ OWNER)
- Vô hiệu hóa/xóa mềm đồ uống, nguyên liệu, sản phẩm (chỉ OWNER)
- Quản lý người dùng, cơ sở
- Điều chỉnh tồn kho sản phẩm (chỉ OWNER)

### OWNER (Chủ sở hữu)

**Có thể:**

- Tất cả quyền MANAGER
- Điều chỉnh tồn kho nguyên liệu & sản phẩm
- Vô hiệu hóa đồ uống, nguyên liệu, sản phẩm
- Quản lý người dùng (CRUD, phân quyền, gán cơ sở)
- Quản lý cơ sở (CRUD, vô hiệu hóa)
- Xem tất cả báo cáo

## Chống Gian lận

**Cấm:**

- Khách hàng ẩn danh
- Walk-in không đăng ký
- Đồ uống không theo dõi

Mọi đồ uống phải có thể truy vết:
Khách hàng → Giao dịch → Tồn kho → Audit Log

## Các module chính

| Module       | File                | Chức năng                                    |
| ------------ | ------------------- | -------------------------------------------- |
| Khách hàng   | customer.py         | CRUD, auto mã HV000001, birthday alerts      |
| Check-in     | checkin.py          | Check-in buổi tập, gắn với gói tập           |
| Bán hàng     | transaction.py      | Tạo giao dịch bán đồ uống, sản phẩm, gói     |
| Đồ uống      | drink.py            | CRUD đồ uống, soft delete (OWNER)            |
| Nguyên liệu  | ingredient.py       | CRUD nguyên liệu, điều chỉnh tồn kho (OWNER) |
| Sản phẩm     | product.py          | CRUD sản phẩm bán lẻ, điều chỉnh tồn kho     |
| Gói tập      | package.py          | Tạo & quản lý gói trả trước cho khách hàng   |
| Mẫu gói      | package_template.py | Quản lý mẫu gói (BASIC, FAT_LOSS, COMBO)     |
| Nâng cấp gói | package_upgrade.py  | Nâng cấp gói, tính tiền bù                   |
| PT           | pt.py               | PT sessions & rate cards                     |
| Nhật ký      | audit.py            | Xem audit log, lọc theo entity/action/user   |
| Dashboard    | dashboard.py        | Thống kê, fraud alerts, export CSV           |
| Người dùng   | auth.py             | CRUD users, locations, phân quyền đa cơ sở   |
| Auth         | auth.py             | Login, JWT, bcrypt, navbar                   |

## Đa cơ sở (Multi-location)

- Mỗi entity có `location_id`, data được scope theo cơ sở
- User được gán vào locations qua bảng `user_locations`
- Sau khi login, user phải chọn cơ sở làm việc (`/select-location`)
- Navbar hiển thị cơ sở hiện tại, có nút đổi cơ sở
- Location switcher: `app.storage.user["location_id"]` + `app.storage.user["location_name"]`

## Database

- **Local dev**: SQLite (WAL mode, foreign keys) tại `data/gym_nutrition.db`
- **Production**: PostgreSQL trên Railway (tự detect qua `DATABASE_URL` env)
- **18 tables**: locations, users, user_locations, customers, drinks, ingredients, drink_recipes, products, product_stock_adjustments, packages, package_items, package_templates, package_sessions, transactions, inventory_adjustments, pt_rates, pt_sessions, audit_logs
