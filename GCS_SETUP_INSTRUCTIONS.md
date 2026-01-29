# Hướng dẫn Cấu hình GCS (Google Cloud Storage)

Service Account hiện tại (`qa-data-generator@...`) đang thiếu quyền truy cập vào Storage. Để sử dụng Batch Processing, bạn cần cấp quyền cho nó.

## Các bước thực hiện:

1.  Truy cập **[Google Cloud IAM Console](https://console.cloud.google.com/iam-admin/iam?project=uet-education-qa-data-for-sft)**.
    *(Đảm bảo bạn đang chọn project `uet-education-qa-data-for-sft`)*.

2.  Tìm email Service Account trong danh sách:
    `qa-data-generator@uet-education-qa-data-for-sft.iam.gserviceaccount.com`

3.  Nhấn vào biểu tượng **Bút chì** (Edit principal) ở cuối dòng tương ứng với email đó.

4.  Trong panel chỉnh sửa, nhấn nút **+ ADD ANOTHER ROLE**.

5.  Trong ô tìm kiếm "Select a role", gõ: `Storage Admin`.
    *Chọn kết quả **Storage Admin** (quyền cao nhất với Storage).*

6.  Nhấn **Save**.

---
Sau khi bạn thực hiện xong, hãy báo cho tôi biết ("Đã cấp quyền"). Tôi sẽ chạy lại script để tạo Bucket và bắt đầu Batch Processing.
