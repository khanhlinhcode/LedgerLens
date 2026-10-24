# Kịch bản trình diễn khi phỏng vấn AI Application Engineer

## Video demo 90 giây

- **00:00–00:15 — Bài toán:** Doanh nghiệp nhận báo cáo Excel hàng tuần từ nhiều bộ phận; cột dữ liệu khác nhau, sai định dạng tiền, ngày tháng và bản ghi trùng khiến tổng hợp thủ công khó kiểm tra.
- **00:15–00:30 — Import:** Upload `examples/01_sales_standard.xlsx`, giải thích rule chuẩn hóa `document_no`, `txn_date`, `department`, `entry_type`, `amount`, `status`.
- **00:30–00:48 — Data Quality:** Upload `02_messy_mixed_departments.xlsx`; hệ thống phát hiện 1 dòng sai giá trị số tiền, 1 dòng trùng, và cảnh báo bỏ qua một sheet metadata. Không tự ý đoán/sửa số tiền bị lỗi.
- **00:48–01:08 — Dashboard:** Hiển thị doanh thu, chi phí, công nợ và biểu đồ nhóm. Giải thích số tiền là từ dữ liệu chuẩn hóa đã chấp nhận; các khoản công nợ không được cộng trùng vào Net.
- **01:08–01:25 — Text-to-Excel:** Nhập "Chi phí theo tháng", cho xem router chỉ chọn `group_by=month`, bấm Export để mở 4 sheet gồm Read Me, Summary, Normalized Data và Data Quality.
- **01:25–01:30 — Kết:** Có API authentication, import lineage/quality log, automated tests và tùy chọn mô hình Ollama phân loại câu hỏi, không cấp quyền chạy SQL tự do. Chưa có security audit trail theo người dùng.

## Cách trình bày với kỹ sư tuyển dụng

- **Tại sao không để LLM sinh SQL trực tiếp?** Vì LLM có thể tạo câu query vượt phạm vi, truy cập dữ liệu nhạy cảm và tạo số liệu sai. Ở MVP, mô hình chỉ quyết định loại báo cáo trong danh sách cho phép; truy vấn và phép tính chạy trong backend.
- **Xử lý lỗi Excel ra sao?** Khớp alias header, bỏ qua sheet không có đủ cột, xử lý định dạng ngày và VND, loại những dòng sai và ghi nguồn sheet / dòng. Tuy nhiên chưa xử lý mọi kiểu merged cell, macro hoặc external link.
- **Chống trùng thế nào?** Fingerprint versioned từ chứng từ, ngày, bộ phận, đối tác, loại và số tiền; unique constraint ở DB. Đó là demo key, chưa chắc phù hợp mọi doanh nghiệp; sản phẩm thật phải có business key được BA xác nhận.
- **Dữ liệu có đáng tin không?** Chỉ lấy record hợp lệ, xuất kèm issue log và ghi định nghĩa phép tính. Các mục công nợ không bị gộp vào net revenue-expense.
- **Đã tích hợp ERP chưa?** Chưa. Hiện đã có canonical data model và API; kế hoạch là làm mock Odoo/ERPNext trước rồi bổ sung auth, RBAC, audit log, sync idempotency và signed webhook.
- **AI có chạy không?** Quy tắc intent hoạt động không phụ thuộc provider. Có hỗ trợ gọi local Ollama nếu người dùng cung cấp URL và model. Chưa khẳng định chất lượng LLM production hoặc chạy benchmark.
- **Đã triển khai production?** Không. Chỉ xác nhận local MVP và automated tests. Có Docker Compose PostgreSQL để tái hiện môi trường demo.

## Phần cần triển khai thêm nếu có thời gian trước 21/11/2026

**Mức ưu tiên 1 — quan trọng cho JD:** Tích hợp mock ERP read-only, xây dựng rule đối soát chênh lệch, giao diện map column manual cho workbook xấu, load-test 100 workbook nhỏ.

**Mức ưu tiên 2:** Benchmark agent intent, audit request ID và RBAC read-only, file export template kế toán, mở rộng kiểm thử Excel formula injection, stress-test, đo time saved so với thủ công.

**Mức ưu tiên 3:** OCR chứng từ, RPA email/Zalo, VBA interoperability, native Excel PivotTable, deploy cloud với secrets và observability.

## Tên dự án cho CV

**LedgerLens — Enterprise Excel AI Copilot (Portfolio MVP)** · Python, FastAPI, SQLAlchemy, Pandas, OpenPyXL, XlsxWriter, PostgreSQL-ready, constrained AI.

**Bullet có thể sử dụng sau khi tự chạy demo:**
- Built a local Excel-to-database automation prototype for heterogeneous business reports, including bilingual column normalization, validation, duplicate detection and traceable quality logs.
- Added a governed natural-language reporting interface and formatted multi-sheet Excel exports with grouped financial summaries and charts; validated ingestion/reporting endpoints with automated tests.

Không đưa lên CV thông tin đã tích hợp ERP thật, OCR, RPA Zalo/Email hoặc vận hành production vì chưa triển khai.
