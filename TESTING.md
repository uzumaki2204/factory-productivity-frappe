# Kiểm thử Productivity

```powershell
python -m unittest discover -s tests -v
```

Bộ test chạy trên bộ nhớ bằng adapter Frappe, không cần bench và không ghi dữ liệu Pilot. Đối chiếu quy tắc từ `ProductivityServices.cs` của FactoryManagement commit `6d556e209359efa3f99d768ae9f6627624c0d532`.

Các trường hợp kiểm tra: giữ nguyên sản lượng từng ca/tổng, mục tiêu và giờ bằng 0, ngày đầu/cuối hiệu lực kế hoạch, ngày kết thúc thực tế, báo cáo trùng theo chuyền/ngày/kế hoạch, sửa bản hiện có, xóa mềm, sai phạm vi hoặc mã hàng, kế hoạch đã xóa, khung giờ lặp/sai công ty, số âm và retry cùng operation ID.

Kết quả 18/11/2026: 15 test đạt sau khi sửa. Trước sửa, test xác nhận app cho phép ngày ngoài hiệu lực, báo cáo trùng, báo cáo không có khung giờ và báo cáo trỏ kế hoạch đã xóa qua Data Import. Controller đã bổ sung kiểm tra, có khóa bản ghi kế hoạch trong transaction để serialize kiểm tra trùng. Chưa thực hiện test hai transaction đồng thời trên MariaDB; test bộ nhớ không xác nhận hành vi khóa của database.

Patch `refresh_report_validation` làm mới cache metadata để Pilot chạy migrate nhận bản cập nhật controller; không thay đổi schema hoặc dữ liệu cũ. Báo cáo đã xóa mềm được bỏ qua kiểm tra hiệu lực kế hoạch khi xóa. Kế hoạch hết hiệu lực không còn nằm trong danh sách chọn tạo báo cáo.

Pilot được kiểm tra chỉ đọc và hiện không có báo cáo Productivity. Luồng ghi thực qua Frappe ORM/Data Import cần chạy trên site thử nghiệm riêng khi có site đó; chưa thực hiện trên Pilot sản xuất.

Cập nhật app này trước Dashboard. Phiên bản trước để quay lui là 0.1.11. Các thông báo mới nằm trong i18n.json; rollback không tự thực hiện.
