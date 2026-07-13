---
name: Project Context
alwaysApply: true
---

# Yoga/Gym Management System

Hệ thống quản lý phòng tập Yoga/Gym, hỗ trợ đa cơ sở và chống gian lận trong vận hành hằng ngày.

## Mục đích

Quản lý toàn diện hoạt động phòng tập:

- Khách hàng, check-in, gói tập trả trước.
- Đồ uống dinh dưỡng, nguyên liệu, tồn kho.
- Sản phẩm bán lẻ.
- Giao dịch bán hàng.
- PT sessions và bảng giá PT.
- Audit log cho thao tác quan trọng.
- Phân quyền theo vai trò và cơ sở.

## Business Rules

1. Mọi đồ uống dinh dưỡng phải thuộc về một khách hàng.
2. Không cho phép giao dịch đồ uống ẩn danh.
3. Quản lý tồn kho nguyên liệu bằng đơn vị nghiệp vụ như muỗng/nắp/gói.
4. STAFF không được sửa/xóa giao dịch.
5. Chỉ OWNER được điều chỉnh tồn kho nguyên liệu và sản phẩm.
6. Dữ liệu quan trọng dùng soft delete bằng `is_active=0`.
7. Dữ liệu phải được scope theo `location_id`.
8. Mọi thao tác quan trọng phải tạo audit log.
9. User phải chọn cơ sở làm việc trước khi thao tác dữ liệu.

## Roles

### STAFF

Có thể:

- Xem dashboard, khách hàng, đồ uống, nguyên liệu, sản phẩm.
- Tạo khách hàng mới.
- Check-in khách hàng.
- Tạo giao dịch bán hàng.
- Ghi nhận PT sessions.

Không thể:

- Sửa/xóa giao dịch.
- Điều chỉnh tồn kho.
- Tạo/sửa/xóa mềm đồ uống, nguyên liệu, sản phẩm.
- Xem audit log.
- Quản lý người dùng/cơ sở.

### MANAGER

Có thể:

- Tất cả quyền STAFF.
- Tạo/sửa đồ uống, nguyên liệu, sản phẩm.
- Sửa thông tin khách hàng.
- Xem audit log và fraud alerts.
- Quản lý mẫu gói và nâng cấp gói.

Không thể:

- Điều chỉnh tồn kho nguyên liệu/sản phẩm.
- Xóa mềm đồ uống/nguyên liệu/sản phẩm.
- Quản lý người dùng/cơ sở.

### OWNER

Có thể:

- Tất cả quyền MANAGER.
- Điều chỉnh tồn kho nguyên liệu và sản phẩm.
- Vô hiệu hóa dữ liệu quan trọng theo soft delete.
- Quản lý người dùng, vai trò, cơ sở.
- Xem toàn bộ báo cáo và audit.

## Multi-location

- Entity nghiệp vụ phải có hoặc dùng `location_id`.
- User được gán cơ sở qua `user_locations`.
- Sau login, user chọn cơ sở tại `/select-location`.
- Cơ sở hiện tại lưu trong `app.storage.user["location_id"]` và `app.storage.user["location_name"]`.
- Query dữ liệu nghiệp vụ phải lọc theo cơ sở hiện tại.

## Main Domain Files

| Domain             | File                  | Ghi chú                               |
| ------------------ | --------------------- | ------------------------------------- |
| Auth/User/Location | `auth.py`             | JWT, bcrypt, navbar, users, locations |
| Customer           | `customer.py`         | CRUD, auto mã HVxxxxxx                |
| Check-in           | `checkin.py`          | Check-in gắn với gói                  |
| Sales              | `transaction.py`      | Bán đồ uống, sản phẩm, gói            |
| Drink              | `drink.py`            | Đồ uống và recipe                     |
| Ingredient         | `ingredient.py`       | Nguyên liệu, tồn kho                  |
| Product            | `product.py`          | Sản phẩm bán lẻ                       |
| Package            | `package.py`          | Gói trả trước                         |
| Package Template   | `package_template.py` | Mẫu gói                               |
| Package Upgrade    | `package_upgrade.py`  | Nâng cấp gói                          |
| PT                 | `pt.py`               | PT sessions/rates                     |
| Audit              | `audit.py`            | Nhật ký hệ thống                      |
| Dashboard          | `dashboard.py`        | Thống kê, fraud alerts, export        |

## Anti-fraud Focus

Mọi giao dịch cần truy vết được:

Khách hàng → Giao dịch → Tồn kho/Gói → Audit Log → User → Cơ sở

Khi chỉnh logic bán hàng, check-in, tồn kho, package hoặc user/location, luôn kiểm tra:

- Đúng quyền.
- Đúng cơ sở.
- Có audit log.
- Không tạo lỗ hổng giao dịch ẩn danh hoặc chỉnh sửa trái quyền.
