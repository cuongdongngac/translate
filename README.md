# Book Translate — Dịch sách bán tự động qua NotebookLM

## Dự án này làm gì

Tự động hoá việc dịch sách tiếng Anh (OCR) sang tiếng Việt theo phương pháp
"cuốn chiếu" (dịch nối tiếp từng đoạn ~300-600 từ), dùng NotebookLM làm
"bộ não dịch" (vì có lợi thế grounded trên nguồn PDF thật, ít bịa nội dung),
và tự động đẩy kết quả lên một Google Doc duy nhất, giữ định dạng
(heading, in đậm, bảng biểu).

Sách lớn được cắt thành nhiều file PDF nhỏ theo kiểu "gối đầu" (overlap)
bằng `split.py`, vì NotebookLM quản lý một nguồn lớn dễ bị lẫn ngữ cảnh.

## Vận hành theo kiểu BÁN TỰ ĐỘNG (quyết định có chủ đích)

- **Người dùng** tự tay thêm/xoá nguồn PDF trên web notebooklm.google.com
  (mỗi lúc chỉ giữ đúng 1 nguồn sách trong notebook).
- **Script** (`translate_book.py`) chỉ lo phần lặp lại: tự gõ
  "Bắt đầu"/"Tiếp tục" thay người dùng, và tự đẩy bản dịch lên Google Doc.

Lý do KHÔNG chọn tự động hoàn toàn (dù kỹ thuật làm được): việc đổi nguồn
bằng tay đóng vai trò "trạm kiểm tra chất lượng" — con người phát hiện sớm
nếu AI dịch lệch hoặc hệ thống trục trặc giữa chừng, trước khi sai sót lan
rộng ra nhiều đoạn.

## Cách "trí nhớ" hoạt động (quan trọng để hiểu code)

Ứng dụng **không tự đếm** đã dịch đến trang/đoạn nào. Toàn bộ dựa vào:
1. `conversation_id` được lưu trong `checkpoint.json` và gửi lại mỗi lần
   hỏi — NotebookLM tự nhớ lại toàn bộ lịch sử hội thoại trước đó.
2. Các trang "gối đầu" ở đầu mỗi file PDF phần sau (do `split.py` chèn ghi
   chú) giúp AI đối chiếu chỗ đã dịch, tránh dịch lặp.
3. Một câu thông báo chuyển tiếp tường minh script tự gửi khi chạy với
   `--new-part`.

Không có cơ chế "chốt cứng" vị trí nào khác — nếu conversation bị mất/reset,
sẽ không tự phát hiện được, đây là lý do vẫn cần con người giám sát điểm
chuyển file.

## Cấu trúc file

| File | Vai trò | Ai sửa |
|---|---|---|
| `translate_book.py` | Script chính, vòng lặp dịch + đẩy Google Doc | Chỉ sửa khi đổi logic |
| `config.json` | notebook_id, doc_title, target_folder_id, rounds_per_run | Sửa mỗi khi đổi sách |
| `config.example.json` | Bản mẫu config không chứa dữ liệu thật | Tham khảo |
| `credentials.json` | OAuth Client (Desktop app) từ Google Cloud Console | Lấy 1 lần, dùng chung mọi sách |
| `token.json` | Phiên đăng nhập Google Drive đã lưu | Tự sinh, không sửa tay |
| `checkpoint.json` | Tiến độ dịch (conversation_id, round, doc_id...) | Tự sinh; xoá khi bắt đầu sách mới |
| `ban_dich.md` | Toàn bộ bản dịch dạng markdown (bản gốc, luôn đúng) | Tự sinh |
| `ghi_chu.log` | Log riêng phần "📌 Ghi chú hệ thống" mỗi vòng | Tự sinh |
| `google_doc_link.txt` | Link Google Doc để mở lại nhanh | Tự sinh |
| `split.py` | Cắt PDF lớn thành nhiều phần gối đầu | Công cụ tiền xử lý |
| `prompt.txt` | **KHÔNG nằm trong thư mục này** — người dùng tự viết, tự upload trực tiếp làm nguồn trên NotebookLM | Người dùng quản lý trên web |

**Lưu ý quan trọng:** `prompt.txt` (vai trò dịch giả, quy tắc văn phong
riêng của từng sách) **không được script đọc hay gửi qua chat** — vì làm
vậy từng gây lỗi `ChatError: over-long question` (status 3) khi nội dung
quá dài. Giải pháp: người dùng tự upload `prompt.txt` làm 1 nguồn cố định
trên NotebookLM, và script chỉ gửi một câu ngắn trỏ tới nguồn đó.

## Quy tắc automation nằm trong CODE, không nằm trong prompt.txt

Cố ý tách biệt (theo yêu cầu người dùng): `prompt.txt` là không gian tự do
tuỳ biến theo từng sách (vai trò, văn phong, thuật ngữ...). Các quy tắc
phục vụ *cơ chế tự động hoá* (không phải nội dung dịch) nằm trong hằng số
`AUTOMATION_RULES` ở đầu `translate_book.py`, luôn được gửi kèm câu lệnh
"Bắt đầu" đầu tiên, áp dụng cho MỌI sách:

1. Báo hiệu hết nguồn (in `HẾT NGUỒN HIỆN TẠI` khi dịch hết nội dung hiện có)
2. Xử lý trang gối đầu (không dịch lại phần trùng lặp từ `split.py`)
3. Xử lý câu bị cắt cụt ở cuối nguồn (do cắt theo trang, không theo câu)
4. Không hỏi lại / không bình luận thêm ngoài định dạng quy định
5. Không chèn số hiệu trích dẫn `[1]`, `[2]`... vào bản dịch

## Cách chạy

```bash
# 0. Cài uv (chỉ 1 lần / máy)
#    Windows (PowerShell):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
#    Mac / Linux (Terminal):
curl -LsSf https://astral.sh/uv/install.sh | sh

# 1. Cài đặt dự án (1 lần / thư mục dự án)
uv venv
.venv\Scripts\activate      # Windows;  source .venv/bin/activate trên Mac/Linux
uv pip install -r requirements.txt

# 2. Cài lệnh `notebooklm` toàn cục (1 lần / máy, không phụ thuộc thư mục dự án)
uv tool install "notebooklm-py[browser]"
notebooklm login

# 3. Dịch tiếp trong file hiện tại (lặp lại tuỳ ý)
python translate_book.py

# 4. Sau khi thấy "HẾT NGUỒN HIỆN TẠI": tự đổi nguồn trên web NotebookLM, rồi
python translate_book.py --new-part              # còn phần tiếp theo
python translate_book.py --new-part --last-part   # đây là phần CUỐI CÙNG
```

## Dịch chỉ định (file `restart_point.txt`)

Bình thường hệ thống chỉ tin theo mạch hội thoại cũ (`conversation_id`) để biết
dịch tiếp từ đâu. Nhưng có lúc cần **tự chỉ đích danh điểm bắt đầu** thay vì để
hệ thống tự suy — ví dụ: phát hiện đoạn dịch sai muốn làm lại từ chỗ đúng
trước đó, hoặc người khác đã dịch xong một đoạn và giờ đến lượt mình dịch
tiếp từ đúng chỗ họ dừng.

File `restart_point.txt` tự sinh ngay từ lần chạy đầu tiên (cờ = `0`, dòng 2
trống — chưa dùng đến). Khi cần, chỉ việc mở file này lên sửa, đúng 2 dòng:

```
1
By the late 1980s, mammography had gained general acceptance.
```

- **Dòng 1**: cờ `1` (dùng) hoặc `0`/bỏ trống (không dùng — bỏ qua hoàn toàn,
  kể cả khi dòng 2 vẫn còn nội dung cũ)
- **Dòng 2**: câu tiếng Anh của điểm bạn muốn bắt đầu dịch tiếp (ví dụ lấy từ
  `ghi_chu.log`, vòng ngay trước chỗ lỗi)

**Trước khi chạy `python translate_book.py`:** tự tay xoá phần nội dung
sai/thừa trong `ban_dich.md` (giữ lại đến đúng điểm bạn muốn bắt đầu tiếp).
Sau khi dùng xong 1 lần, dòng 1 tự động được đặt lại thành `0` để tránh vô
tình dùng lại ở lần chạy sau.

## Bắt đầu dịch một cuốn sách MỚI

1. Xoá `checkpoint.json`, `ban_dich.md`, `ghi_chu.log`
2. Sửa `notebook_id` / `doc_title` trong `config.json`
3. Viết `prompt.txt` riêng cho sách mới, tự upload làm nguồn trên
   NotebookLM (tên nguồn phải khớp hằng số `GUIDE_TITLE` trong script)
4. Chạy `split.py` để cắt PDF sách mới nếu cần

## Định hướng tương lai (chưa làm, chỉ ghi lại ý định)

- Có thể viết lại bằng Go để đóng gói thành 1 file thực thi duy nhất,
  chia sẻ cho người dùng không rành kỹ thuật (ví dụ nhân viên thư viện)
  mà không cần cài Python/uv/venv. Điểm khó: `notebooklm-py` chỉ có bản
  Python, cần tự viết lại phần xác thực/chat bằng Go (có thể dùng
  `playwright-go`); phần Google Drive API có SDK Go chính thức, dễ chuyển.
- Có thể dùng n8n để lên lịch tự động gọi `python translate_book.py`
  (không kèm `--new-part`) trong lúc không có người giám sát — phần đổi
  nguồn (`--new-part`) vẫn cần con người, không tự động hoá được bằng n8n
  với thiết kế hiện tại.
