# Deploy lên Railway

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

| Key                   | Value                                 |
| --------------------- | ------------------------------------- |
| `SECRET_KEY`          | Chuỗi ngẫu nhiên ít nhất 32 ký tự     |
| `STORAGE_SECRET`      | gym-nutrition-secret (hoặc tùy chỉnh) |
| `SUPER_USER_USERNAME` | admin                                 |
| `SUPER_USER_PASSWORD` | admin123                              |

`DATABASE_URL` được Railway tự động inject từ PostgreSQL service, không cần thêm thủ công.

### 5. Deploy

Railway tự động build Dockerfile và deploy. Mỗi lần push code mới lên GitHub, Railway sẽ tự động redeploy.

### 6. Truy cập

Sau khi deploy thành công, Railway cung cấp URL dạng `https://xxx.railway.app`. Vào URL đó để truy cập ứng dụng.

**Đăng nhập mặc định:** `admin` / `admin123`

## Cấu trúc project sau khi deploy

```
├── Dockerfile          # Railway dùng file này để build
├── requirements.txt    # bcrypt, PyJWT, psycopg2-binary
├── main.py
├── settings.py         # Đọc DATABASE_URL từ env
├── database.py         # Tự detect SQLite (local) hoặc PostgreSQL (Railway)
├── auth.py
├── customer.py
├── drink.py
├── ingredient.py
├── package.py
├── transaction.py
├── audit.py
├── dashboard.py
└── data/               # Chỉ dùng khi local dev (SQLite)
```

## Cách hoạt động

- **Local dev**: Không có `DATABASE_URL` → dùng SQLite (`data/gym_nutrition.db`)
- **Railway**: Có `DATABASE_URL` → dùng PostgreSQL, schema tự tạo, seed data tự động

## Lưu ý

- Đổi `SECRET_KEY` thành chuỗi ngẫu nhiên mạnh trước khi deploy
- Đổi `SUPER_USER_PASSWORD` hoặc tạo user mới sau khi deploy
- PostgreSQL trên Railway có giới hạn dung lượng theo plan (512MB free)
