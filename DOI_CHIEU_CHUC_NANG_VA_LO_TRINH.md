# Đối chiếu chức năng và lộ trình hoàn thiện hệ thống

## 1. Phạm vi đối chiếu

- Tài liệu nguồn: `V1_1150080030_NguyenVanPhu_CNPM1_DECUONGDATN - Phú Nguyễn Văn.docx`.
- Hệ thống hiện tại: dự án Django/PostgreSQL `QL_PhongChoThue`.
- Dự án `QL_PhongTro` dùng Next.js/MongoDB được xem là dự án tham khảo cũ, không phải hệ thống triển khai chính trong đề cương.
- Ngày đánh giá: 22/10/2026.

## 2. Kết luận tổng quan

Hệ thống đã triển khai phần lớn nghiệp vụ quản lý nhà cho thuê: tài khoản, phân quyền, tòa nhà, phòng, người thuê, hợp đồng, dịch vụ, điện nước, hóa đơn, thanh toán, thông báo, sự cố, cổng người thuê và chat thời gian thực.

Các thành phần tạo nên trọng tâm nghiên cứu của đề tài hiện chưa được triển khai: quản lý camera, YOLO phát hiện lửa/khói, Temporal Sliding Window, sự kiện cảnh báo cháy, Indoor Map, liên kết cảnh báo với bản đồ, Dijkstra tìm đường thoát và Random Forest gợi ý giá thuê.

Ước lượng theo nhóm chức năng:

- Hoàn thành tương đối: khoảng 55%.
- Đã triển khai nhưng chưa đáp ứng đầy đủ đề cương: khoảng 15%.
- Chưa triển khai: khoảng 30%; đây là nhóm có độ khó và giá trị nghiên cứu cao nhất.

## 3. Ma trận đối chiếu chức năng

| Nhóm chức năng | Trạng thái | Đánh giá hiện tại | Việc còn thiếu |
|---|---|---|---|
| Đăng nhập, đăng xuất, hồ sơ, đổi mật khẩu | Đã làm | Có xác thực Django, hồ sơ và đổi mật khẩu | Hoàn thiện kiểm thử môi trường triển khai |
| Quản lý tài khoản | Đã làm | Tạo, sửa, khóa/mở, đặt lại mật khẩu, lịch sử đăng nhập và audit | Có thể bổ sung chính sách khóa tự động khi đăng nhập sai |
| Vai trò và phân quyền | Đã làm phần lớn | Có Admin, Owner, Staff, Tenant; giới hạn dữ liệu theo chủ nhà/tòa nhà | Rà soát đầy đủ quyền xem/thêm/sửa/xóa cho từng màn hình |
| Quản lý nhiều tòa nhà | Đã làm | Có tạo, sửa, tìm kiếm, trạng thái hoạt động và nhân viên phụ trách | Chưa thấy luồng xóa/khóa mềm hoàn chỉnh |
| Quản lý tầng | Một phần | Tầng đang là trường số trong `Room` | Chưa có thực thể `Floor` độc lập và metadata của tầng |
| Quản lý phòng | Đã làm phần lớn | Có tầng, diện tích, giá, trạng thái, tiện nghi, ảnh/video | Chưa có loại phòng rõ ràng; cần hoàn thiện lịch sử trạng thái |
| GPS khu nhà | Chưa làm | `Building` mới lưu địa chỉ dạng văn bản | Thêm latitude/longitude hoặc PostGIS |
| Quản lý người thuê | Đã làm | Hồ sơ, liên hệ, CCCD, trạng thái và liên kết tài khoản | Có thể bổ sung file ảnh CCCD nếu cần đúng phạm vi mở rộng |
| Lịch sử thuê | Đã làm phần lớn | Có thể truy xuất qua hợp đồng và thành viên hợp đồng | Cần màn hình lịch sử rõ ràng theo phòng/người thuê |
| Quản lý hợp đồng | Đã làm tốt | Tạo, sửa, kích hoạt, gia hạn, chấm dứt, hủy, thành viên và dịch vụ | Có thể bổ sung file hợp đồng và chức năng in/xuất PDF |
| Quản lý dịch vụ | Đã làm | Có danh mục, đơn giá, đơn vị tính và gắn vào hợp đồng | Cần lịch sử thay đổi đơn giá nếu yêu cầu đối soát dài hạn |
| Chỉ số điện nước | Đã làm | Có chỉ số đầu/cuối, kỳ, kiểm tra dữ liệu và tính tiêu thụ | Có thể bổ sung ảnh công tơ |
| Hóa đơn | Đã làm tốt | Tạo đơn lẻ/hàng loạt, chi tiết tiền phòng, điện nước, dịch vụ | Chưa tự động chạy định kỳ; chưa xuất PDF/Excel |
| Thanh toán và công nợ | Đã làm | Hỗ trợ thanh toán một phần/toàn phần và hủy giao dịch | Chưa xuất phiếu thu PDF |
| Thông báo | Đã làm | Theo người/phòng/tòa nhà, hợp đồng sắp hết hạn, đã đọc/chưa đọc | Chưa có email/push và chưa liên kết cảnh báo cháy |
| Quản lý sự cố | Đã làm | Người thuê gửi sự cố; quản lý phân công và cập nhật trạng thái | Đây là sự cố vận hành, không thay thế sự kiện cảnh báo cháy |
| Dashboard | Đã làm cơ bản | Có phòng, hợp đồng, công nợ, hóa đơn và sự cố | Thiếu biểu đồ doanh thu, thống kê theo thời gian và báo cáo chuyên sâu |
| Báo cáo và xuất dữ liệu | Chưa đầy đủ | Có số liệu tổng quan và API summary | Chưa có báo cáo doanh thu/công nợ và xuất Excel/PDF |
| Chat thời gian thực | Đã làm | Có Conversation, ChatMessage, WebSocket, lịch sử và trạng thái đọc | Cần kiểm thử tải và trải nghiệm reconnect nếu triển khai thật |
| Cổng người thuê | Đã làm | Xem phòng, hợp đồng, hóa đơn, thanh toán, sự cố và thông báo | Chưa nhận cảnh báo cháy theo khu vực |
| Quản lý camera | Chưa làm | Không có model hoặc màn hình camera | Tạo camera, nguồn RTSP/video, tòa nhà, tầng và vùng giám sát |
| YOLO nhận diện lửa/khói | Chưa làm | Không có Ultralytics, PyTorch, OpenCV hoặc model weights | Chuẩn bị dataset, huấn luyện, đánh giá và service suy luận |
| Temporal Sliding Window | Chưa làm | Chưa có bộ đệm theo camera | Thiết kế cửa sổ, ngưỡng, cooldown và kiểm thử cảnh báo sai |
| Sự kiện cảnh báo cháy | Chưa làm | Không có AlertEvent hoặc ảnh minh chứng | Lưu thời gian, camera, loại, confidence, ảnh và trạng thái xử lý |
| Lịch sử cảnh báo | Chưa làm | Không có dữ liệu và màn hình tra cứu | Thêm lọc theo thời gian, tòa nhà, tầng, camera và trạng thái |
| Indoor Map | Chưa làm | Sơ đồ phòng hiện tại chỉ nhóm phòng theo tầng | Tạo bản đồ tầng, vùng, tọa độ phòng, hành lang, lối thoát và thiết bị PCCC |
| SfM/SLAM | Chưa làm | Không có pipeline dựng bản đồ | Thực nghiệm ngoại tuyến trên một khu vực mẫu và chuẩn hóa kết quả |
| Liên kết camera/cảnh báo với bản đồ | Chưa làm | Chưa có khóa liên kết không gian | Liên kết Camera → MapZone và AlertEvent → HazardZone |
| Đồ thị nút–cạnh | Chưa làm | Không có MapNode/MapEdge | Mô hình hóa mạng lưới di chuyển và trọng số |
| Dijkstra tìm đường thoát | Chưa làm | Không có thuật toán hoặc thư viện đồ thị | Tìm lối thoát, tránh vùng nguy hiểm và tính lại khi trạng thái đổi |
| Random Forest gợi ý giá | Chưa làm | Không có dataset, mô hình hoặc API dự đoán | Huấn luyện, đánh giá MAE/RMSE/R² và tích hợp giao diện |
| PostGIS/khoảng cách đến trường | Chưa làm | PostgreSQL chưa cấu hình GIS | Cài PostGIS hoặc dùng Haversine cho prototype có ghi rõ giới hạn |
| Lịch sử gợi ý giá | Chưa làm | Chưa có model lưu dự đoán | Lưu đầu vào, giá hiện tại, giá gợi ý và quyết định áp dụng |

## 4. Bằng chứng trong mã nguồn

- Model nghiệp vụ: `apps/rentals/models.py`.
- Route chức năng: `apps/rentals/urls.py`.
- Nghiệp vụ hợp đồng, hóa đơn và thanh toán: `apps/rentals/services.py`.
- Chat WebSocket: `apps/rentals/consumers.py` và `apps/rentals/routing.py`.
- Dashboard và sơ đồ phòng: `apps/rentals/views.py`.
- Tài khoản và audit: `apps/accounts/models.py`, `apps/accounts/services.py`.
- Kiểm thử: thư mục `tests/`.

Không tìm thấy model, route, service hoặc dependency tương ứng với YOLO, OpenCV, Temporal Sliding Window, camera giám sát, sự kiện cháy, Indoor Map, Dijkstra, Random Forest và PostGIS.

## 5. Lộ trình thực hiện đến 04/12/2026

Do thời gian còn khoảng sáu tuần, mục tiêu phù hợp là một prototype tích hợp hoàn chỉnh trên một tòa nhà và một tầng thử nghiệm, thay vì hệ thống camera/bản đồ ở quy mô production.

### Giai đoạn 1 — 22/10 đến 25/10: ổn định nền tảng

- Chốt mô hình `Floor`: tạo thực thể riêng hoặc giữ `Room.floor` cho prototype.
- Bổ sung GPS cho tòa nhà và loại phòng.
- Thiết kế ERD cho camera, cảnh báo và Indoor Map.
- Cài đồng bộ dependency trong virtual environment.
- Chạy migration, Django check và toàn bộ test hiện có.
- Bổ sung báo cáo doanh thu/công nợ tối thiểu theo tháng.

**Tiêu chí hoàn thành:** migration sạch, test nghiệp vụ cũ chạy qua, ERD mới được cố định.

### Giai đoạn 2 — 26/10 đến 08/11: mô-đun YOLO

- Thu thập và chuẩn hóa dataset lửa, khói và các trường hợp không cháy.
- Chia train/validation/test theo nguồn video để tránh rò rỉ dữ liệu.
- Fine-tune YOLO pretrained trên Google Colab.
- Lưu phiên bản dataset, cấu hình huấn luyện và trọng số tốt nhất.
- Đánh giá Precision, Recall, F1-score, mAP và confusion matrix.
- Viết chương trình suy luận độc lập cho ảnh và video.

**Tiêu chí hoàn thành:** chương trình nhận video và trả về bounding box, lớp lửa/khói, confidence và timestamp.

### Giai đoạn 3 — 09/11 đến 15/11: camera, Sliding Window và cảnh báo

Tạo các model tối thiểu:

- `Camera`
- `DetectionResult`
- `AlertEvent`
- `AlertEvidence`
- `AlertStatusHistory`

Triển khai:

- Nhận video file trước; RTSP camera là bước mở rộng.
- Tạo bộ đệm kết quả riêng cho từng camera.
- Cấu hình `window_size`, `min_positive_frames`, confidence và cooldown.
- Lưu ảnh minh chứng của cảnh báo.
- Xây trang danh sách, chi tiết, xác nhận và xử lý cảnh báo.
- Gửi thông báo tới chủ nhà/người quản lý và người thuê liên quan.

**Tiêu chí hoàn thành:** video thử nghiệm đi qua YOLO và Sliding Window, sau đó tạo đúng một cảnh báo có ảnh và vị trí camera.

### Giai đoạn 4 — 16/11 đến 22/11: Indoor Map và tìm đường

Tạo các model:

- `IndoorMap`
- `MapZone`
- `MapNode`
- `MapEdge`
- `ExitPoint`
- `SafetyDevice`
- `HazardZone`

Triển khai:

- Chọn một tầng mẫu để xây bản đồ.
- Chạy SfM/SLAM ngoại tuyến nếu dữ liệu đáp ứng; không bắt buộc tích hợp trực tiếp vào web.
- Chuẩn hóa kết quả thành bản đồ 2D đơn giản.
- Gắn phòng, hành lang, cầu thang, lối thoát, camera và thiết bị PCCC.
- Xây đồ thị nút–cạnh.
- Cài Dijkstra; loại bỏ hoặc tăng trọng số cạnh đi qua vùng nguy hiểm.
- Hiển thị vùng nguy hiểm và đường thoát bằng SVG hoặc Canvas.

**Tiêu chí hoàn thành:** chọn được vị trí bắt đầu và tìm được lối thoát; tuyến đường thay đổi khi vùng nguy hiểm thay đổi.

### Giai đoạn 5 — 16/11 đến 22/11, thực hiện song song: gợi ý giá thuê

- Chuẩn bị dữ liệu diện tích, tiện ích, vị trí, khoảng cách và mùa vụ.
- Dùng PostGIS nếu kịp cấu hình; nếu không, dùng Haversine cho prototype và ghi rõ giới hạn.
- Huấn luyện Random Forest Regressor.
- Đánh giá MAE, RMSE và R².
- Xây trang nhập/chọn thông tin phòng cần định giá.
- Hiển thị giá hiện tại và giá mô hình gợi ý.
- Chỉ cập nhật giá thuê khi chủ nhà xác nhận.
- Lưu lịch sử đầu vào, kết quả và quyết định áp dụng.

**Tiêu chí hoàn thành:** dự đoán được giá tham khảo và có báo cáo đánh giá mô hình.

### Giai đoạn 6 — 23/11 đến 29/11: tích hợp end-to-end

Kiểm thử chuỗi hoàn chỉnh:

```text
Camera/video
→ YOLO nhận diện
→ Temporal Sliding Window
→ AlertEvent
→ xác định Camera và MapZone
→ đánh dấu HazardZone
→ chạy lại Dijkstra
→ hiển thị cảnh báo và đường thoát
→ gửi thông báo
```

Các kịch bản bắt buộc:

- Video không cháy.
- Chỉ có lửa.
- Chỉ có khói.
- Nhận diện chập chờn trong một số khung hình.
- Hai camera cùng phát hiện.
- Một lối đi hoặc lối thoát bị đánh dấu nguy hiểm.
- Người dùng không được xem dữ liệu của tòa nhà ngoài phạm vi quyền.

**Tiêu chí hoàn thành:** toàn bộ chuỗi chạy được trên dữ liệu demo và có test tích hợp cho các nhánh chính.

### Giai đoạn 7 — 30/11 đến 04/12: hoàn thiện đồ án

- Tổng hợp kết quả YOLO và Random Forest.
- Đo cảnh báo sai, bỏ sót và độ trễ của Sliding Window.
- Hoàn thiện Use Case, ERD, kiến trúc và sequence diagram.
- Chụp màn hình và quay video demo luồng tích hợp.
- Hoàn thiện hướng dẫn cài đặt, vận hành và dữ liệu mẫu.
- Trình bày rõ giới hạn của AI, SfM/SLAM và bản đồ thoát hiểm thử nghiệm.
- Chuẩn bị video demo dự phòng nếu camera trực tiếp không ổn định.

## 6. Thứ tự ưu tiên khi thiếu thời gian

1. YOLO và Temporal Sliding Window.
2. Lưu, hiển thị và xử lý sự kiện cảnh báo.
3. Indoor Map mẫu và Dijkstra.
4. Liên kết cảnh báo với bản đồ và thông báo.
5. Báo cáo/thống kê còn thiếu.
6. Random Forest gợi ý giá.
7. SfM/SLAM tự động hoàn toàn và PostGIS nâng cao.

Không nên ưu tiên làm lại giao diện các màn hình quản lý đã có trước khi hoàn thành chuỗi AI → cảnh báo → bản đồ → tìm đường. Đây là phần quyết định hệ thống có đáp ứng đúng tên và mục tiêu của đề tài hay không.

## 7. Rủi ro và lưu ý

- Virtual environment hiện thiếu package `daphne`, dù dependency đã có trong `requirements.txt`; vì vậy chưa chạy được Django check và test suite tại thời điểm đánh giá.
- SfM/SLAM có rủi ro cao về chất lượng dữ liệu và thời gian xử lý. Nên thực hiện ngoại tuyến và chỉ tích hợp sản phẩm bản đồ đã chuẩn hóa.
- Không trình bày bản đồ hoặc đường thoát của prototype như giải pháp PCCC được chứng nhận.
- Cần lưu phiên bản dataset, model và cấu hình thí nghiệm để kết quả trong báo cáo có thể tái lập.
- Video dung lượng lớn không nên lưu trực tiếp trong PostgreSQL; chỉ lưu metadata, ảnh minh chứng và đường dẫn file.
