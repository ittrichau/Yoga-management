FROM python:3.13-slim

WORKDIR /app

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .
COPY static ./static

# Tạo thư mục data cho SQLite
RUN mkdir -p /app/data

# Render cung cấp PORT qua env; mặc định 8080 cho local/docker-compose
ENV PORT=8080
EXPOSE 8080

# Chạy trực tiếp bằng python main.py để NiceGUI ui.run() bind port đúng
CMD ["python", "main.py"]
