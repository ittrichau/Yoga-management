---
name: Railway Deploy
alwaysApply: false
---

# Deploy lên Railway

Chỉ đọc file này khi task liên quan deploy, environment, Docker hoặc Railway.

## Tổng quan

Ứng dụng dùng Python 3.13+, FastAPI, NiceGUI, bcrypt, PyJWT.

Database tự detect theo môi trường:

- Không có `DATABASE_URL` → dùng SQLite local tại `data/gym_nutrition.db`.
- Có `DATABASE_URL` → dùng PostgreSQL trên Railway.

Khi app start, `main.py` chạy `init_db()`, `migrate_schema()` và `seed_defaults()` để tự tạo schema, migration cơ bản và dữ liệu mặc định.

## Railway Setup

1. Push code lên GitHub.
2. Tạo project Railway từ GitHub repository.
3. Thêm PostgreSQL service.
4. Railway tự inject `DATABASE_URL` vào app service.
5. App build bằng `Dockerfile`.

## Environment Variables

| Key                   | Gợi ý                                   | Ghi chú                              |
| --------------------- | --------------------------------------- | ------------------------------------ |
| `SECRET_KEY`          | Chuỗi ngẫu nhiên mạnh, ít nhất 32 ký tự | Dùng ký JWT                          |
| `STORAGE_SECRET`      | Chuỗi ngẫu nhiên mạnh                   | Dùng cho NiceGUI storage             |
| `SUPER_USER_USERNAME` | `admin`                                 | Username mặc định                    |
| `SUPER_USER_PASSWORD` | Mật khẩu mạnh                           | Không dùng `admin123` khi production |
| `PORT`                | `8080`                                  | Railway thường tự set                |
| `HOST`                | `0.0.0.0`                               | Source đã default `0.0.0.0`          |

## Local vs Production

- Local dev: không có `DATABASE_URL` → SQLite.
- Railway: có `DATABASE_URL` → PostgreSQL.
- Không commit file database trong `data/`.
- Không hard-code secret trong source.

## Static Files

Source dùng `/static/style.css` qua `app.add_static_files("/static", static_dir)`.

Dockerfile cần copy static:

```dockerfile
COPY static ./static
```

Nếu deploy lên Railway mà UI mất CSS, kiểm tra Dockerfile có dòng trên.

## Production Notes

- Đổi `SECRET_KEY` và `STORAGE_SECRET` thành chuỗi mạnh.
- Đổi `SUPER_USER_PASSWORD`.
- Vô hiệu hóa user demo nếu không cần.
- Backup PostgreSQL định kỳ nếu dùng production thật.
- Kiểm tra migration/seed không làm mất dữ liệu production.
