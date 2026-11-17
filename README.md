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

## Gợi ý giá thuê thử nghiệm

Đăng nhập bằng tài khoản chủ nhà hoặc quản trị viên, vào **Phòng**, chọn **Gợi ý giá** ở phòng cần xem, rồi nhấn **Tạo và lưu gợi ý mới**. Giá đề xuất và lịch sử được lưu riêng; chỉ khi nhấn **Áp dụng giá** thì giá niêm yết của phòng mới thay đổi. Giá trong hợp đồng hiện có không thay đổi.

Mô hình Random Forest dùng giá niêm yết của ít nhất 8 phòng **khác** thuộc cùng chủ nhà, có diện tích và giá hợp lệ. Đặc trưng gồm diện tích, tầng, sức chứa, tòa nhà và tiện nghi. Từ 20 phòng tham chiếu trở lên, trang hiển thị MAE, RMSE và R² của lần chia tập kiểm tra nội bộ. Cần cài `scikit-learn` qua `pip install -r requirements.txt` và chạy `python manage.py migrate` sau khi cập nhật mã.

Đây chỉ là giá tham khảo nội bộ: dữ liệu demo, giá tự niêm yết và thiếu vị trí GPS, khoảng cách đến trường, thời điểm giao dịch hoặc giá thuê thực tế đều có thể làm dự đoán sai. Để đánh giá giá thị trường, cần tập dữ liệu giao dịch độc lập, đủ lớn và có nguồn rõ ràng.

## Hồ sơ và ảnh CCCD khách thuê

Form thêm/sửa khách thuê có hai tab Thông tin và Ảnh CCCD. Chỉ họ tên bắt buộc;
số điện thoại, email, số CCCD và ảnh mặt trước/mặt sau đều có thể bổ sung sau.
Số CCCD có nhập vẫn phải duy nhất. Ảnh nhận JPG/PNG/WebP tối đa 5 MB mỗi mặt,
được kiểm tra và mã hóa lại để loại metadata trước khi tải lên Cloudinary với
`type=authenticated`. Chạy `python manage.py migrate` để cập nhật schema.

Ảnh không có URL công khai trong hồ sơ. Endpoint xem ảnh kiểm tra quyền quản lý
khách thuê rồi tạo URL ký có thời hạn ngắn. Thay/xóa ảnh trong form sẽ dọn ảnh
cũ sau khi database lưu thành công; upload dở dang được dọn nếu lưu thất bại.
Trên PostgreSQL, bảng metadata ảnh mới bật RLS; tài khoản database của Django
cần quyền sở hữu bảng như cấu hình migration hiện tại.

Kiểm thử backend dùng mock Cloudinary:
`python manage.py test tests.test_tenant_identity --settings=config.test_indoor_settings --noinput`.
Để kiểm tra giao diện với database tạm, chạy `tests/serve_indoor_preview.py`
rồi `node tests/tenant_form_browser.mjs`.

## Lệnh kiểm tra

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
python -m ruff check .
```

Kiểm thử cũng sử dụng PostgreSQL. Cấu hình `POSTGRES_TEST_DB` trong `.env`
với tên database riêng (mặc định `test_<POSTGRES_DB>`); không đặt trùng tên
database phát triển vì Django sẽ tạo và xóa database này trong quá trình test.

## Lưu ý production

- Thay toàn bộ secret/mật khẩu mặc định và đặt `DJANGO_DEBUG=false`.
- Chỉ cho phép hostname thực trong `DJANGO_ALLOWED_HOSTS`.
- Chạy sau HTTPS, dùng object storage cho file và backup PostgreSQL định kỳ.
- Không dùng tài khoản hoặc mật khẩu demo ở môi trường thật.

Xem kế hoạch đầy đủ tại [LO_TRINH_XAY_DUNG.md](LO_TRINH_XAY_DUNG.md).

## Gọi thoại và gọi video trong Trò chuyện

Mở một hội thoại rồi bấm biểu tượng điện thoại hoặc camera ở đầu khung chat. Người nhận cần mở trang Trò chuyện để nhận lời mời, sau đó chọn Trả lời. Trình duyệt yêu cầu quyền microphone/camera khi gọi hoặc trả lời; tính năng dùng được trên localhost hoặc HTTPS.

Cuộc gọi sử dụng WebRTC. Cấu hình mặc định dùng kết nối trực tiếp, phù hợp để thử trên localhost/mạng nội bộ. Khi triển khai cho các thiết bị khác mạng, cấu hình máy chủ STUN/TURN qua biến `WEBRTC_ICE_SERVERS` (mảng JSON gồm các đối tượng `urls`, `username`, `credential` theo cấu hình máy chủ). Cần TURN để chuyển tiếp âm thanh/video khi mạng không cho phép kết nối trực tiếp. Sau khi đổi biến môi trường Docker, chạy lại `docker compose up -d web`.

## Huấn luyện bổ sung nhận diện lửa nhỏ

`ai/prepare_small_fire.py` chọn dữ liệu từ bộ [D-Fire](https://github.com/gaia-solutions-on-demand/DFireDataset) đã có trong `datasets/D-Fire`, ưu tiên các hộp lửa chiếm tối đa 1% diện tích ảnh. Vẫn giữ ảnh khói và ảnh không có đối tượng để kiểm tra báo nhầm. Script không sửa ảnh/nhãn gốc, loại ảnh có nhãn không hợp lệ và giữ nguyên ranh giới train/validation/test. Các danh sách, số lượng và SHA-256 được ghi vào `datasets/D-Fire/small_fire_v1/manifest.json`.

```powershell
.venv/Scripts/python.exe -X utf8 ai/prepare_small_fire.py
.venv/Scripts/python.exe -X utf8 ai/train_yolo.py --model runs/fire_detection/dfire_yolo11n_e30/weights/best.pt --data datasets/D-Fire/small_fire_v1/dataset.yaml --epochs 6 --imgsz 768 --batch 4 --device 0 --workers 2 --name dfire_smallfire_768 --optimizer AdamW --lr0 0.0002 --freeze 10 --mosaic 0.2 --scale 0.25 --close-mosaic 2
.venv/Scripts/python.exe -X utf8 ai/evaluate_fire.py --model <checkpoint.pt> --images datasets/D-Fire/small_fire_v1/val.txt --output runs/fire_detection/evaluations/validation.json --imgsz 768
```

So sánh checkpoint cũ/mới trên cùng tập và cùng kích thước suy luận; chọn checkpoint/ngưỡng bằng validation rồi kiểm tra trên test độc lập. `evaluate_fire.py` đo precision/recall từng lớp, recall lửa nhỏ và số ảnh âm tính có phát hiện nhầm tại IoU ≥ 0,5. Đây là phép đo trên ảnh, không phải hiệu quả báo cháy thực tế của webcam hoặc cơ chế xác nhận nhiều khung hình. Tập chọn lọc này chưa đại diện cho bật lửa cầm tay, điều kiện phòng cụ thể hay toàn bộ phân bố D-Fire; kiểm tra theo đường dẫn không loại trừ ảnh gần trùng từ video.

Chỉ đổi `FIRE_MODEL_PATH` trong `.env` sang checkpoint đã kiểm tra. `FIRE_IMAGE_SIZE` điều khiển độ phân giải; `FIRE_CONFIDENCE`/`SMOKE_CONFIDENCE` điều khiển ngưỡng riêng từng lớp. Khởi động lại máy chủ để nạp `.env`, sau đó bấm **Bắt đầu giám sát**. Trang hiển thị đường dẫn model, độ phân giải và ngưỡng thực sự được dùng. Không tự động mở camera khi tải trang. “Chưa phát hiện” không có nghĩa là không có cháy; hệ thống không thay thế thiết bị PCCC.

Kiểm tra logic mà không truy cập webcam hoặc PostgreSQL/Supabase:

```powershell
.venv/Scripts/python.exe -X utf8 manage.py test tests.test_fire_detection tests.test_fire_evaluation tests.test_small_fire_dataset tests.test_fire_selection --settings=config.test_indoor_settings --noinput
```

### Kết quả lượt huấn luyện ngày 15/11/2026

Đã fine-tune checkpoint cũ trong 6 epoch trên GPU GTX 1650, với 2.400 ảnh train (1.200 ảnh có lửa nhỏ), 400 ảnh validation và 400 ảnh test tách riêng. Checkpoint mới được lưu ở `runs/fire_detection/dfire_smallfire_768_20261115/weights/best.pt`; không ghi đè checkpoint cũ.

Trên 400 ảnh validation, tại ngưỡng lửa 0,25 / khói 0,55 và IoU ≥ 0,5:

| Cấu hình | Recall lửa nhỏ (447 hộp) | Precision lửa | Recall khói | Precision khói |
| --- | ---: | ---: | ---: | ---: |
| Cũ, 512 px | 54,81% | 65,09% | 60,22% | 95,93% |
| Cũ, 768 px | 59,73% | 59,74% | 55,47% | 93,25% |
| Fine-tune, 768 px | 59,73% | 61,03% | 56,57% | 91,18% |

**Chưa triển khai checkpoint mới:** các ngưỡng lửa 0,15–0,35 không đồng thời vượt qua điều kiện cải thiện recall lửa nhỏ và bảo toàn precision/recall lửa, khói. Mặc định vẫn là model cũ ở 512 px, ngưỡng lửa 0,25 / khói 0,55. Tập test 400 ảnh chưa được dùng; cần thêm video/ảnh webcam gốc bị bỏ sót để đánh giá đúng điều kiện sử dụng, chia theo video/phiên quay để tránh rò rỉ giữa train và test.

Báo cáo có hash checkpoint/danh sách ảnh nằm trong `runs/fire_detection/evaluations/`: `baseline_val_512.json`, `baseline_val_768.json`, `candidate_val_768.json`, `selection.json`. Lệnh chọn cấu hình chỉ đọc báo cáo validation, không tự đổi model hay `.env`:

```powershell
.venv/Scripts/python.exe -X utf8 ai/select_fire_candidate.py --baseline runs/fire_detection/evaluations/baseline_val_768.json --reference runs/fire_detection/evaluations/baseline_val_512.json --candidate runs/fire_detection/evaluations/candidate_val_768.json --output runs/fire_detection/evaluations/selection.json
```

### Chẩn đoán video webcam ngày 15/11/2026

Video quay màn hình cho thấy có lúc khung hình đã khoanh lửa nhưng bảng trạng thái vẫn hiện 0 và mất kết nối. Log `server-20261115-222119.err.log` ghi lỗi `EMAXCONNSESSION` (Supabase session pool giới hạn 15 kết nối), làm API trạng thái trả HTTP 500 sau khoảng 42 giây. Đây là lỗi kết nối/đồng bộ giao diện, tách biệt với việc mô hình bỏ sót ngọn lửa yếu. Đoạn ghi hình cũng có nhiều khung hình lặp; không dùng chúng như những lần xác nhận độc lập.

Ứng dụng dùng Daphne/ASGI nên `CONN_MAX_AGE` được đặt về 0 theo [hướng dẫn Django](https://docs.djangoproject.com/en/5.2/topics/async/). Thời gian chờ kết nối mặc định là 5 giây **cho mỗi địa chỉ đích**; tùy chọn kết nối do người dùng cung cấp vẫn được giữ nguyên. Đây không phải giới hạn tổng thời gian của cả yêu cầu khi hostname có nhiều địa chỉ. Không thay cấu hình/gói dịch vụ Supabase, không bỏ kiểm tra đăng nhập.

Lưu cảnh báo vào cơ sở dữ liệu được chuyển sang một worker có hàng đợi giới hạn. Lịch sử/ảnh cục bộ xuất hiện trước, giao diện phân biệt đang chờ, đã lưu, chưa gắn camera và lưu thất bại. Worker đóng kết nối sau mỗi lần xử lý, không giữ luồng suy luận chờ cơ sở dữ liệu. Hàng đợi là bộ nhớ trong tiến trình, **không phải hàng đợi bền vững**: tác vụ đang chờ có thể mất khi máy chủ tắt; lỗi/đầy hàng đợi được báo rõ, không được coi là đã ghi vào bản đồ.

Đã thử lại trên 119 khung hình lấy từ vùng webcam trong 31,5 giây đầu video, che banner trạng thái cũ. Kết quả ở ngưỡng lửa 0,25: model cũ 512 px có phát hiện trong 23 khung hình, cũ 768 px trong 26, cũ 1024 px trong 26, model fine-tune 768 px trong 28. **Đây không phải độ chính xác/recall**: không có nhãn chuẩn cho toàn bộ khung hình, có ảnh lặp và các hộp nhận diện cũ đã ghi lên video. Không đổi model/ngưỡng triển khai chỉ dựa vào clip này; không dùng clip đồng thời để train và tuyên bố chất lượng kiểm thử độc lập. Báo cáo nằm ở `runs/fire_detection/evaluations/clip_20261115_baseline.json` và `clip_20261115_candidate.json`.

Công cụ chẩn đoán chỉ đọc video cục bộ, không mở webcam, không gửi ảnh ra ngoài và không sửa video gốc:

```powershell
.venv/Scripts/python.exe -X utf8 ai/inspect_fire_video.py --video "<video.mp4>" --output tmp/fire-clip-inspection --start 0 --end 31.5 --step 0.25 --crop 406 291 1036 583
.venv/Scripts/python.exe -X utf8 ai/diagnose_fire_clip.py --frames tmp/fire-clip-inspection --model runs/fire_detection/dfire_yolo11n_e30/weights/best.pt --sizes 512 768 1024 --mask-banner 8 8 280 45 --output runs/fire_detection/evaluations/clip_diagnostic.json
```

Tọa độ crop/banner ở trên chỉ phù hợp video đã kiểm tra; cần điều chỉnh theo bố cục video khác. Đây là quy trình chẩn đoán, không phải pipeline tự gán nhãn huấn luyện. Dùng video có sẵn, không đốt vật liệu hay thử lửa gần mặt để kiểm tra phần mềm.

## Gửi ảnh cảnh báo cháy qua n8n

Xem [hướng dẫn cấu hình webhook chính thức](docs/fire-webhook.md). Trang giám sát mở camera bằng trình duyệt, gửi JPEG tới Django trên Vercel để nhận diện ONNX 512 px. Cảnh báo được lưu và gửi sang Cloudinary/n8n bằng yêu cầu riêng; không cần cài OpenCV trên Vercel.
