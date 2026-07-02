# Deploy lên Railway

## Tổng quan

Ứng dụng hiện tại là **Yoga/Gym Management System** dùng Python 3.13, FastAPI, NiceGUI, bcrypt, PyJWT.

Database được tự detect theo môi trường:

- Không có `DATABASE_URL` → dùng SQLite local tại `data/gym_nutrition.db`
- Có `DATABASE_URL` → dùng PostgreSQL trên Railway

Khi app start, `main.py` chạy `init_db()`, `migrate_schema()` và `seed_defaults()` để tự tạo schema, migration cơ bản và dữ liệu mặc định.

## Yêu cầu

- Tài khoản [Railway](https://railway.app/)
- Kết nối GitHub repository

## Các bước

### 1. Push code lên GitHub

```bash
git add .
git commit -m "Ready for Railway deploy"
git push origin main
```

### 2. Tạo project trên Railway

1. Vào [Railway Dashboard](https://railway.app/dashboard)
2. Click **New Project** → **Deploy from GitHub repo**
3. Chọn repository của bạn

### 3. Thêm PostgreSQL service

1. Trong project, click **New** → **Database** → **PostgreSQL**
2. Railway tự động tạo PostgreSQL và inject `DATABASE_URL` vào app

### 4. Thêm biến môi trường (Variables)

Vào tab **Variables** của service app, thêm:

| Key                   | Value                                   | Ghi chú                                 |
| --------------------- | --------------------------------------- | --------------------------------------- |
| `SECRET_KEY`          | Chuỗi ngẫu nhiên mạnh, ít nhất 32 ký tự | Dùng ký JWT                             |
| `STORAGE_SECRET`      | Chuỗi ngẫu nhiên mạnh                   | Dùng cho NiceGUI storage                |
| `SUPER_USER_USERNAME` | `admin`                                 | Username mặc định                       |
| `SUPER_USER_PASSWORD` | Mật khẩu mạnh                           | Không nên giữ `admin123` khi production |
| `PORT`                | `8080`                                  | Railway thường tự set, chỉ thêm nếu cần |
| `HOST`                | `0.0.0.0`                               | Source đã default `0.0.0.0`             |

`DATABASE_URL` được Railway tự động inject từ PostgreSQL service, không cần thêm thủ công.

### 5. Deploy

Railway tự động build Dockerfile và deploy. Mỗi lần push code mới lên GitHub, Railway sẽ tự động redeploy.

### 6. Truy cập

Sau khi deploy thành công, Railway cung cấp URL dạng `https://xxx.railway.app`. Vào URL đó để truy cập ứng dụng.

**Đăng nhập mặc định:** `admin` / `admin123`

Source hiện tại cũng seed user demo: `giangvien1` / `123456` với role `STAFF`.

Sau khi deploy production, nên đổi mật khẩu hoặc vô hiệu hóa user demo nếu không cần.

## Cấu trúc project sau khi deploy

```
├── Dockerfile          # Railway dùng file này để build
├── requirements.txt    # FastAPI, NiceGUI, bcrypt, PyJWT, psycopg2-binary
├── main.py             # App startup, register routers, ui.run
├── settings.py         # Đọc env: DATABASE_URL, SECRET_KEY, STORAGE_SECRET...
├── database.py         # Tự detect SQLite local hoặc PostgreSQL Railway
├── auth.py             # Login, JWT, users, locations, navbar
├── customer.py         # Khách hàng
├── checkin.py          # Check-in buổi tập
├── drink.py            # Đồ uống
├── ingredient.py       # Nguyên liệu/tồn kho
├── package.py          # Gói trả trước
├── package_template.py # Mẫu gói
├── package_upgrade.py  # Nâng cấp gói
├── transaction.py      # Bán hàng/giao dịch
├── pt.py               # PT sessions/rates
├── audit.py            # Nhật ký hệ thống
├── dashboard.py        # Dashboard, export CSV
├── static/             # CSS/UI assets
└── data/               # Chỉ dùng khi local dev SQLite
```

## Các route UI chính

| Route                | Chức năng                   |
| -------------------- | --------------------------- |
| `/login`             | Đăng nhập                   |
| `/select-location`   | Chọn cơ sở làm việc         |
| `/dashboard`         | Bảng điều khiển             |
| `/customers`         | Quản lý khách hàng          |
| `/checkin`           | Check-in buổi tập           |
| `/packages`          | Gói trả trước               |
| `/packages/upgrade`  | Nâng cấp gói                |
| `/package-templates` | Mẫu gói                     |
| `/pt`                | Ghi nhận PT                 |
| `/drinks`            | Quản lý đồ uống             |
| `/ingredients`       | Quản lý nguyên liệu/tồn kho |
| `/sales`             | Bán hàng                    |
| `/audit`             | Nhật ký hệ thống            |
| `/users`             | Quản lý người dùng          |
| `/locations`         | Quản lý cơ sở               |

## Cách hoạt động

- **Local dev**: Không có `DATABASE_URL` → dùng SQLite (`data/gym_nutrition.db`)
- **Railway**: Có `DATABASE_URL` → dùng PostgreSQL, schema tự tạo, seed data tự động

## Lưu ý

### Static files

Source hiện tại có dùng `/static/style.css` qua `app.add_static_files("/static", static_dir)`, nhưng Dockerfile hiện tại đang dùng:

```dockerfile
COPY *.py .
```

Dòng này chỉ copy file `.py`, không copy thư mục `static/`.

Nếu deploy lên Railway mà UI mất CSS, cần cập nhật Dockerfile để copy thêm static:

```dockerfile
COPY static ./static
```

### Production

- Đổi `SECRET_KEY` thành chuỗi ngẫu nhiên mạnh trước khi deploy
- Đổi `STORAGE_SECRET` thành chuỗi ngẫu nhiên mạnh trước khi deploy
- Đổi `SUPER_USER_PASSWORD` hoặc tạo user mới sau khi deploy
- Vô hiệu hóa user demo nếu không cần
- Backup PostgreSQL định kỳ nếu dùng production thật
- PostgreSQL trên Railway có giới hạn dung lượng theo plan
