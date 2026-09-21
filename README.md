# QL Phòng Cho Thuê

Hệ thống quản lý phòng cho thuê viết bằng Python/Django và PostgreSQL. Phiên bản hiện tại cung cấp nền tảng MVP gồm tài khoản, tòa nhà, phòng, khách thuê, hợp đồng, chỉ số điện nước, hóa đơn, thanh toán, sự cố, dashboard và Django Admin.

## Chạy bằng Docker

Yêu cầu Docker có Compose plugin hoặc chương trình `docker-compose`.

```bash
docker compose up --build -d
docker compose exec web python manage.py seed_demo
```

Nếu máy dùng Docker Compose độc lập, thay `docker compose` bằng `docker-compose`.

Truy cập `http://localhost:8000`. Dữ liệu demo tạo hai tài khoản:

- Quản trị: `admin` / `Admin@123456`
- Người thuê: `khachthue` / `Khach@123456`

Phải đổi các mật khẩu này ngay nếu triển khai thật.

## Chạy trực tiếp

1. Tạo PostgreSQL database và user.
2. Tạo virtual environment và cài thư viện:

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

3. Sao chép `.env.example` thành `.env`, sau đó nạp các biến môi trường bằng công cụ phù hợp với hệ điều hành.
4. Chạy migration, tạo dữ liệu mẫu và khởi động:

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

## Lệnh kiểm tra

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
$env:DJANGO_TEST_SQLITE="true"; python manage.py test  # PowerShell
ruff check .
```

## Lưu ý production

- Thay toàn bộ secret/mật khẩu mặc định và đặt `DJANGO_DEBUG=false`.
- Chỉ cho phép hostname thực trong `DJANGO_ALLOWED_HOSTS`.
- Chạy sau HTTPS, dùng object storage cho file và backup PostgreSQL định kỳ.
- Không dùng tài khoản hoặc mật khẩu demo ở môi trường thật.

Xem kế hoạch đầy đủ tại [LO_TRINH_XAY_DUNG.md](LO_TRINH_XAY_DUNG.md).
