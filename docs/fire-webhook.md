# Camera trình duyệt, YOLO và webhook n8n

## Luồng trên Vercel

Bấm Bắt đầu → trình duyệt xin quyền camera bằng getUserMedia → gửi từng JPEG (tối đa 1280×720, 1 MB) tới Django → ONNX Runtime CPU nhận diện lửa/khói → trả bounding box và trạng thái để vẽ trên video.

Mô hình ONNX được xuất từ checkpoint hiện tại, giữ 512 px, lớp smoke/fire, ngưỡng riêng và NMS 0,7. File `models/fire_detection.json` ghi hash checkpoint, hash ONNX và tham số export. Vercel dùng onnxruntime trong pyproject.toml; không cần cv2, PyTorch, camera của máy chủ hoặc worker chạy liên tục. Một yêu cầu xử lý một khung hình; trình duyệt chờ kết quả rồi gửi tiếp sau 750 ms. Cold start và đường truyền ảnh hưởng tốc độ. Không thể suy ra độ chính xác hay độ trễ production từ tốc độ local.

Tuổi kết quả trên giao diện tính từ lúc chụp JPEG, bao gồm thời gian gửi ảnh và chờ máy chủ. Chỉ số “AI” là thời gian xử lý backend; “Tổng” gồm cả thời gian chụp/gửi/nhận kết quả. Video vẫn chạy trực tiếp nên box thuộc khung đã phân tích có thể lệch với vật thể đang di chuyển. Mô hình có thể bỏ sót lửa hoặc khói trong từng ảnh; việc đổi camera mặc định và sửa cách hiển thị không phải huấn luyện lại mô hình hoặc bằng chứng tăng độ chính xác.

Xác nhận riêng từng phiên bằng ít nhất 2/5 kết quả thực tế, xóa cửa sổ khi gián đoạn hơn 10 giây. API giữ `state` của cửa sổ xác nhận và trả thêm `current_state`: `recent_alert` khi cảnh báo chỉ còn bằng chứng ở khung trước. Giao diện hiển thị “Đang theo dõi sau cảnh báo”, vẫn giữ màu cảnh báo nhưng không phát âm báo hoặc gửi ảnh mới dựa trên bằng chứng cũ. Khi xác nhận, lưu BrowserFireAlert trên PostgreSQL và áp dụng cooldown theo người dùng (mặc định 30 giây, không reset bằng tải lại trang).

Trình duyệt gửi lại đúng JPEG của khung hình cảnh báo tới endpoint giao ảnh riêng, đồng thời tiếp tục nhận diện. Server kiểm tra SHA-256, quyền sở hữu và trạng thái cảnh báo; vẽ box → tải lên Cloudinary → POST JSON tới n8n. Trạng thái được khóa bằng transaction để hai request không gửi cùng sự kiện hai lần. Không tự retry khi timeout vì bên nhận có thể đã xử lý. Nếu đóng tab trước khi gửi ảnh, sự kiện pending có thể hết hạn; nếu request bị hủy giữa chừng, kết quả gửi có thể chưa xác nhận. Trạng thái lịch sử phân biệt pending/sending/sent/failed/expired/unknown. 2xx chỉ xác nhận n8n nhận webhook, không xác nhận Zalo đã gửi.

Nếu FIRE_CAMERA_ID hợp lệ và thuộc tòa nhà người dùng được phép xem, cảnh báo được liên kết Indoor Map. Camera chưa gắn map không chặn gửi n8n. Không nhầm cảnh báo có ảnh với cảnh báo đã lưu thành công vào bản đồ.

## Thiết lập

```dotenv
CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
FIRE_WEBHOOK_URL=https://YOUR_N8N_HOST/webhook/YOUR_PATH
FIRE_WEBHOOK_TOKEN=
FIRE_CAMERA_NAME=Camera tầng 1
FIRE_CAMERA_LOCATION=Hành lang tầng 1
```

Cập nhật biến trong môi trường thực sự chạy Django: `.env` cho local, Project Environment Variables cho Vercel. Redeploy Vercel sau khi đổi. Không commit `.env`. Các biến Cloudinary riêng nếu có phải cùng cloud với URL.

Chạy `python manage.py migrate` để thêm bảng fire_detection_browserfirealert. Trên PostgreSQL, migration bật RLS để tránh lộ bảng qua Supabase Data API; Django dùng tài khoản kết nối sở hữu bảng, quyền truy cập người dùng được kiểm tra ở backend.

n8n: Webhook POST, Respond Immediately, Publish/Active workflow. Dùng Production URL. HTTP Request kế tiếp: GET `{{ $json.body.image_url }}`, Response Format File, binary field `data`; node Zalo dùng ảnh này. Nếu bật token, chọn Header Auth với tên `X-Fire-Webhook-Token` và giá trị tương ứng.

Payload gồm event_id, detected_at (UTC ISO8601), camera_id, camera_name, location, label, confidence, detections và image_url (HTTPS Cloudinary). Header Idempotency-Key bằng event_id. Ảnh nằm trong `ql-phong-cho-thue/fire-alerts/<event_id>`. Webhook chỉ bật khi có FIRE_WEBHOOK_URL; không cấu hình n8n vẫn lưu ảnh Cloudinary.

Mở `/giam-sat-chay/`, đăng nhập vai trò quản lý, bấm Bắt đầu và cấp quyền camera. Cần HTTPS hoặc localhost. Không tự mở camera khi tải trang. Dừng hoặc rời trang sẽ tắt các track; đây là giám sát khi tab còn mở, không phải camera nền 24/7.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe manage.py test tests.test_browser_fire tests.test_fire_webhook tests.test_fire_detection --settings=config.test_indoor_settings --noinput
node tests/browser_camera_fire.mjs
```

Test backend dùng SQLite tách biệt và mock Cloudinary/n8n. Test Chromium dùng camera giả lập, không truy cập webcam thật. Có thể đặt PLAYWRIGHT_CHROMIUM_EXECUTABLE nếu dùng Chromium đã cài. Test gồm phân quyền/CSRF, đầu vào giả/malformed, cửa sổ xác nhận, cooldown, image hash, chống gửi trùng, xử lý lỗi, mở/dừng camera và request cũ trả sau khi dừng.

## Chế độ cũ

Các endpoint webcam máy chủ cũ được giữ để tương thích local, cùng bounded worker độc lập. Trang web chính dùng API camera trình duyệt mới, không dùng luồng cv2 này.

Xuất lại mô hình ở môi trường local có Ultralytics và onnx: `python ai/export_fire_onnx.py`. Không đổi checkpoint/ngưỡng triển khai khi chỉ đổi định dạng mô hình.

## Chọn camera khi hình đen

Mục Camera liệt kê thiết bị trình duyệt nhìn thấy; sau khi cấp quyền sẽ hiện tên thật. Mặc định ưu tiên HD User Facing (không phân biệt chữ hoa/thường, chấp nhận mã thiết bị phía sau). Nếu tên bị ẩn trước khi cấp quyền, ứng dụng xin quyền khi bấm Bắt đầu, liệt kê lại rồi chuyển sang HD User Facing trước khi gửi ảnh AI. Nếu không có thiết bị này thì dùng mặc định của trình duyệt. Lựa chọn thủ công của người dùng được giữ trong trang hiện tại, kể cả lựa chọn camera mặc định của trình duyệt. Không ép camera sau hoặc độ phân giải.

Chọn thiết bị sẽ mở theo deviceId chính xác; đổi trong lúc giám sát sẽ đóng nguồn cũ trước khi mở nguồn mới. Tên nguồn và kích thước video được hiển thị dưới trạng thái. Khung hình gần như đen hoàn toàn liên tiếp sẽ hiện cảnh báo nguồn ảnh và tạm ngừng gửi AI; camera vẫn mở để có thể tự phục hồi khi có hình. Kiểm tra này không chứng minh thiết bị bị hỏng hoặc phân biệt được phòng tối với nguồn camera trống.
