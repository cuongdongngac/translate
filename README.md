# Công cụ dịch sách tự động qua NotebookLM → Google Docs

Tự động hoá việc dịch một cuốn sách tiếng Anh (PDF, kể cả bản scan/OCR) sang
tiếng Việt theo phương pháp "cuốn chiếu" (dịch nối tiếp từng đoạn ~300-600
từ), dùng **NotebookLM** làm "bộ não dịch" (đọc trực tiếp từ nguồn PDF thật,
ít bịa nội dung hơn so với gọi thẳng một mô hình không có nguồn tham chiếu).
Kết quả tự động đẩy lên **Google Doc** để theo dõi trực tiếp, đồng thời lưu
đầy đủ vào file `translation.md` cục bộ (nguồn dữ liệu thật, không giới hạn
dung lượng).

**Vận hành bán tự động có chủ đích:** bạn tự tay thêm/xoá nguồn PDF trên
NotebookLM; chương trình lo phần lặp lại (gõ "Bắt đầu"/"Tiếp tục" thay bạn,
đẩy kết quả lên Doc, tự phát hiện và phục hồi một số lỗi thường gặp). Việc
đổi nguồn bằng tay đóng vai trò "trạm kiểm tra chất lượng" — giúp phát hiện
sớm nếu AI dịch lệch hướng.

### Sơ đồ luồng hoạt động

```
PDF sách (bạn tự upload lên NotebookLM)
        │
        ▼
NotebookLM (dịch từng đoạn, theo lệnh "Bắt đầu"/"Tiếp tục")
        │
        ▼
translate_book.py (điều phối vòng lặp, tự phục hồi lỗi)
        │
        ├──► translation.md   (bản dịch đầy đủ — NGUỒN DỮ LIỆU THẬT)
        │
        └──► Google Doc(s)    (theo dõi trực tiếp; tự tách "Phần 2, 3..."
                                nếu vượt giới hạn 1.024.000 ký tự/Doc)
```

---

## 1. Yêu cầu trước khi bắt đầu

- Một tài khoản Google (dùng cho NotebookLM và Google Drive).
- Máy tính chạy **Windows**, **macOS**, hoặc **Linux**.
- Không cần biết lập trình để *sử dụng hàng ngày* — chỉ cần làm đúng các
  bước cài đặt bên dưới (1 lần duy nhất).

---

## 2. Cài đặt môi trường

### 2.1. Cài `uv` (công cụ quản lý Python)

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux (Terminal):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
> macOS dùng chung lệnh với Linux — mở app **Terminal** (hoặc iTerm), dán
> đúng lệnh trên.

Đóng và mở lại terminal, kiểm tra:
```bash
uv --version
```

### 2.2. Tạo thư mục dự án

**Windows:**
```powershell
mkdir C:\book-translate
cd C:\book-translate
```

**macOS / Linux:**
```bash
mkdir ~/book-translate
cd ~/book-translate
```

Đặt toàn bộ file dự án (`translate_book.py`, `config.example.json`,
`requirements.txt`, `.gitignore`, `split.py`, `latex_to_equation.py`) vào
đúng thư mục này.

### 2.3. Tạo môi trường ảo và cài thư viện

**Windows:**
```powershell
uv venv
.venv\Scripts\activate
uv pip install -r requirements.txt
```

**macOS / Linux:**
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

> ⚠️ Mỗi khi mở terminal MỚI, luôn phải `cd` vào thư mục dự án + kích hoạt
> lại môi trường ảo trước khi chạy lệnh Python. Dấu hiệu đã đúng: thấy
> `(.venv)` ở đầu dòng lệnh.

### 2.4. Cài lệnh `notebooklm` toàn cục

```bash
uv tool install "notebooklm-py[browser]"
```
Nếu thiếu trình duyệt khi đăng nhập lần đầu:
```bash
uv tool run playwright install chromium
```

### 2.5. Đăng nhập NotebookLM

```bash
notebooklm login
```
Trình duyệt tự mở để đăng nhập. Kiểm tra lại:
```bash
notebooklm auth check --test --json
```
Thấy `"status": "ok"` là thành công.

> 🔒 **Cảnh báo bảo mật:** thư viện có tuỳ chọn `--master-token` để tránh
> phải đăng nhập lại — **KHÔNG dùng với tài khoản Google chính của bạn**.
> Tài liệu chính thức của thư viện gọi đây là *"infostealer-grade"* (mức độ
> nguy hiểm tương đương mã độc đánh cắp tài khoản), tồn tại vĩnh viễn kể cả
> sau khi đổi mật khẩu. Chỉ dùng với tài khoản Google "dùng bỏ", không quan
> trọng. Xem mục 8 để biết cách an toàn hơn tránh hết hạn phiên đăng nhập.

---

## 3. Thiết lập Google Cloud Console (lấy `credentials.json`)

Cần lấy **một lần duy nhất**, dùng chung cho mọi cuốn sách sau này.

1. Vào [console.cloud.google.com](https://console.cloud.google.com), đăng
   nhập đúng tài khoản Google dùng cho NotebookLM.
2. **Select a project → New Project** → đặt tên bất kỳ → **Create**.
3. Tìm kiếm **Google Drive API** → **Enable**.
4. **APIs & Services → Google Auth Platform** → tab **Audience**:
   - **User type: External**.
   - **Test users** → **+ Add users** → thêm đúng email của bạn.
5. Tab **Clients** → **+ Create client**:
   - **Application type: Desktop app** → đặt tên bất kỳ → **Create**.
6. Tải file JSON (hoặc tự điền theo mẫu, thay đúng `client_id`/`client_secret`):
   ```json
   {
     "installed": {
       "client_id": "XXXX.apps.googleusercontent.com",
       "project_id": "ten-project-cua-ban",
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       "token_uri": "https://oauth2.googleapis.com/token",
       "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
       "client_secret": "GOCSPX-xxxxxxxxxxxx",
       "redirect_uris": ["http://localhost"]
     }
   }
   ```
7. Lưu thành `credentials.json` trong thư mục dự án (Windows: chọn
   **Save as type: All Files** để tránh Windows tự thêm đuôi `.txt`).

---

## 4. Chuẩn bị dự án cho một cuốn sách mới

### 4.1. `config.json`

Copy `config.example.json` thành `config.json`:
```json
{
  "notebook_id": "id-notebook-lấy-từ-lệnh-notebooklm-list",
  "doc_title": "Tên hiển thị cho Google Doc",
  "target_folder_id": "",
  "rounds_per_run": 5,
  "rounds_before_refresh": 0
}
```
- `notebook_id`: chạy `notebooklm list` để xem.
- `target_folder_id`: để trống nếu không cần đặt Doc vào thư mục Drive cụ thể.
- `rounds_per_run`: số đoạn dịch tối đa mỗi lần chạy lệnh (khuyên 5 lúc mới bắt đầu).
- `rounds_before_refresh`: (tuỳ chọn) sau bao nhiêu vòng thì **chủ động** làm
  mới hội thoại để phòng ngừa hội thoại quá dài gây lỗi — `0` = tắt.

### 4.2. `prompt.txt` — viết riêng, KHÔNG đặt trong thư mục dự án

Tự viết, tự upload trực tiếp làm nguồn trên NotebookLM (mục 5). Nội dung
gồm: vai trò dịch giả, chuyên môn sách, quy tắc định dạng đầu ra (Word:
heading/bold/bảng markdown, công thức LaTeX bọc `\[...\]`/`\(...\)`...).

### 4.3. `automation_rules.txt` — tự sinh, chỉ cần upload

Chạy chương trình lần đầu (mục 6) — nó tự ghi ra file này. Đây là các luật
"hệ thống" áp dụng mọi cuốn sách: báo hiệu hết nguồn, xử lý trang gối đầu,
không chèn số trích dẫn, tự soát nội dung ngoài phạm vi sách, không tự ý
tìm internet khi hết nguồn...

---

## 5. Thiết lập Notebook trên NotebookLM

1. Vào [notebooklm.google.com](https://notebooklm.google.com), tạo notebook mới.
2. **Add source** → upload PDF sách (sách quá dày xem mục 9.1 — `split.py`).
3. **Add source** → **Paste text** → dán `prompt.txt` → đặt tên nguồn: `prompt.txt`.
4. **Add source** → **Paste text** → dán `automation_rules.txt` (sau khi chạy
   bước 6 lần đầu) → đặt tên nguồn: `automation_rules.txt`.
5. Lấy `notebook_id` bằng `notebooklm list`, điền vào `config.json`.

> ⚠️ Tên nguồn phải khớp chính xác với `GUIDE_TITLE`/`AUTOMATION_TITLE` ở
> đầu `translate_book.py`. Đặt tên khác thì sửa lại 2 hằng số đó cho khớp.

---

## 6. Chạy chương trình lần đầu

```bash
python translate_book.py
```
Lần đầu sẽ: tự sinh `automation_rules.txt` (nếu chưa có, dừng lại để bạn
upload theo mục 5 rồi chạy lại) → mở trình duyệt xin quyền Drive (chỉ hỏi
1 lần) → dịch vài đoạn → tạo Google Doc, in link (lưu vào
`google_doc_link.txt`).

---

## 7. Vận hành hàng ngày

### 7.1. Dịch tiếp bình thường
```bash
python translate_book.py
```

### 7.2. Khi hết nguồn hiện tại (`HẾT NGUỒN HIỆN TẠI`)
1. Vào NotebookLM, xoá nguồn PDF hiện tại, thêm file phần tiếp theo.
2. ```bash
   python translate_book.py --new-part
   ```
   Thêm `--last-part` nếu đó là phần cuối sách.

### 7.3. "Dịch chỉ định" (`--restart`) — làm mới hội thoại

Dùng khi: lỗi mạng/phản hồi bất thường, hội thoại quá dài gây lặp/nhảy
cóc, hoặc muốn sửa lại một đoạn dịch sai.

```bash
python translate_book.py --restart
```
Script tự động:
- Lấy câu neo (tiếng Anh) từ trường `last_anchor` trong `checkpoint.json`
  — **tự cập nhật sau mỗi vòng thành công**, không cần bạn tự tìm/copy.
- **Xoá hội thoại cũ trên server** (giống bấm "Delete history" trên web) rồi
  tạo hội thoại hoàn toàn mới, neo đúng vào câu đó — tránh mang theo gánh
  nặng ngữ cảnh (context) cũ.

**Muốn neo vào một điểm CŨ hơn** (không phải điểm vừa dịch xong, ví dụ cần
sửa lỗi từ vài vòng trước):
1. Mở `notes.log`, tìm câu tiếng Anh đúng + đoạn tiếng Việt tương ứng của
   vòng muốn quay về.
2. Mở `translation.md`, dùng đoạn tiếng Việt đó để Ctrl+F tìm đúng vị trí,
   xoá phần phía sau (hoặc dán `<!-- CUT_HERE -->` tại đó — script tự cắt).
3. Mở `checkpoint.json`, sửa trường `"last_anchor"` = đúng câu tiếng Anh
   (nên lấy **nguyên văn từ PDF gốc**, không dùng câu AI tự "làm sạch" lỗi
   OCR khi trích dẫn — đôi khi khác bản gốc, gây khó định vị chính xác).
4. `python translate_book.py --restart`.

**Kết hợp cờ:** `--new-part`, `--last-part`, `--restart` dùng chung được,
không quan trọng thứ tự gõ trên dòng lệnh — ví dụ:
```bash
python translate_book.py --new-part --restart
python translate_book.py --new-part --last-part --restart
```

### 7.4. Tự động phục hồi (không cần bạn làm gì)

- **Thiếu khối "📌 Ghi chú hệ thống"**: nếu câu trả lời AI bị lỗi/cắt cụt và
  thiếu hẳn phần ghi chú kết thúc, script **tự động** không lưu nội dung
  đáng ngờ đó, tự cập nhật `last_anchor` về điểm đúng gần nhất, và báo bạn
  chỉ cần chạy `--restart`.
- **Phản hồi quá lớn / mất mạng** (`RPCResponseTooLargeError`,
  `NetworkError`): script dừng gọn gàng, không mất gì (chưa kịp ghi gì cho
  vòng đó) — thường chỉ cần chạy lại bình thường; nếu lặp lại, dùng `--restart`.
- **Google Doc gần chạm giới hạn 1.024.000 ký tự**: script tự động chốt
  Doc hiện tại, mở **Doc "Phần N" mới** liền mạch, ghi thêm dòng mới vào
  `google_doc_link.txt` — không cần bạn can thiệp.

### 7.5. Hiệu chỉnh khẩn cấp — nguồn `addition` (tuỳ chọn)

Khi cần chỉnh gấp mà không muốn sửa `prompt.txt`/`automation_rules.txt`
chính thức: vào NotebookLM → **Add source → Paste text** → viết hướng dẫn
cần thiết → đặt tên nguồn đúng là **`addition`**. Mọi câu hỏi gửi đi trong
các lần chạy sau sẽ tự nhắc AI đọc thêm nguồn đó. Xong việc, xoá nguồn đó đi
— lần chạy tiếp theo tự động không còn nhắc đến nữa, không cần sửa gì khác.

### 7.6. Nếu chương trình lỡ ghi sai vào `translation.md`

`translation.backup.md` luôn giữ "phiên bản tốt cuối cùng" (cập nhật sau
mỗi vòng thành công) — copy đè lại thành `translation.md` nếu cần khôi phục.

---

## 8. Tránh hết hạn phiên đăng nhập khi chạy dài (an toàn, khuyên dùng)

Code đã bật sẵn `keepalive=300` khi mở client — tự "gõ nhẹ" định kỳ trong
lúc chạy để cookie không hết hạn giữa chừng. Muốn chắc chắn hơn nữa (kể cả
lúc không chạy script), đặt lịch tự làm mới phiên định kỳ:

**Bước 1 — tìm đường dẫn `notebooklm`:**
```bash
# Windows
where notebooklm
# macOS/Linux
which notebooklm
```

**Bước 2 — đặt lịch chạy** (`notebooklm auth refresh --quiet`) mỗi 15-20 phút:
- **Windows**: dùng **Task Scheduler** → Create Task → Trigger: On a
  schedule, Repeat task every 15 minutes, Indefinitely → Action: Start a
  program, Program/script = đường dẫn tìm được ở Bước 1, Add arguments =
  `auth refresh --quiet` → tick "Run whether user is logged on or not".
- **macOS/Linux**: thêm dòng sau vào crontab (`crontab -e`):
  ```
  */15 * * * * /đường/dẫn/notebooklm auth refresh --quiet
  ```

> Lưu ý: `auth refresh` chỉ "gia hạn" một phiên **đang còn sống** — nếu
> phiên đã hết hạn hoàn toàn, vẫn cần chạy `notebooklm login` lại một lần.

---

## 9. Các công cụ hỗ trợ khác

### 9.1. `split.py` — chia sách quá dày thành nhiều phần gối đầu

Chỉ cần khi một nguồn PDF vượt giới hạn NotebookLM (~500.000 từ/nguồn).
Nhiều sách 500 trang vẫn upload nguyên vẹn làm 1 nguồn được — chỉ tách khi
thật sự cần thiết.
```bash
python split.py sach.pdf 100 10 -o parts
```
(mỗi phần 100 trang, gối đầu 10 trang, lưu vào thư mục `parts`)

### 9.2. `latex_to_equation.py` — chuyển LaTeX thành Equation Word thật

Sau khi dịch xong (hoặc định kỳ), chuyển toàn bộ `translation.backup.md`
(bản đầy đủ, đã đẩy Doc thành công) sang `.docx`:
```bash
pandoc translation.backup.md -o ban_dich_hoan_chinh.docx
```
Rồi chuyển công thức LaTeX (`\[...\]`, `\(...\)`, còn ở dạng text) thành
equation Word thật (sửa được bằng Equation Editor):
```bash
python latex_to_equation.py ban_dich_hoan_chinh.docx ban_dich_final.docx
```

---

## 10. Xử lý sự cố thường gặp

| Lỗi gặp phải | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ModuleNotFoundError` | Quên kích hoạt `.venv` | `cd` vào thư mục dự án, kích hoạt lại venv |
| `ValueError: Authentication expired` | Phiên NotebookLM hết hạn | `notebooklm login` lại (xem mục 8 để phòng ngừa) |
| `Unexpected error: Authentication expired...` khi chạy `auth refresh` | Phiên đã hết hạn HOÀN TOÀN, không "gia hạn" được nữa | Phải `notebooklm login` lại trước, `auth refresh` chỉ cho phiên còn sống |
| `ChatError: ... too large` | Câu hỏi gửi đi quá dài | Đã khắc phục (dùng nguồn `prompt.txt`/`automation_rules.txt` riêng thay vì nhồi vào chat) |
| `RPCResponseTooLargeError` / `NetworkError` | Rất có thể nguồn đã hết và AI cố tìm internet, hoặc hội thoại quá dài | Script tự dừng an toàn — chạy lại; nếu lặp lại, dùng `--restart` |
| `HttpError 400 Bad Request` khi đẩy Doc | Google Doc chạm giới hạn 1.024.000 ký tự | Đã tự động xử lý (tự mở Doc "Phần N" mới) |
| Bản dịch bị lặp/nhảy cóc | Hội thoại quá dài, có thể chạm giới hạn context NotebookLM | `python translate_book.py --restart` |
| Doc mới bị tạo thay vì nối tiếp Doc cũ | `checkpoint.json` bị thiếu (ví dụ chạy từ thư mục mới) | Copy đúng `checkpoint.json` từ thư mục cũ sang |
| Câu trả lời thiếu khối "📌 Ghi chú hệ thống" | AI trả lời lỗi/cắt cụt giữa chừng | Script tự phục hồi — chỉ cần chạy `--restart` |

---

## 11. Cấu trúc file trong thư mục dự án

| File | Vai trò | Ai quản lý |
|---|---|---|
| `translate_book.py` | Script chính | Không tự sửa trừ khi đổi logic |
| `config.json` | Cấu hình riêng từng sách | Sửa mỗi khi đổi sách |
| `credentials.json` | OAuth Client Google Drive | Lấy 1 lần, dùng chung mọi sách |
| `token.json` | Phiên đăng nhập Drive đã lưu | Tự sinh |
| `checkpoint.json` | Tiến độ + `last_anchor` (câu neo tự cập nhật) | Tự sinh; sửa tay khi cần neo điểm khác |
| `translation.md` | Toàn bộ bản dịch — **nguồn dữ liệu thật** | Tự sinh, tự sửa khi cần dịch chỉ định |
| `translation.backup.md` | Bản sao lưu an toàn | Tự sinh |
| `notes.log` | Câu neo tiếng Anh + đoạn tiếng Việt tương ứng mỗi vòng | Tự sinh |
| `google_doc_link.txt` | Link Google Doc (mọi phần) | Tự sinh, tự nối thêm dòng khi tách Doc mới |
| `automation_rules.txt` | Luật hệ thống (xuất ra để upload NotebookLM) | Tự sinh từ code |
| `split.py` | Công cụ chia PDF | Dùng khi cần |
| `latex_to_equation.py` | Công cụ chuyển LaTeX → Equation Word | Dùng khi cần |
| `prompt.txt` | Vai trò dịch giả, định dạng riêng sách | **Không nằm trong thư mục này** — tự viết, tự upload lên NotebookLM |

---

## 12. Nguyên tắc nên nhớ

- **Luôn theo dõi định kỳ** — dù có nhiều lớp tự động, không gì thay được
  việc con người đọc lại Google Doc thường xuyên.
- **`rounds_per_run` nhỏ khi chưa quen** — dễ phát hiện lỗi sớm hơn.
- **Khi cần câu neo chính xác nhất, lấy nguyên văn từ PDF gốc** — AI đôi khi
  tự "sửa" lỗi OCR ngay cả khi tự trích dẫn câu neo của chính nó.
- **`translation.md`/`translation.backup.md` mới là nguồn thật** — Google
  Doc chỉ là cửa sổ theo dõi tạm thời; nếu Doc có lệch/lỗi hiển thị, không
  ảnh hưởng gì đến kết quả cuối (luôn xuất lại từ `translation.backup.md`
  bằng `pandoc`).
- **Không cần Docker/máy ảo gì thêm** — `.venv` là đủ cho quy mô dự án này.
- **Tuyệt đối không dùng `--master-token` với tài khoản Google chính.**
