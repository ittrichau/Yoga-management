# GOAL - Các việc cần hoàn thành tiếp theo

## Mục tiêu tổng quan

Hoàn thiện các lỗi và thiếu sót hiện tại của hệ thống quản lý Yoga/Gym, tập trung vào trải nghiệm quản trị, quản lý khách hàng, gói tập, đồ uống, nguyên liệu và nhật ký.

---

## 1. Tự động tạo mã khách hàng

### Trang liên quan

- `/customers`
- File dự kiến: `customer.py`

### Yêu cầu

Khi thêm khách hàng mới, trường **mã khách hàng** phải được hệ thống tự động sinh, không bắt người dùng nhập tay.

### Quy tắc đề xuất

- Mã khách hàng là duy nhất.
- Có thể dùng format đơn giản:
  - `KH000001`
  - `KH000002`
  - `KH000003`
- Khi mở popup thêm khách hàng, mã được tự động hiển thị hoặc tự động gán khi lưu.
- Không cho phép sửa mã khách hàng nếu không cần thiết.

### Tiêu chí hoàn thành

- [ ] Thêm khách hàng mới không cần nhập mã.
- [ ] Mã khách hàng không bị trùng.
- [ ] Khách hàng mới lưu thành công với mã tự sinh.
- [ ] UI hiển thị mã khách hàng sau khi tạo.

---

## 2. Tất cả popup phải có icon đóng

### Trang liên quan

- Tất cả các trang có popup/dialog:
  - Khách hàng
  - Sản phẩm/đồ uống
  - Nguyên liệu/tồn kho
  - Gói tập
  - Người dùng
  - Nhật ký
  - Giao dịch

### File dự kiến

- `customer.py`
- `product.py`
- `inventory.py`
- `nutrition.py`
- `auth.py`
- Các file UI khác nếu có dialog

### Yêu cầu

Mỗi popup/dialog phải có icon hoặc nút đóng rõ ràng ở góc phải phía trên.

### Tiêu chí hoàn thành

- [ ] Popup thêm/sửa khách hàng có nút đóng.
- [ ] Popup đồ uống có nút đóng.
- [ ] Popup nguyên liệu/tồn kho có nút đóng.
- [ ] Popup gói tập có nút đóng.
- [ ] Popup người dùng có nút đóng.
- [ ] Popup nhật ký nếu có filter/detail popup thì có nút đóng.
- [ ] Nút đóng hoạt động đúng, không làm mất dữ liệu ngoài ý muốn nếu chưa lưu.

---

## 3. Thêm trang quản lý gói tập

### Trang mới cần có

- `/packages` hoặc `/membership-packages`

### File dự kiến

- Tạo mới: `package.py` hoặc `membership.py`
- Sửa: `database.py`
- Sửa: `main.py`
- Có thể sửa: `customer.py`

### Yêu cầu nghiệp vụ

Cần có trang quản lý các **gói tập**. Khi tạo hoặc cập nhật gói cho khách hàng thì chọn từ danh sách gói này.

### Dữ liệu gói tập đề xuất

Một gói tập gồm:

- Tên gói
- Mô tả
- Số buổi hoặc số ngày hiệu lực
- Giá tiền
- Trạng thái hoạt động
- Ngày tạo

### Chức năng cần có

- [ ] Xem danh sách gói tập.
- [ ] Thêm gói tập.
- [ ] Sửa gói tập.
- [ ] Vô hiệu hóa gói tập thay vì xóa cứng.
- [ ] Tìm kiếm/lọc gói tập.
- [ ] Khi tạo khách hàng hoặc gán gói cho khách hàng, chọn gói từ danh sách đã tạo.

### Database dự kiến

Cần thêm bảng mới, ví dụ:

- `packages`
  - `id`
  - `name`
  - `description`
  - `duration_days`
  - `session_count`
  - `price`
  - `is_active`
  - `created_at`
  - `created_by`

Có thể cần thêm bảng lịch sử gói khách hàng:

- `customer_packages`
  - `id`
  - `customer_id`
  - `package_id`
  - `start_date`
  - `end_date`
  - `remaining_sessions`
  - `status`
  - `created_at`
  - `created_by`

### Tiêu chí hoàn thành

- [ ] Có menu/trang quản lý gói tập.
- [ ] Tạo được gói tập mới.
- [ ] Sửa được gói tập.
- [ ] Vô hiệu hóa được gói tập.
- [ ] Khách hàng có thể được gán gói tập từ danh sách.
- [ ] Không nhập tay tên gói khi gán cho khách hàng.

---

## 4. Sửa lỗi page đồ uống

### Trang liên quan

- Page đồ uống/sản phẩm
- File dự kiến: `product.py`

### Yêu cầu

Hiện tại page đồ uống đang lỗi, cần kiểm tra và sửa.

### Việc cần kiểm tra

- [ ] Trang có load được không.
- [ ] Lỗi query database.
- [ ] Lỗi hiển thị bảng.
- [ ] Lỗi thêm/sửa đồ uống.
- [ ] Lỗi danh mục/category.
- [ ] Lỗi tồn kho theo số muỗng/scoops.
- [ ] Lỗi phân quyền MANAGER/OWNER.
- [ ] Lỗi popup không đóng được hoặc thiếu nút đóng.

### Tiêu chí hoàn thành

- [ ] Mở page đồ uống không lỗi.
- [ ] Thêm đồ uống thành công.
- [ ] Sửa đồ uống thành công.
- [ ] Vô hiệu hóa/xóa mềm đồ uống thành công.
- [ ] Danh sách cập nhật lại sau thao tác.
- [ ] Có thông báo thành công/thất bại rõ ràng.

---

## 5. Sửa lỗi nguyên liệu / tồn kho

### Trang liên quan

- Page nguyên liệu hoặc tồn kho
- File dự kiến: `inventory.py`

### Yêu cầu

Hiện tại page nguyên liệu/tồn kho đang lỗi, cần kiểm tra và sửa.

### Việc cần kiểm tra

- [ ] Trang có load được không.
- [ ] Lỗi lấy danh sách sản phẩm/nguyên liệu.
- [ ] Lỗi điều chỉnh tồn kho.
- [ ] Lỗi lịch sử điều chỉnh.
- [ ] Lỗi quyền OWNER khi điều chỉnh.
- [ ] Lỗi đơn vị tính.
- [ ] Lỗi cập nhật số lượng sau khi điều chỉnh.
- [ ] Lỗi popup thiếu icon đóng.

### Tiêu chí hoàn thành

- [ ] Mở page nguyên liệu/tồn kho không lỗi.
- [ ] OWNER điều chỉnh tồn kho được.
- [ ] STAFF/MANAGER không được điều chỉnh nếu không đủ quyền.
- [ ] Lịch sử điều chỉnh hiển thị đúng.
- [ ] Số lượng tồn kho cập nhật đúng.
- [ ] Có audit log khi điều chỉnh.

---

## 6. Sửa lỗi trang nhật ký

### Trang liên quan

- Page nhật ký/audit log
- File dự kiến: `audit.py`

### Yêu cầu

Hiện tại trang nhật ký đang lỗi, cần kiểm tra và sửa.

### Việc cần kiểm tra

- [ ] Trang có load được không.
- [ ] Lỗi query audit log.
- [ ] Lỗi lọc theo hành động.
- [ ] Lỗi lọc theo loại dữ liệu.
- [ ] Lỗi phân quyền MANAGER/OWNER.
- [ ] Lỗi hiển thị user thực hiện.
- [ ] Lỗi format thời gian.
- [ ] Lỗi popup/detail nếu có.

### Tiêu chí hoàn thành

- [ ] Mở trang nhật ký không lỗi.
- [ ] MANAGER/OWNER xem được nhật ký.
- [ ] STAFF không được xem nếu không đủ quyền.
- [ ] Bộ lọc hoạt động đúng.
- [ ] Dữ liệu hiển thị rõ ràng.
- [ ] Không làm crash app nếu audit log trống.

---

## Thứ tự ưu tiên đề xuất

1. Sửa lỗi page đồ uống.
2. Sửa lỗi nguyên liệu/tồn kho.
3. Sửa lỗi trang nhật ký.
4. Tự động generate mã khách hàng.
5. Thêm icon đóng cho tất cả popup.
6. Thêm trang quản lý gói tập.
7. Gán gói tập cho khách hàng.

---

## Ghi chú kỹ thuật

- Không tạo controller/service/repository/dto không cần thiết.
- Ưu tiên sửa trực tiếp trong file domain hiện tại.
- Không refactor lan rộng ngoài phạm vi lỗi.
- Mọi thao tác quan trọng cần ghi audit log.
- Dữ liệu quan trọng dùng soft delete, không xóa cứng.
- UI nên dùng tiếng Việt thống nhất.

---

## Next Suggested Task

Bắt đầu bằng việc kiểm tra lỗi cụ thể ở page đồ uống, nguyên liệu và nhật ký bằng cách đọc các file:

- `product.py`
- `inventory.py`
- `audit.py`

Sau đó chạy app hoặc kiểm tra log lỗi để sửa đúng nguyên nhân.