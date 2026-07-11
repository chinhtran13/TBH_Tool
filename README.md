# Theo dõi túi đồ

Tool Python này theo dõi 2 vùng màn hình và tự động click theo luồng:

1. Vùng 1 thay đổi thì click vào vị trí hành động bạn chọn.
2. Sau đó kiểm tra Vùng 2, nếu đầy thì click sang túi tiếp theo trong danh sách.
3. Khi vừa đổi túi mà đồ ở Vùng 1 vẫn còn, tool sẽ quét lại Vùng 1 và click tiếp thay vì bỏ qua.
4. Tiếp tục lặp lại cho đến hết các túi bạn đã cấu hình.

## Chạy tool

```powershell
python .\inventory_bag_monitor.py
```

## Cách dùng

1. Bấm `Chọn vùng 1` rồi kéo chuột chọn khu vực điều kiện.
2. Bấm `Chọn vùng 2` rồi kéo chuột chọn khu vực báo đầy túi.
3. Bấm `Chọn vị trí bằng 1 lần click`, rồi click một cái vào vị trí hành động trên màn hình.
4. Với các túi tiếp theo, dùng `Thêm vị trí túi bằng 1 lần click` hoặc nhập thủ công theo từng dòng `x,y`.
5. Bấm `Chụp mốc gốc vùng 1 + vùng 2` khi màn hình đang ở trạng thái bình thường.
6. Bấm `Xem ảnh đã chụp` để mở cửa sổ xem trước 2 vùng vừa chụp và kiểm tra đã chọn đúng chưa.
7. Bấm `Lưu ảnh đã chụp` nếu muốn xuất ảnh ra thư mục `captures`.
8. Bấm `Bật giám sát`.

## Lưu ý

- `Ngưỡng thay đổi` càng nhỏ thì càng nhạy.
- Sau khi đổi túi, tool chỉ chụp lại mốc gốc của Vùng 2 để còn quét lại Vùng 1 nếu đồ vẫn chưa được bỏ vào túi.
- Bạn có thể thêm bao nhiêu túi cũng được trong danh sách vị trí túi.
- Ảnh xuất ra được lưu dạng `.bmp` trong thư mục `captures`.
- Cấu hình được lưu trong `inventory_bag_monitor_config.json`.
