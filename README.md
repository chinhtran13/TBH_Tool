# 🎒 TBH_Tool - Trình Giám Sát & Tự Động Hóa Túi Đồ

**TBH_Tool** là một công cụ tự động hóa thông minh chạy trên Windows, được thiết kế để theo dõi các thay đổi trên màn hình bằng thuật toán so sánh ảnh pixel gốc và tự động thực hiện các chuỗi thao tác click chuột theo cấu hình.

---

## ✨ Các Tính Năng Nổi Bật

*   **🔍 Giám Sát Song Song 2 Vùng Màn Hình:**
    *   **Vùng 1 (Điều kiện):** Phát hiện thay đổi trạng thái hình ảnh để kích hoạt click chuột hành động.
    *   **Vùng 2 (Đầy túi):** Kiểm tra trạng thái đầy túi đồ để tự động chuyển sang vị trí túi tiếp theo.
*   **📂 Quản Lý Cấu Hình (Profiles Multi-Save):** Cho phép lưu trữ và nạp nhanh nhiều hồ sơ cấu hình tọa độ khác nhau cho từng tài khoản hoặc tác vụ riêng biệt.
*   **🔔 Thông Báo Qua Telegram:** Tự động gửi tin nhắn thông báo về điện thoại khi túi đồ bị đầy, hết túi dự phòng hoặc khi có sự cố.
*   **🔄 Tự Động Cập Nhật (Auto-Updater & Hot-Swap):** Tự động phát hiện phiên bản mới từ GitHub Releases, tải ngầm và tự động thay thế file chạy `.exe` cũ mà không cần người dùng thao tác thủ công.
*   **⚡ Tối Ưu Hóa Hiệu Năng:** Được tối ưu hóa bằng các hàm Win32 API (`ctypes`), không tốn tài nguyên CPU và hỗ trợ đa màn hình độ phân giải cao (DPI-Aware).

---

## 🚀 Tải Về & Sử Dụng Ngay (Không Cần Cài Python)

Dành cho người dùng thông thường muốn chạy trực tiếp phần mềm:

1.  Nhìn sang cột bên phải trang GitHub này, tìm mục **Releases** (hoặc bấm trực tiếp vào phiên bản mới nhất).
2.  Tại phần **Assets**, tải xuống file **`TBH_Tool.exe`**.
3.  Chạy trực tiếp file `.exe` vừa tải về để mở giao diện điều khiển.

---

## 💻 Hướng Dẫn Sử Dụng Chi Tiết

Để cấu hình tool hoạt động chính xác nhất, bạn hãy làm theo các bước sau:

1.  **Chọn Vùng 1 (Điều kiện):** Bấm nút `Chọn vùng 1` rồi quét chuột chọn khu vực cần theo dõi thay đổi.
2.  **Chọn Vùng 2 (Báo đầy túi):** Bấm nút `Chọn vùng 2` rồi quét chuột chọn khu vực ô trống báo hiệu túi đầy.
3.  **Chọn điểm click hành động:** Bấm nút `Chọn vị trí bằng 1 lần click` và nhấp vào mục tiêu cần tác động trên màn hình.
4.  **Thêm các túi dự phòng:** Bấm nút `Thêm vị trí túi bằng 1 lần click` rồi nhấp lần lượt vào các túi tiếp theo trên màn hình (hoặc nhập tọa độ thủ công dạng `x,y` trong khung văn bản).
5.  **Chụp ảnh mốc gốc:** Đặt màn hình game/ứng dụng ở trạng thái bình thường chưa thay đổi, sau đó bấm `Chụp mốc gốc vùng 1 + vùng 2`.
6.  **Lưu cấu hình:** Nhập tên vào ô cấu hình và bấm `Lưu` để không phải thiết lập lại ở lần chạy sau.
7.  **Bắt đầu:** Bấm nút `Bật giám sát`.


---

## ⚙️ Thiết Lập Nhà Phát Triển (Chạy từ Source Code)

Nếu bạn muốn đóng góp code hoặc chạy trực tiếp từ mã nguồn:

### Yêu cầu hệ thống:
*   Hệ điều hành: **Windows 10 / 11**
*   **Python 3.10+**

### Cài đặt thư viện phụ thuộc:
Tool sử dụng hầu hết các thư viện tiêu chuẩn của Python. Nếu bạn muốn đóng gói chương trình, hãy cài đặt PyInstaller:
```powershell
pip install pyinstaller
```

### Chạy ứng dụng:
```powershell
python .\inventory_bag_monitor.py
```

### Đóng gói ứng dụng sang file `.exe`:
```powershell
pyinstaller --noconfirm --onefile --windowed --name="TBH_Tool" .\inventory_bag_monitor.py
```

---

## ⚠️ Một Số Lưu Ý Quan Trọng

*   **Độ nhạy (Threshold):** `Ngưỡng thay đổi` càng nhỏ thì độ nhạy phát hiện thay đổi ảnh càng cao. Giá trị khuyên dùng mặc định là `0.035`.
*   **Tính an toàn:** Phần mềm chạy hoàn toàn cục bộ trên máy tính của bạn và tương tác trực tiếp qua hệ thống Windows API để chụp màn hình và giả lập click chuột, không can thiệp vào bộ nhớ của trò chơi/phần mềm khác.
