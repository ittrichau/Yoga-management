---
name: Product Goal
alwaysApply: true
---

# Product Goal

## Mục tiêu tổng quan

Hoàn thiện hệ thống quản lý Yoga/Gym theo hướng vận hành ổn định, chống gian lận, dễ dùng cho nhân viên/quản lý/chủ cơ sở và giữ codebase đơn giản để AI có thể bảo trì an toàn.

## Active Priorities

### 1. Hoàn tất kiểm tra popup/dialog có nút đóng

Các popup/dialog còn cần kiểm tra hoặc bổ sung icon đóng ở góc phải phía trên:

- `package.py`
- `auth.py`
- `transaction.py`
- `product.py`

Tiêu chí hoàn thành:

- Popup thêm/sửa/xem chi tiết có nút đóng rõ ràng.
- Nút đóng hoạt động đúng.
- Không làm mất dữ liệu ngoài ý muốn nếu chưa lưu.
- UI thống nhất với các popup đã hoàn thành ở `customer.py`, `drink.py`, `ingredient.py`, `audit.py`.

### 2. Cải thiện tìm kiếm/lọc và validation

Ưu tiên sau popup:

- Tìm kiếm/lọc gói tập ở `/packages` nếu còn thiếu.
- Validation UI rõ ràng hơn cho các form chính.
- Thông báo lỗi/thành công phải dễ hiểu, tiếng Việt.

### 3. Hoàn thiện dữ liệu và package item

Các việc có thể làm tiếp:

- Seed dữ liệu mẫu phong phú hơn.
- Thêm sản phẩm bán lẻ vào `package_items` nếu cần nghiệp vụ combo sản phẩm.
- Kiểm tra thống nhất audit log cho các thao tác quan trọng.

## Backlog

- Đổi mật khẩu cá nhân / flow đổi mật khẩu.
- Charts cho dashboard: doanh thu, xu hướng check-in, tồn kho.
- Barcode/QR code cho sản phẩm.
- Print receipt cho giao dịch.
- Multi-language EN/VN.
- Dark mode.
- Chuyển từ top navbar sang left sidebar nếu cần nâng cấp UI lớn.

## Done Recently

- Tự động sinh mã khách hàng theo cơ sở: `HV000001`, `HV000002`, ...
- API preview mã khách hàng tiếp theo: `/api/customers/next-code`.
- Sửa page đồ uống: load, thêm/sửa, soft delete, phân quyền, popup close.
- Sửa page nguyên liệu/tồn kho: adjust, lịch sử, OWNER permission, audit log, popup close.
- Sửa trang audit log: query/filter/user/time/detail popup.
- Hoàn thành quản lý gói trả trước, mẫu gói, nâng cấp gói và gán gói từ danh sách mẫu.
- Hoàn thành Responsive Mobile UI Phase 3: mobile navbar, CSS responsive, dialog full-width, table scroll, dashboard grid, form/button polish.

## Technical Constraints

- Không tạo controller/service/repository/dto không cần thiết.
- Không refactor lan rộng ngoài phạm vi task.
- Ưu tiên sửa trực tiếp trong file domain hiện tại.
- Mọi thao tác quan trọng cần audit log.
- Dữ liệu quan trọng dùng soft delete, không xóa cứng.
- Dữ liệu phải scope theo `location_id`.
- UI dùng tiếng Việt thống nhất.
- File đồ uống: `drink.py`.
- File nguyên liệu/tồn kho: `ingredient.py`.
- File sản phẩm bán lẻ: `product.py`.

## Current Task Update Policy

Sau mỗi task implement, phải cập nhật `.clinerules/07_CURRENT_TASK.md`.

Nếu task làm thay đổi backlog, ưu tiên, tiêu chí hoàn thành hoặc task tiếp theo, phải cập nhật file này.
