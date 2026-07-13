---
name: UI UX Goal
alwaysApply: true
---

# UI/UX Goal

## Product Vision

Giao diện theo hướng **Modern SaaS Dashboard** cho hệ thống quản lý Yoga/Gym nội bộ.

Ưu tiên:

- Rõ ràng.
- Nhanh thao tác.
- Nhất quán.
- Dễ dùng cho STAFF, MANAGER, OWNER.
- Phù hợp vận hành đa cơ sở.
- Calm, clean, premium, dễ nhìn khi dùng lâu.

## Design Principles

- Usability over decoration.
- Desktop productivity là ưu tiên chính.
- Giảm số click và giảm tải nhận thức.
- Không thêm component chỉ để làm đẹp.
- Không phá vỡ flow: Login → Select Location → Dashboard.
- Không phá vỡ phân quyền, location scope, audit log.

## Visual Direction

- Background chính: `#FFFFFF`.
- Background phụ: `#F7F4EF`.
- Accent chính: `#8FAF9D`.
- Accent phụ: `#748C70`.
- Text: `#2E3A35`.
- Border: `#E5E7EB`.
- Radius mềm: 8–12px.
- Shadow nhẹ, chỉ dùng để phân tách lớp.
- Typography sạch, ưu tiên Inter/Geist nếu có.
- Tránh gradient nặng, glassmorphism, animation trang trí, visual clutter.

## Layout

Source hiện tại dùng shared top navbar trong `auth.render_navbar()`.

Khi chỉnh navigation:

- Giữ đủ module hiện có.
- Hiển thị cơ sở hiện tại rõ ràng.
- Có đổi cơ sở.
- Có quick actions quan trọng như Bán hàng, Check-in.
- Không hiển thị menu/action vượt quyền.
- Mobile có thể dùng hamburger/drawer/bottom nav nhưng không hy sinh desktop.

## Data Pages

Áp dụng cho khách hàng, gói, PT, đồ uống, nguyên liệu, sản phẩm, mẫu gói, audit, user, cơ sở.

Mỗi trang nên có:

- Tiêu đề rõ.
- Toolbar với search/filter nếu cần.
- Action chính dễ thấy.
- Table dễ scan, ưu tiên table hơn card nếu thao tác dữ liệu.
- Badge trạng thái như Hoạt động/Vô hiệu/Sắp hết/Tồn kho thấp.
- Empty state và loading/error state rõ ràng.
- Text thông báo tiếng Việt dễ hiểu.

## Forms and Dialogs

Forms/dialogs cần:

- Label rõ ràng.
- Field bắt buộc dễ nhận biết.
- Validation message cụ thể bằng tiếng Việt.
- Group field liên quan khi form dài.
- Submit/cancel rõ ràng.
- Action nguy hiểm có confirmation.
- Popup/dialog thêm/sửa/xem chi tiết có icon đóng rõ ở góc phải phía trên.
- Dialog responsive, không tràn màn hình mobile.

## Dashboard

Dashboard chỉ nên cung cấp tổng quan nhanh theo cơ sở đang chọn:

- Tổng khách hàng.
- Doanh thu hôm nay/tháng.
- Giao dịch hôm nay.
- Check-in hôm nay.
- Gói sắp hết hạn/buổi.
- Tồn kho thấp.
- Hoạt động gần đây.
- Fraud alerts cho MANAGER/OWNER.

Không biến dashboard thành trang báo cáo phức tạp.

## Responsive Strategy

- Desktop là nền tảng chính.
- Tablet giữ đủ chức năng chính.
- Mobile ưu tiên nghiệp vụ nhanh và tránh tràn layout.
- Table trên mobile cần horizontal scroll hoặc layout phù hợp.
- Dialog trên mobile cần full-width hợp lý.

## Implementation Checklist

Trước khi hoàn thành UI task, kiểm tra:

- Hành động chính có dễ thấy không?
- Cơ sở hiện tại có rõ không?
- User không thấy action vượt quyền không?
- Form/table/dialog có dễ dùng không?
- Error/success state có rõ và tiếng Việt không?
- UI có nhất quán, calm, clean không?
