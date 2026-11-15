# Bản đồ trong nhà 3D

Giao diện dùng Three.js 0.180.0 (WebGL, thư viện phục vụ từ `static/vendor/three/`, không phụ thuộc CDN). Mặt bằng là các vùng 2D có tọa độ, được dựng thành sàn, tường và cửa 3D. Cách tổ chức tham khảo [Mappedin: How to Create Indoor Navigation Maps](https://www.mappedin.com/resources/blog/how-to-create-indoor-navigation-maps/); không sử dụng SDK hoặc dịch vụ Mappedin.

## Sử dụng

- Vào **Bản đồ trong nhà**, chọn tòa nhà/tầng đã có mặt bằng.
- Bấm phòng trên mô hình hoặc danh sách để chọn điểm bắt đầu; chọn điểm đến hoặc để **Lối thoát gần nhất**.
- Kéo để xoay, cuộn để thu phóng, chuột phải để di chuyển. Có nút 2D/3D, đặt lại, xoay và toàn màn hình.
- Chủ nhà/quản trị viên có thể mở **Mô phỏng & lớp bản đồ** để chặn thử từng vùng. Mạng lưới định tuyến mặc định ẩn.
- Không hỗ trợ WebGL thì dùng mặt bằng SVG 2D dự phòng, vẫn tìm đường qua máy chủ.

## Dữ liệu và giới hạn

Mặt bằng mẫu gồm phòng, cửa, hành lang, hai điểm thoát, cầu thang và nội thất giả định. Tên/trạng thái phòng lấy từ dữ liệu quản lý. Đường đi dùng Dijkstra trên đồ thị **trong phòng → cửa → hành lang → điểm đến**; loại bỏ cả nút và cạnh giao vùng chặn. API JSON và giao diện sử dụng cùng một kết quả tính toán.

Đây không phải mô hình đo đạc hay tái dựng 3D từ một ảnh. Khoảng cách hiển thị chỉ là ước lượng theo tỉ lệ mẫu 0,04 m/đơn vị. Mặt bằng tùy chỉnh chưa hiệu chuẩn không hiển thị số mét. Chưa có chỉ đường liên tầng, định vị người dùng thời gian thực, nhập CAD, hoặc chứng nhận an toàn thoát nạn. Không dùng mô phỏng này thay cho phương án PCCC được phê duyệt.

`scene_for_map` kiểm tra phạm vi tòa nhà ở view, không xuất URL nguồn camera. Mô phỏng yêu cầu quyền chủ nhà/quản trị viên và CSRF; không làm mất cảnh báo thật.

## Nâng cấp demo cũ

Chỉ chạy với đúng bản đồ demo dạng hình sao do `seed_indoor_map` tạo:

```powershell
.venv/Scripts/python.exe -X utf8 manage.py build_demo_floorplan --map-id <UUID>
```

Lệnh sao lưu các bản ghi liên quan trong `tmp/indoor-map-backups/` trước khi thay hình học, giữ ID phòng/vùng/camera/cảnh báo, thay các cạnh mẫu bằng đường qua cửa và hành lang. Không sửa phòng, hợp đồng, hóa đơn. Chạy lại sẽ không làm lại bản đồ đã nâng cấp; bản đồ có tên tùy chỉnh hoặc đồ thị không còn dạng demo bị từ chối. Bản sao lưu chứa các bản ghi cũ để đối chiếu/khôi phục có kiểm soát, không nên `loaddata` đè lên bản đồ đang dùng.

## Kiểm thử tách biệt

```powershell
.venv/Scripts/python.exe -X utf8 manage.py test tests.test_indoor_map tests.test_indoor_scene --settings=config.test_indoor_settings --noinput
```

Kiểm thử chỉ dùng SQLite trong bộ nhớ, không kết nối hay tạo/xóa database trên Supabase. Để kiểm tra trình duyệt, mở hai terminal:

```powershell
# Terminal 1: dữ liệu mẫu trong SQLite tạm, chỉ lắng nghe localhost:8001.
.venv/Scripts/python.exe -X utf8 tests/serve_indoor_preview.py

# Terminal 2:
npm ci
npx playwright install chromium
node tests/indoor_map_browser.mjs
```

Có thể đặt `PLAYWRIGHT_CHROMIUM_EXECUTABLE` trỏ tới Chromium sẵn có. Bài kiểm tra bao gồm chọn phòng, đường qua cửa, 2D/3D, thu phóng, tìm kiếm, đổi lối thoát, hết đường đi, lỗi mạng, màn hình hẹp và dự phòng khi thiếu WebGL. Ảnh kiểm tra nằm trong `test-results/` (không đưa vào Git). Tài khoản preview chỉ tồn tại trong database tạm; không được tạo trên database thật.
