# Lộ trình xây dựng hệ thống quản lý phòng cho thuê

## 1. Mục tiêu

Xây dựng hệ thống quản lý phòng cho thuê có chức năng tương tự dự án tham khảo `QL_PhongTro`, nhưng được viết bằng Python và sử dụng PostgreSQL.

Hệ thống phục vụ ba nhóm người dùng chính:

- Quản trị viên: quản lý toàn bộ hệ thống và tài khoản.
- Chủ nhà/nhân viên: quản lý tòa nhà, phòng, khách thuê, hợp đồng, hóa đơn và sự cố.
- Khách thuê: xem hợp đồng, hóa đơn, thanh toán, thông báo và gửi yêu cầu hỗ trợ.

## 2. Phạm vi chức năng

### Chức năng cốt lõi (MVP)

- Đăng nhập, đăng xuất, đổi mật khẩu và phân quyền theo vai trò.
- Quản lý tòa nhà/khu trọ.
- Quản lý phòng, trạng thái phòng, giá thuê và tiện nghi.
- Quản lý hồ sơ khách thuê.
- Quản lý hợp đồng và thành viên cùng phòng.
- Ghi chỉ số điện, nước theo tháng.
- Lập hóa đơn và tự động tính tiền phòng, điện, nước, dịch vụ.
- Ghi nhận thanh toán, công nợ và xuất phiếu thu.
- Dashboard thống kê cơ bản.

### Chức năng mở rộng

- Upload ảnh phòng, CCCD, biên lai và file hợp đồng.
- Quản lý sự cố và tiến độ xử lý.
- Thông báo cho khách thuê theo phòng hoặc tòa nhà.
- Cổng thông tin riêng cho khách thuê.
- Xuất Excel/PDF và báo cáo doanh thu.
- Tự động tạo hóa đơn định kỳ.
- Email/thông báo thời gian thực.
- Sao lưu, nhật ký hoạt động và phục hồi dữ liệu.

## 3. Công nghệ đề xuất

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.12+ |
| Web framework | Django 5.x |
| REST API | Django REST Framework |
| Cơ sở dữ liệu | PostgreSQL 16+ |
| ORM và migration | Django ORM, Django migrations |
| Giao diện | Django Templates, Bootstrap 5, HTMX, Alpine.js |
| Xác thực | Django Authentication, session/cookie bảo mật |
| Tác vụ nền | Celery + Redis (giai đoạn mở rộng) |
| Lưu file | Local khi phát triển; S3/Cloudinary khi production |
| Kiểm thử | pytest, pytest-django, factory_boy |
| Chất lượng code | Ruff, Black, mypy, pre-commit |
| Đóng gói | Docker, Docker Compose |
| Triển khai | Gunicorn, Nginx, PostgreSQL |

Không đưa mật khẩu hoặc chuỗi kết nối vào Git. Cấu hình được đọc từ `.env`; repository chỉ lưu `.env.example`.

## 4. Kiến trúc dự án dự kiến

```text
QL_PhongChoThue/
├── config/                  # settings, URL, ASGI/WSGI
├── apps/
│   ├── accounts/            # tài khoản, vai trò, phân quyền
│   ├── properties/          # tòa nhà, phòng, tiện nghi, dịch vụ
│   ├── tenants/             # khách thuê, người ở cùng
│   ├── contracts/           # hợp đồng và phụ lục
│   ├── meters/              # chỉ số điện, nước
│   ├── billing/             # hóa đơn, chi tiết hóa đơn, thanh toán
│   ├── maintenance/         # sự cố và xử lý
│   ├── notifications/       # thông báo
│   ├── reports/             # dashboard, thống kê, xuất dữ liệu
│   └── audit/               # nhật ký thao tác
├── templates/               # giao diện HTML dùng chung
├── static/                  # CSS, JavaScript, hình tĩnh
├── media/                   # file upload ở môi trường phát triển
├── tests/                   # test tích hợp/toàn hệ thống
├── scripts/                 # seed, backup và tác vụ quản trị
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── pyproject.toml
├── .env.example
└── README.md
```

Mỗi Django app nên phân tách tối thiểu thành `models`, `services`, `selectors`, `forms`/`serializers`, `views`, `urls`, `admin` và `tests`. Quy tắc nghiệp vụ quan trọng đặt trong service thay vì nhồi vào view hoặc signal.

## 5. Thiết kế cơ sở dữ liệu PostgreSQL

### Các bảng chính

| Bảng | Mục đích và quan hệ chính |
|---|---|
| `users` | Tài khoản, vai trò, trạng thái; dùng custom user model ngay từ đầu |
| `buildings` | Tòa nhà/khu trọ, địa chỉ, chủ sở hữu |
| `rooms` | Thuộc tòa nhà; số phòng là duy nhất trong từng tòa nhà |
| `amenities` | Danh mục tiện nghi; quan hệ nhiều-nhiều với phòng |
| `services` | Điện, nước, internet, rác và cách tính phí |
| `tenants` | Hồ sơ khách thuê; liên kết tài khoản nếu có quyền đăng nhập |
| `contracts` | Liên kết phòng và người đại diện; thời hạn, tiền cọc, giá thuê |
| `contract_members` | Danh sách người ở trong từng hợp đồng |
| `meter_readings` | Chỉ số đầu/cuối theo phòng, loại đồng hồ và kỳ tính tiền |
| `invoices` | Hóa đơn theo hợp đồng và kỳ; tổng tiền, hạn trả, trạng thái |
| `invoice_items` | Chi tiết tiền phòng, điện, nước, dịch vụ và điều chỉnh |
| `payments` | Giao dịch thanh toán; hỗ trợ thanh toán nhiều lần cho một hóa đơn |
| `incidents` | Sự cố, mức ưu tiên, người phụ trách và trạng thái xử lý |
| `notifications` | Nội dung, đối tượng nhận, thời gian gửi và trạng thái đọc |
| `attachments` | Metadata file đính kèm cho hợp đồng, sự cố, thanh toán... |
| `audit_logs` | Người thao tác, hành động, đối tượng, thời gian và dữ liệu thay đổi |

### Ràng buộc bắt buộc

- Dùng khóa chính `UUID` cho các thực thể nghiệp vụ.
- Tiền tệ dùng `NUMERIC(14, 2)`, tuyệt đối không dùng số thực.
- Mọi thời điểm lưu theo timezone; hiển thị theo `Asia/Ho_Chi_Minh`.
- Một phòng không được có hai hợp đồng đang hiệu lực chồng thời gian.
- Mỗi phòng, loại đồng hồ và kỳ chỉ có một bản ghi chỉ số.
- Chỉ số cuối không được nhỏ hơn chỉ số đầu.
- Mỗi hợp đồng chỉ có một hóa đơn cho một kỳ, trừ hóa đơn điều chỉnh.
- Tổng các khoản thanh toán hợp lệ quyết định số dư và trạng thái hóa đơn.
- Không xóa cứng dữ liệu tài chính; dùng trạng thái hủy và audit log.
- Tạo index cho khóa ngoại, trạng thái, kỳ hóa đơn, hạn thanh toán và trường tìm kiếm phổ biến.

## 6. Luồng nghiệp vụ trọng tâm

### Cho thuê phòng

1. Tạo hồ sơ khách thuê.
2. Chọn phòng đang trống.
3. Lập hợp đồng, tiền cọc, ngày bắt đầu/kết thúc và dịch vụ áp dụng.
4. Thêm người ở cùng và tài liệu liên quan.
5. Kích hoạt hợp đồng trong transaction; chuyển phòng sang `đang thuê`.

### Lập hóa đơn tháng

1. Chốt kỳ hóa đơn và ghi chỉ số điện/nước.
2. Kiểm tra chỉ số hợp lệ với kỳ trước.
3. Tính tiền phòng, lượng tiêu thụ, dịch vụ cố định và khoản phát sinh.
4. Lưu `invoice` và `invoice_items` trong cùng transaction.
5. Phát hành hóa đơn và gửi thông báo.

### Thanh toán

1. Chọn hóa đơn và nhập số tiền, phương thức, mã tham chiếu.
2. Khóa bản ghi hóa đơn khi cập nhật để tránh ghi nhận đồng thời sai số dư.
3. Tính lại số đã trả/còn nợ.
4. Chuyển trạng thái sang chưa trả, trả một phần hoặc đã trả.
5. Sinh phiếu thu và ghi audit log.

## 7. REST API dự kiến

API dùng tiền tố `/api/v1/` và được mô tả bằng OpenAPI.

- `/auth/`: đăng nhập, đăng xuất, hồ sơ và đổi mật khẩu.
- `/users/`: tài khoản và phân quyền.
- `/buildings/`, `/rooms/`, `/amenities/`, `/services/`.
- `/tenants/`, `/contracts/`, `/contracts/{id}/terminate/`.
- `/meter-readings/` và `/meter-readings/previous/`.
- `/invoices/`, `/invoices/generate/`, `/invoices/{id}/issue/`.
- `/payments/`, `/payments/{id}/receipt/`.
- `/incidents/`, `/notifications/`.
- `/dashboard/summary/`, `/reports/revenue/`, `/reports/debt/`.

Các endpoint danh sách phải có phân trang, tìm kiếm, sắp xếp và bộ lọc. Quyền truy cập được kiểm tra theo vai trò và phạm vi tòa nhà, không chỉ ẩn nút ở giao diện.

## 8. Lộ trình triển khai

### Giai đoạn 0 — Chốt yêu cầu và tiêu chí nghiệm thu

- [ ] Xác định mô hình một chủ nhà hay nhiều chủ nhà.
- [ ] Chốt vai trò và ma trận quyền.
- [ ] Chốt cách tính điện, nước, dịch vụ, tiền cọc và phạt trễ.
- [ ] Vẽ ERD và wireframe các màn hình chính.
- [ ] Lập backlog, ưu tiên MVP và dữ liệu mẫu.

**Hoàn thành khi:** ERD, luồng nghiệp vụ, ma trận quyền và danh sách màn hình được duyệt.

### Giai đoạn 1 — Khởi tạo nền tảng

- [ ] Tạo virtual environment và dự án Django.
- [ ] Tạo cấu trúc app theo kiến trúc ở mục 4.
- [ ] Cấu hình PostgreSQL qua biến `DATABASE_URL`.
- [ ] Thêm Docker Compose cho web, PostgreSQL và Redis tùy chọn.
- [ ] Cấu hình Ruff, Black, mypy, pytest và pre-commit.
- [ ] Tạo custom user model, đăng nhập và phân quyền nền tảng.
- [ ] Tạo CI chạy lint, migration check và test.

**Hoàn thành khi:** ứng dụng khởi động được, kết nối PostgreSQL, migration chạy sạch và test nền tảng đạt.

### Giai đoạn 2 — Tòa nhà, phòng và dịch vụ

- [ ] CRUD tòa nhà và phòng.
- [ ] Trạng thái phòng: trống, đã đặt, đang thuê, bảo trì, ngừng sử dụng.
- [ ] Tiện nghi, hình ảnh và biểu giá dịch vụ.
- [ ] Danh sách, tìm kiếm, lọc và phân trang.
- [ ] Test quyền truy cập và ràng buộc số phòng.

**Hoàn thành khi:** chủ nhà quản lý được danh mục phòng và biết chính xác tình trạng sử dụng.

### Giai đoạn 3 — Khách thuê và hợp đồng

- [ ] CRUD khách thuê, CCCD và liên hệ khẩn cấp.
- [ ] Tạo hợp đồng, người ở cùng và tài liệu đính kèm.
- [ ] Gia hạn, thanh lý/hủy hợp đồng.
- [ ] Ngăn hợp đồng chồng thời gian và đồng bộ trạng thái phòng.
- [ ] Trang lịch sử thuê của khách/phòng.

**Hoàn thành khi:** toàn bộ vòng đời nhận phòng đến trả phòng hoạt động trong transaction và có test.

### Giai đoạn 4 — Chỉ số, hóa đơn và thanh toán

- [ ] Nhập chỉ số điện/nước và đối chiếu kỳ trước.
- [ ] Xây dựng dịch vụ tính hóa đơn có thể kiểm thử độc lập.
- [ ] Tạo hóa đơn thủ công và hàng loạt theo tháng.
- [ ] Ghi nhận thanh toán một phần/toàn phần và công nợ.
- [ ] Xuất hóa đơn, phiếu thu PDF và dữ liệu Excel.
- [ ] Kiểm thử làm tròn tiền, tính lặp an toàn và thao tác đồng thời.

**Hoàn thành khi:** một kỳ thu tiền có thể chạy từ chỉ số đến thanh toán và đối soát chính xác.

### Giai đoạn 5 — Dashboard, sự cố và thông báo

- [ ] Dashboard công suất phòng, doanh thu, công nợ và hợp đồng sắp hết hạn.
- [ ] Quy trình tiếp nhận, phân công và đóng sự cố.
- [ ] Thông báo theo người, phòng hoặc tòa nhà.
- [ ] Cổng khách thuê để xem dữ liệu thuộc chính mình.

**Hoàn thành khi:** số liệu dashboard đối chiếu đúng với dữ liệu giao dịch và khách thuê không xem được dữ liệu người khác.

### Giai đoạn 6 — Tự động hóa và vận hành

- [ ] Celery/Redis cho tạo hóa đơn định kỳ và gửi email.
- [ ] Theo dõi lỗi, log có cấu trúc và health check.
- [ ] Backup PostgreSQL tự động; diễn tập restore.
- [ ] Giới hạn upload, kiểm tra loại file và lưu object storage.
- [ ] Docker production, Nginx, HTTPS và cấu hình bảo mật.
- [ ] Tài liệu cài đặt, vận hành và hướng dẫn người dùng.

**Hoàn thành khi:** staging chạy ổn định, restore backup thành công và checklist phát hành đạt.

## 9. Chiến lược kiểm thử

- Unit test: tính điện/nước, tổng hóa đơn, công nợ, trạng thái hợp đồng/phòng.
- Model test: constraint, validation, index và quy tắc xóa dữ liệu.
- API test: xác thực, phân quyền, lọc, phân trang và mã lỗi.
- Integration test: nhận phòng, xuất hóa đơn, thanh toán, trả phòng.
- End-to-end smoke test: đăng nhập và hoàn thành luồng nghiệp vụ chính.
- Migration test: dựng database mới hoàn toàn và nâng cấp từ phiên bản liền trước.

Mục tiêu ban đầu: 80% coverage cho lớp nghiệp vụ; 100% cho hàm tính tiền và cập nhật công nợ.

## 10. Bảo mật và an toàn dữ liệu

- Hash mật khẩu bằng cơ chế chuẩn của Django; không tự viết thuật toán mật khẩu.
- CSRF, secure cookie, HTTPS, giới hạn đăng nhập và khóa tạm thời khi thử sai nhiều lần.
- Kiểm tra quyền ở backend cho mọi thao tác và mọi đối tượng.
- Dữ liệu nhạy cảm như CCCD chỉ hiển thị cho vai trò cần thiết.
- Validate file upload, đổi tên file và không cho thực thi file tải lên.
- Audit các thao tác với hợp đồng, hóa đơn, thanh toán và quyền người dùng.
- Backup mã hóa, quy định thời gian lưu và kiểm tra phục hồi định kỳ.

## 11. Dữ liệu mẫu và tiêu chí bàn giao MVP

Dữ liệu seed tối thiểu gồm 1 quản trị viên, 2 tòa nhà, 10 phòng, 5 khách thuê, hợp đồng ở nhiều trạng thái, chỉ số hai kỳ, hóa đơn và thanh toán mẫu.

MVP chỉ được xem là hoàn thành khi:

- Cài mới theo README và chạy bằng một quy trình rõ ràng.
- Migration có thể chạy trên PostgreSQL trống.
- Không có secret trong Git.
- Luồng phòng → khách → hợp đồng → chỉ số → hóa đơn → thanh toán chạy trọn vẹn.
- Phân quyền được kiểm thử tự động.
- Báo cáo doanh thu và công nợ khớp với giao dịch.
- Test, lint và kiểm tra migration đều đạt.
- Có quy trình backup và restore đã được thử nghiệm.

## 12. Thứ tự triển khai ngay tiếp theo

1. Chốt các quyết định ở Giai đoạn 0, đặc biệt là mô hình nhiều chủ nhà và cách tính phí.
2. Tạo skeleton Django, Docker Compose và PostgreSQL.
3. Thiết kế ERD chi tiết rồi tạo migration đầu tiên.
4. Hoàn thành tài khoản/phân quyền trước khi viết các module nghiệp vụ.
5. Phát triển theo từng lát cắt có test, không sao chép trực tiếp cấu trúc MongoDB sang PostgreSQL.

