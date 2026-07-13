# 1. Image nền: Python 3.12 bản gọn nhẹ
FROM python:3.12-slim

# 2. Thư mục làm việc bên trong container
WORKDIR /app

# 3. Copy requirements TRƯỚC (để tận dụng cache)
COPY requirements.txt .

# 4. Cài thư viện
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy code vào sau
COPY app.py .

# 6. Khai báo port app lắng nghe (mang tính tài liệu)
EXPOSE 5000

# 7. Lệnh chạy khi container khởi động
CMD ["python", "app.py"]