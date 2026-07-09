---
name: UI UX Goal
alwaysApply: true
---

# UI/UX Goal

## Product Vision

Hệ thống được định hướng theo phong cách **Modern SaaS Dashboard** dành cho một **Yoga/Gym Studio Management System**.

Đây là hệ thống quản lý nội bộ được sử dụng hằng ngày bởi lễ tân, quản lý, chủ cơ sở và huấn luyện viên/PT. Vì vậy, giao diện cần ưu tiên:

- Rõ ràng
- Nhanh thao tác
- Nhất quán
- Dễ sử dụng
- Ít gây mệt mỏi khi dùng lâu
- Chuyên nghiệp và đáng tin cậy
- Phù hợp vận hành đa cơ sở

Thiết kế tổng thể cần mang cảm giác **bình tĩnh, sạch sẽ, cao cấp và dễ chịu**, phù hợp với tinh thần yên bình của yoga.

---

## Core Design Philosophy

Ưu tiên **usability over decoration**.

Mỗi màn hình cần trả lời được:

1. Mục tiêu chính của người dùng là gì?
2. Cách nhanh nhất để hoàn thành mục tiêu đó là gì?
3. Thông tin quan trọng nhất có hiển thị ngay lập tức không?
4. Người dùng có hiểu màn hình trong vòng 5 giây không?

Nguyên tắc UX chính:

- Giảm số lần click không cần thiết
- Giảm tải nhận thức
- Giữ tương tác dễ đoán
- Ưu tiên luồng làm việc thực tế
- Không dùng hiệu ứng trang trí gây phân tâm
- Desktop productivity là ưu tiên chính

---

## Design Style

Phong cách giao diện:

- Modern SaaS Dashboard
- Minimalism 2.0
- Spacious layout với nhiều khoảng trắng
- Soft rounded corners: 8–12px
- Light shadows chỉ dùng khi cần phân tách lớp
- Clean typography
- Consistent spacing theo hệ 8px
- Animation nhẹ, tinh tế: 150–250ms

Tránh sử dụng:

- Glassmorphism nặng
- Neobrutalism
- Gradient quá nhiều
- Giao diện quá nhiều màu
- Animation trang trí
- Visual clutter

---

## Color Palette

### Primary Background

```text
White: #FFFFFF
```

### Secondary Background

```text
Soft Beige: #F7F4EF
```

### Primary Accent

```text
Sage Green: #8FAF9D
```

### Secondary Accent

```text
Olive Green: #748C70
```

### Text

```text
Dark Gray: #2E3A35
```

### Border

```text
Neutral Gray: #E5E7EB
```

Tổng thể màu sắc cần tạo cảm giác:

- Thư giãn
- Cao cấp
- Tin cậy
- Thân thiện với mắt khi làm việc lâu

---

## Layout Direction

Sử dụng layout SaaS cổ điển:

- Left Sidebar Navigation hoặc Header Navigation tùy giai đoạn triển khai
- Top Toolbar/Header
- Wide Content Area
- Spacious white space
- Responsive nhưng không hy sinh năng suất desktop

Source hiện tại đang dùng **shared top navbar** trong `auth.py` qua hàm `render_navbar()`. Nếu nâng cấp UI về sau, có thể chuyển dần sang left sidebar nhưng phải giữ đầy đủ module hiện tại.

### Sidebar / Main Navigation

Navigation dùng cho điều hướng chính của **Yoga/Gym Management System**.  
Mục tiêu là giúp nhân viên thao tác nhanh các nghiệp vụ hằng ngày: bán hàng, check-in, quản lý khách hàng, gói tập, PT, đồ uống, nguyên liệu và tồn kho theo từng cơ sở.

Source hiện tại đang dùng top navbar + mobile hamburger menu trong `auth.render_navbar()`. Nếu chuyển sang sidebar, cần giữ cùng cấu trúc menu và quyền truy cập.

#### Nhóm vận hành hằng ngày

Các mục nên có:

- **Bảng điều khiển** (`/dashboard`)  
  Tổng quan số liệu theo cơ sở đang chọn, doanh thu, giao dịch gần đây, gói sắp hết hạn, cảnh báo tồn kho thấp và fraud alerts nếu người dùng có quyền.

- **Bán hàng** (`/sales`)  
  Tạo giao dịch bán đồ uống/dinh dưỡng cho khách hàng, chọn đồ uống, số serving, gói trả trước nếu có và ghi nhận doanh thu.

- **Check-in** (`/checkin`)  
  Ghi nhận buổi tập/check-in theo gói tập đang hoạt động của khách hàng.

- **Khách hàng** (`/customers`)  
  Quản lý khách hàng theo cơ sở, tìm kiếm theo mã/tên/SĐT, thêm khách mới, cập nhật thông tin và kiểm tra lịch sử liên quan.

- **Gói trả trước** (`/packages`)  
  Tạo và quản lý gói tập/gói đồ uống trả trước của khách hàng, theo dõi tổng buổi, buổi còn lại, tổng ly và ly còn lại.

- **PT** (`/pt`)  
  Ghi nhận buổi PT, chọn khách hàng, trainer, bảng giá PT, thời lượng, doanh thu PT và dinh dưỡng đi kèm nếu có.

#### Nhóm sản phẩm và tồn kho

- **Đồ uống** (`/drinks`)  
  Quản lý đồ uống, giá mỗi serving, trạng thái hoạt động và công thức nguyên liệu.

- **Nguyên liệu** (`/ingredients`)  
   Quản lý nguyên liệu, đơn vị (`muỗng`, `nắp`, `gói`), tồn kho hiện tại, tồn kho tối thiểu và điều chỉnh tồn kho.  
   Thêm/sửa nguyên liệu dành cho **MANAGER** và **OWNER**.  
   Điều chỉnh tồn kho chỉ dành cho **OWNER**.

- **Sản phẩm** (`/products`)  
   Quản lý sản phẩm bán lẻ (thảm, áo, phụ kiện), giá bán, khuyến mãi, tồn kho và điều chỉnh tồn kho.

#### Nhóm quản lý gói

Các mục này phục vụ quản lý nâng cao, nên hiển thị cho **MANAGER** và **OWNER**:

- **Mẫu gói** (`/package-templates`)  
  Quản lý mẫu gói như `BASIC`, `FAT_LOSS`, `COMBO`, thời hạn, tổng buổi, tổng ly và giá tiền.

- **Nâng cấp gói** (`/packages/upgrade`)  
  Thực hiện nâng cấp gói cho khách hàng và tính tiền bù nếu có.

#### Nhóm quản trị

Các mục quản trị nên tách khỏi nghiệp vụ hằng ngày:

- **Nhật ký / Audit Log** (`/audit`)  
  Xem nhật ký hành động, lọc theo user, entity, action, xem hoạt động đáng nghi.  
  Chỉ hiển thị với **MANAGER** và **OWNER**.

- **Người dùng** (`/users`)  
  Quản lý tài khoản, vai trò, trạng thái hoạt động và cơ sở được phép truy cập.  
  Chỉ hiển thị với **OWNER**.

- **Cơ sở** (`/locations`)  
  Quản lý cơ sở/phòng tập, địa chỉ và trạng thái hoạt động.  
  Chỉ hiển thị với **OWNER**.

#### Location switcher

Vì source hiện tại hỗ trợ đa cơ sở qua `locations` và `user_locations`, navigation cần có:

- Badge hiển thị cơ sở hiện tại
- Nút hoặc menu **Đổi cơ sở**
- Dialog chọn cơ sở làm việc
- Không cho vào dashboard nếu chưa chọn cơ sở
- Khi đổi cơ sở, quay về dashboard hoặc reload dữ liệu theo cơ sở mới

#### Navigation cần

- Rõ trạng thái active của trang hiện tại
- Icon nhất quán, ưu tiên Lucide Icons hoặc Material Icons hiện có của NiceGUI/Quasar
- Label tiếng Việt ngắn gọn, dễ hiểu
- Không hiển thị menu người dùng không có quyền truy cập
- Nhóm vận hành đặt nổi bật hơn nhóm quản trị
- Có nút đăng xuất dễ thấy nhưng không gây nhầm với action nghiệp vụ
- Có thể thu gọn trên desktop nhưng vẫn giữ icon nhận diện
- Trên mobile/tablet có thể dùng hamburger menu hoặc drawer menu
- Không thêm quá nhiều nhóm menu gây rối

#### Gợi ý icon

- Bảng điều khiển: `LayoutDashboard` / `dashboard`
- Bán hàng: `BadgeDollarSign` / `point_of_sale`
- Check-in: `CheckCircle` / `check_circle`
- Khách hàng: `Users` / `groups`
- Gói trả trước: `PackageCheck` / `shopping_cart`
- PT: `Dumbbell` / `fitness_center`
- Đồ uống: `CupSoda` / `local_cafe`
- Nguyên liệu: `FlaskConical` / `science`
- Mẫu gói: `ClipboardList` / `list_alt`
- Nâng cấp gói: `ArrowUpCircle` / `upgrade`
- Nhật ký: `FileClock` / `history`
- Người dùng: `UserCog` / `manage_accounts`
- Cơ sở: `Building2` / `business`
- Đổi cơ sở: `MapPin` / `place`
- Đăng xuất: `LogOut` / `logout`

### Top Toolbar

Top toolbar/header nên chứa:

- Brand: **Quản lý Gym** hoặc tên sản phẩm thống nhất
- Tên trang hiện tại nếu layout chuyển sang sidebar
- Badge cơ sở đang làm việc
- Nút đổi cơ sở
- Quick actions quan trọng:
  - Bán hàng
  - Check-in
- Username hoặc user menu
- Role nếu cần cho quản trị
- Logout
- Thông báo hoặc trạng thái hệ thống nếu cần

Source hiện tại đã có top navbar trong `render_navbar()` gồm brand, location badge, username, mobile menu, quick actions bán hàng/check-in và logout. Khi cải tiến UI, không phá vỡ flow đăng nhập → chọn cơ sở → dashboard.

---

## Dashboard Goal

Dashboard chỉ nên cung cấp cái nhìn tổng quan nhanh theo **cơ sở đang chọn**.

Sử dụng **light Bento Grid layout** cho các widget tóm tắt.

Widget phù hợp với source hiện tại:

- Tổng khách hàng
- Doanh thu hôm nay
- Doanh thu tháng
- Giao dịch hôm nay
- Check-in hôm nay
- Gói sắp hết hạn
- Gói sắp hết buổi
- Nguyên liệu tồn kho thấp
- Hoạt động gần đây
- Fraud alerts cho MANAGER/OWNER

Nguyên tắc dashboard:

- Không nhồi quá nhiều thông tin
- Số liệu quan trọng phải thấy ngay
- Biểu đồ đơn giản, dễ hiểu
- Ưu tiên hành động nhanh nếu có vấn đề cần xử lý
- Không biến dashboard thành trang báo cáo phức tạp
- Mọi số liệu phải rõ đang tính theo cơ sở nào

---

## Data Pages Goal

Các trang quản lý dữ liệu quan trọng hơn dashboard.

Áp dụng cho:

- Khách hàng
- Gói trả trước
- PT
- Đồ uống
- Nguyên liệu
- Sản phẩm
- Mẫu gói
- Audit Log
- Người dùng
- Cơ sở

Ưu tiên:

- Search mạnh
- Filtering
- Sorting
- Pagination
- Bulk actions
- Sticky table headers
- Export capabilities
- Trạng thái rỗng rõ ràng
- Action buttons dễ tìm
- Badge trạng thái như Hoạt động/Vô hiệu, Sắp hết hạn, Tồn kho thấp

Không nên thay thế bảng bằng card nếu bảng giúp thao tác nhanh hơn.

Các trang dữ liệu cần có:

- Tiêu đề rõ ràng
- Mô tả ngắn nếu cần
- Thanh công cụ phía trên bảng
- Nút hành động chính nổi bật
- Bộ lọc dễ truy cập
- Table layout dễ scan
- Badge trạng thái
- Empty state thân thiện
- Loading state rõ ràng

---

## Forms Goal

Forms cần sạch sẽ, có tổ chức và giảm thao tác thừa.

Áp dụng cho:

- Đăng nhập
- Chọn cơ sở
- Tạo/sửa khách hàng
- Tạo/sửa đồ uống
- Tạo/sửa nguyên liệu
- Tạo/sửa sản phẩm
- Điều chỉnh tồn kho
- Tạo gói trả trước
- Tạo mẫu gói
- Nâng cấp gói
- Ghi nhận PT
- Tạo/sửa người dùng
- Tạo/sửa cơ sở

Nguyên tắc:

- Group các field liên quan thành section hoặc card
- Giữ label dễ đọc
- Khoảng cách nhất quán
- Hiển thị validation rõ ràng
- Tối thiểu số click
- Field bắt buộc phải rõ
- Error message phải dễ hiểu
- Submit button dễ nhận biết
- Action nguy hiểm cần confirmation hoặc cảnh báo rõ

Với workflow dài:

- Dùng multi-step form
- Hoặc chia thành các card rõ ràng
- Không gom quá nhiều field vào một khối lớn

---

## Components

Ưu tiên các component SaaS hiện đại:

- Cards
- Tables
- Dialogs
- Drawers
- Toast Notifications
- Tabs
- Badges
- Dropdown Menus
- Command Bar nếu cần
- Skeleton Loading
- Empty States
- Location Switcher
- Role-aware Navigation

Component cần nhất quán về:

- Radius
- Spacing
- Typography
- Icon style
- Border
- Shadow
- Hover state
- Disabled state

---

## Typography

Font ưu tiên:

- Inter
- Geist

Không dùng font trang trí.

Typography hierarchy cần rõ:

- Page title nổi bật
- Section title dễ scan
- Label form rõ ràng
- Body text dễ đọc
- Helper text nhỏ hơn nhưng không quá mờ
- Error text dễ nhận biết

---

## Icons

Dùng icon nhất quán.

Ưu tiên:

- Lucide Icons nếu xây dựng UI custom
- Material Icons/Quasar Icons nếu tiếp tục dùng NiceGUI mặc định

Nguyên tắc dùng icon:

- Icon hỗ trợ nhận diện, không dùng để trang trí
- Kích thước nhất quán
- Không dùng nhiều style icon khác nhau
- Icon đi kèm label ở các hành động quan trọng
- Icon-only button phải có tooltip hoặc aria-label nếu áp dụng

---

## Interaction Design

Tương tác cần nhanh, rõ và dễ đoán.

Nên có:

- Hover state nhẹ
- Focus state rõ ràng
- Loading state khi xử lý
- Toast notification sau hành động
- Confirmation dialog cho hành động nguy hiểm
- Empty state có hướng dẫn tiếp theo
- Error message cụ thể
- Enter-to-search cho các ô tìm kiếm chính
- Disable button hoặc báo rõ khi thiếu quyền

Animation:

- Subtle
- 150–250ms
- Không gây chậm thao tác
- Không dùng animation trang trí

---

## Responsive Strategy

Ưu tiên desktop.

### Desktop

- Là nền tảng chính
- Tối ưu cho thao tác nhanh
- Table đầy đủ tính năng
- Navigation rõ ràng
- Location badge luôn nhìn thấy

### Tablet

- Vẫn đầy đủ chức năng chính
- Layout có thể co lại
- Table vẫn cần dễ thao tác
- Navigation có thể chuyển thành hamburger/drawer

### Mobile

- Chỉ cần các chức năng quản lý thiết yếu
- Không hy sinh trải nghiệm desktop vì mobile
- Có thể đơn giản hóa bảng hoặc dùng layout phù hợp hơn
- Các nghiệp vụ nhanh như bán hàng/check-in phải dễ mở

---

## Visual Quality Bar

Ứng dụng cần tạo cảm giác tương đương các sản phẩm SaaS hiện đại như:

- Linear
- Stripe Dashboard
- Notion

Nhưng vẫn giữ thẩm mỹ:

- Calm
- Elegant
- Comfortable
- Premium
- Trustworthy

---

## Implementation Guidance

Khi tạo hoặc chỉnh UI, luôn ưu tiên theo thứ tự:

1. Tính rõ ràng
2. Tốc độ thao tác
3. Tính nhất quán
4. Khả năng đọc dữ liệu
5. Tính đúng quyền và đúng cơ sở
6. Tính thẩm mỹ
7. Hiệu ứng và trang trí

Không thêm component chỉ để làm đẹp nếu không cải thiện trải nghiệm sử dụng.

Không phá vỡ các flow hiện tại:

- Login → Select Location → Dashboard
- Bán hàng phải gắn với khách hàng, đồ uống và cơ sở
- Check-in phải gắn với khách hàng/gói tập
- Điều chỉnh tồn kho phải ghi nhận audit
- Người dùng chỉ thao tác trong cơ sở được gán

---

## Design Checklist

Trước khi hoàn thành một màn hình, kiểm tra:

- [ ] Người dùng có hiểu mục tiêu màn hình trong 5 giây không?
- [ ] Hành động chính có dễ thấy không?
- [ ] Cơ sở đang làm việc có rõ không?
- [ ] Người dùng không thấy action vượt quyền không?
- [ ] Có quá nhiều màu hoặc hiệu ứng không?
- [ ] Khoảng cách có nhất quán không?
- [ ] Table hoặc form có dễ dùng không?
- [ ] Error và success state có rõ không?
- [ ] Giao diện có phù hợp làm việc lâu không?
- [ ] Desktop experience có được ưu tiên không?
- [ ] Component có nhất quán với toàn hệ thống không?
- [ ] UI có giữ cảm giác calm, clean, premium không?
