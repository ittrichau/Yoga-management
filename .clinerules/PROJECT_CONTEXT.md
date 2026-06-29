"# Gym Nutrition Management System

Hệ thống quản lý dinh dưỡng phòng gym, chống gian lận nhân viên.

## Mục đích

Quản lý hoạt động dinh dưỡng tại phòng gym, ngăn chặn gian lận từ nhân viên.

## Nguyên tắc Kinh doanh

1. Mọi đồ uống dinh dưỡng phải thuộc về một khách hàng.
2. Quản lý tồn kho bằng số muỗng (scoops), không phải tiền.
3. Nhân viên KHÔNG được sửa hoặc xóa giao dịch.
4. Chỉ OWNER mới được điều chỉnh tồn kho.
5. Mọi hành động phải tạo Audit Log.
6. Dữ liệu không được xóa (soft delete).

## Phân quyền

### STAFF (Nhân viên)

**Có thể:**
- Check-in khách hàng
- Tạo giao dịch dinh dưỡng

**Không thể:**
- Sửa giao dịch
- Xóa giao dịch
- Điều chỉnh tồn kho

### MANAGER (Quản lý)

**Có thể:**
- Kiểm kê tồn kho
- Phê duyệt hủy bỏ
- Xem audit log
- Tạo/sửa sản phẩm
- Sửa thông tin khách hàng

### OWNER (Chủ sở hữu)

**Có thể:**
- Mọi quyền
- Quản lý người dùng
- Điều chỉnh tồn kho
- Xem tất cả báo cáo
- Vô hiệu hóa sản phẩm

## Chống Gian lận

**Cấm:**
- Khách hàng ẩn danh
- Walk-in không đăng ký
- Đồ uống không theo dõi

Mọi đồ uống phải có thể truy vết:
Khách hàng → Giao dịch → Tồn kho → Audit Log
"