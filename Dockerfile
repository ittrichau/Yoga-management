FROM python:3.13-slim

WORKDIR /app

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .

# Tạo thư mục data cho SQLite
RUN mkdir -p /app/data

EXPOSE 8080

# Chạy với uvicorn production mode (không reload)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]