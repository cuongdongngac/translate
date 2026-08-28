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
đẩy kết quả lên Doc, **tự động làm mới hội thoại**, **tự động lấy lại token đăng nhập khi hết hạn**, và tự phục hồi một số lỗi thường gặp). Việc
đổi nguồn bằng tay đóng vai trò "trạm kiểm tra chất lượng" — giúp phát hiện
sớm nếu AI dịch lệch hướng. Chạy vô số vòng liên tục (ví dụ 9999) qua đêm một cách ổn định!

### Sơ đồ luồng hoạt động

```text
PDF sách (bạn tự upload lên NotebookLM)
        │
        ▼
NotebookLM (dịch từng đoạn, theo lệnh "Bắt đầu"/"Tiếp tục")
        │
        ▼
translate_book.py (điều phối vòng lặp, tự làm mới hội thoại định kỳ, tự relogin)
        │
        ├──► translation.md   (bản dịch đầy đủ — NGUỒN DỮ LIỆU THẬT)
        │
        └──► Google Doc(s)    (theo dõi trực tiếp; tự tách "Phần 2, 3..."
                                nếu vượt giới hạn 1.024.000 ký tự/Doc)
```

---

## 0. Cần biết trước khi dùng

- Đây là quy trình **dịch cuốn chiếu từng đoạn nhỏ** (~300-600 từ/lượt), không
  phải "upload nguyên cuốn sách rồi bấm một nút là ra bản dịch hoàn chỉnh
  ngay lập tức". Sách càng dày, càng cần chạy nhiều lượt (`rounds_per_run`).
- Việc thỉnh thoảng **bị lỗi API** (mất mạng, phiên đăng
  nhập hết hạn, phản hồi quá dài...) là chuyện **bình thường** của bất kỳ
  quy trình dịch tự động nào. Ở phiên bản hiện tại, chương trình đã tự động
  phát hiện và khắc phục các vấn đề này ngầm, giúp bạn hoàn toàn an tâm "cắm máy đi ngủ".
- Đã có thực nghiệm dịch liên tục hàng trăm trang sách mà không cần tương tác người dùng.

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

Đặt toàn bộ file dự án vào đúng thư mục này.

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

### 2.5. Tạo file `login.bat` và Đăng nhập NotebookLM lần đầu

Tạo file có tên `login.bat` (hoặc `login.sh` trên Mac/Linux nếu muốn) trong thư mục dự án, nội dung chỉ gồm đúng lệnh sau:
```bat
notebooklm login
```

Chạy file này hoặc gõ lệnh trực tiếp:
```bash
notebooklm login
```
Trình duyệt tự mở để đăng nhập. Sau lần đăng nhập đầu tiên này, token sẽ được lưu lại. Về sau, khi gọi `notebooklm login`, hệ thống sẽ **âm thầm tự động cấp lại cookie/token** mà không bắt bạn click trình duyệt nữa (rất phù hợp để chạy nền tự động).

Kiểm tra lại:
```bash
notebooklm auth check --test --json
```
Thấy `"status": "ok"` là thành công.

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

Copy `config.example.json` thành `config.json` (phải đảm bảo chuẩn JSON, chú ý dấu phẩy):
```json
{
  "notebook_id": "id-notebook-lấy-từ-lệnh-notebooklm-list",
  "doc_title": "Tên hiển thị cho Google Doc",
  "target_folder_id": "",
  "rounds_per_run": 9999,
  "rounds_before_refresh": 15
}
```
- `notebook_id`: chạy `notebooklm list` để xem.
- `target_folder_id`: để trống nếu không cần đặt Doc vào thư mục Drive cụ thể.
- `rounds_per_run`: số đoạn dịch tối đa mỗi lần chạy lệnh (có thể set thật to như `9999` để máy cắm qua đêm).
- `rounds_before_refresh`: **CỰC KỲ QUAN TRỌNG**. Nên để `15` hoặc `20`. Tức là sau 15 vòng, kịch bản sẽ tự động xoá hội thoại cũ rác rưởi đi, lập hội thoại mới tinh trên máy chủ Google (nhưng bảo toàn nguyên vị trí dịch hiện tại) để tránh lỗi tràn context.

### 4.2. `prompt.txt` — viết riêng, KHÔNG đặt trong thư mục dự án

Tự viết, tự upload trực tiếp làm nguồn trên NotebookLM (mục 5). Nội dung
gồm: vai trò dịch giả, chuyên môn sách, quy tắc định dạng đầu ra (Word:
heading/bold/bảng markdown, công thức LaTeX bọc `\[...\]`/`\(...\)`...).

### 4.3. `automation_rules.txt` — tự sinh, chỉ cần upload

Chạy chương trình lần đầu (mục 6) — nó tự ghi ra file này. Đây là các luật
"hệ thống" áp dụng mọi cuốn sách.

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

### 7.1. Dịch tiếp bình thường & Cắm qua đêm
```bash
python translate_book.py
```
Muốn cắm máy dịch liên tục, bạn gõ luôn số vòng lớn:
```bash
python translate_book.py --rounds 9999
```
Chương trình sẽ hoạt động miệt mài. Khi gặp lỗi mạng hoặc token hết hạn, nó **tự động gọi file `login.bat` để phục hồi** và chạy tiếp mà không cần bạn can thiệp.

### 7.2. Khi hết nguồn hiện tại (`HẾT NGUỒN HIỆN TẠI`)
1. Vào NotebookLM, xoá nguồn PDF hiện tại, thêm file phần tiếp theo.
2. ```bash
   python translate_book.py --new-part
   ```
   Thêm `--last-part` nếu đó là phần cuối sách.

### 7.3. "Dịch chỉ định" (`--restart`) — làm mới hội thoại bằng tay

Mặc dù hệ thống đã có tính năng tự động làm mới hội thoại, nhưng nếu bạn muốn ép làm mới thủ công (ví dụ cần sửa lại một đoạn dịch sai từ nhiều ngày trước), dùng cờ:

```bash
python translate_book.py --restart
```
**Muốn neo vào một điểm CŨ hơn** (để dịch lại đoạn lỗi):
1. Mở `notes.log`, tìm câu tiếng Anh đúng + đoạn tiếng Việt tương ứng của
   vòng muốn quay về.
2. Mở `translation.md`, dùng đoạn tiếng Việt đó để Ctrl+F tìm đúng vị trí,
   xoá phần phía sau.
3. Mở `checkpoint.json`, sửa trường `"last_anchor"` = đúng câu tiếng Anh
   (lấy nguyên văn từ PDF gốc).
4. Chạy `python translate_book.py --restart`.

### 7.4. Tự động phục hồi cực mạnh (Không cần bạn làm gì)

- **Làm mới hội thoại định kỳ (Chống tràn context)**: Khi đạt đủ số `rounds_before_refresh`, script tự xoá hội thoại cũ, tạo hội thoại mới, nhồi câu neo tiếng Anh mới nhất vào. Dịch mượt mà tiếp tục.
- **Tự động đăng nhập lại (Auto-Relogin)**: Khi chạy đêm dài, cookie đăng nhập Google có thể hết hạn. Mã nguồn tự nhận diện các lỗi này, âm thầm gọi `login.bat` (chạy `notebooklm login` trong background) để gia hạn token và dịch tiếp.
- **Phản hồi quá lớn** (`RPCResponseTooLargeError`): Khi NotebookLM cố search mạng vì cạn nguồn, script tự động kích hoạt tiến trình RESTART để phục hồi. 
- **Google Doc gần chạm giới hạn 1.024.000 ký tự**: Script tự mở Doc "Phần N" mới nối tiếp.

### 7.5. Hiệu chỉnh khẩn cấp — nguồn `addition` (tuỳ chọn)

Khi cần chỉnh gấp mà không muốn sửa `prompt.txt`/`automation_rules.txt`: vào NotebookLM → **Add source → Paste text** → viết hướng dẫn
cần thiết → đặt tên nguồn đúng là **`addition`**. Chạy xong xoá nó đi.

---

## 8. Tránh hết hạn phiên đăng nhập (ĐÃ TỰ ĐỘNG HOÁ)

Trước đây người dùng cần cài Task Scheduler, Crontab hay dùng các mẹo `--master-token` nguy hiểm. **Hiện tại việc này là không cần thiết nữa!**

Mã nguồn Python đã được thiết kế để theo dõi chặt chẽ tính toàn vẹn của kết nối. Khi nó nhận thấy kết nối tới Google thất bại (Authentication expired), nó sẽ trực tiếp kích hoạt lệnh trong file `login.bat` của bạn để gia hạn. Nhờ cơ chế tự động giữ phiên mới của công cụ dòng lệnh NotebookLM, mọi thứ sẽ diễn ra âm thầm trong nền. Bạn có thể thoải mái treo máy!

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

Bước này dùng **`pandoc`** — một chương trình cài ở cấp hệ điều hành, **không
phải** thư viện Python nên `uv pip install` ở mục 2.3 **không** cài được nó.
Cần cài riêng, **một lần duy nhất** (giống mục 2.1), trước khi chạy lệnh
`pandoc` bên dưới.

**Cài `pandoc`:**

**Windows (PowerShell hoặc Command Prompt, có sẵn từ Windows 10+):**
```powershell
winget install --id JohnMacFarlane.Pandoc
```
> Nếu máy không có `winget`, tải bộ cài `.msi` trực tiếp tại
> [pandoc.org/installing.html](https://pandoc.org/installing.html).
> Đóng và mở lại terminal sau khi cài để lệnh `pandoc` được nhận.

**macOS (Terminal, cần [Homebrew](https://brew.sh) — cài 1 lần nếu chưa có):**
```bash
brew install pandoc
```

Kiểm tra đã cài đúng:
```bash
pandoc --version
```

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

## 10. Xử lý sự cố thường gặp (Troubleshooting)

Hầu hết các lỗi đã được tự động xử lý bởi mã nguồn, tuy nhiên đây là một số kịch bản bạn có thể theo dõi:

| Sự cố | Hiện tượng & Nguyên nhân | Cách hệ thống hoặc bạn xử lý |
|---|---|---|
| Mạng chập chờn, rớt kết nối mạng nội bộ | Báo lỗi kết nối Timeout | Script sẽ thử khởi động lại kết nối. Nếu nhà bạn mất mạng hoàn toàn, quá trình dịch sẽ tạm dừng cho đến khi bạn bật lại script. |
| NotebookLM Server quá tải | Văng lỗi HTTP 500 hoặc NetworkError đột xuất | Script sẽ bắt lỗi, chờ và thực hiện tự động tạo phiên (Restart) hoặc gọi lại `login.bat` để làm tươi kết nối và tự động thử lại. |
| Dùng chung tài khoản | Nếu người khác truy cập cùng lúc và huỷ phiên | Lỗi không xác thực. Script tự động gọi `login.bat` để xin lại Token. Vẫn giữ nguyên neo cũ không ảnh hưởng tài liệu. |
| `RPCResponseTooLargeError` | AI tìm nguồn ngoài do nguồn tài liệu đã cạn | Tự động kích hoạt làm mới hội thoại; Nếu vẫn bị lặp lại liên tục, bạn cần kiểm tra file PDF gốc đã dịch đến trang cuối chưa và tiến hành cấp nguồn mới. |
| `ModuleNotFoundError` | Quên kích hoạt `.venv` | Kích hoạt lại môi trường ảo: `.venv\Scripts\activate` hoặc `source .venv/bin/activate` |

---

## 11. Cấu trúc file trong thư mục dự án

| File | Vai trò | Ai quản lý |
|---|---|---|
| `translate_book.py` | Script chính | Không tự sửa trừ khi đổi logic |
| `config.json` | Cấu hình riêng từng sách | Sửa mỗi khi đổi sách |
| `login.bat` | Script hỗ trợ lấy Token | Tạo một lần, để Script tự gọi lại khi cần |
| `credentials.json` | OAuth Client Google Drive | Lấy 1 lần, dùng chung mọi sách |
| `token.json` | Phiên đăng nhập Drive đã lưu | Tự sinh |
| `checkpoint.json` | Tiến độ + `last_anchor` (câu neo tự cập nhật) | Tự sinh; sửa tay khi cần neo điểm khác |
| `translation.md` | Toàn bộ bản dịch — **nguồn dữ liệu thật** | Tự sinh, tự sửa khi cần dịch chỉ định |
| `translation.backup.md` | Bản sao lưu an toàn | Tự sinh |
| `notes.log` | Câu neo tiếng Anh + đoạn tiếng Việt tương ứng mỗi vòng | Tự sinh |

---

## 12. Nguyên tắc nên nhớ

- **Luôn theo dõi định kỳ** — dù có nhiều lớp tự động, thi thoảng cũng nên liếc qua quá trình nó dịch xem mọi thứ có đi đúng hướng không.
- **Lưu ý số lượng `rounds_before_refresh`** — Phải chắc chắn file cấu hình có dòng này để tránh tràn Memory / Context của NotebookLM.
- **`translation.md`/`translation.backup.md` mới là nguồn thật** — Google
  Doc chỉ là cửa sổ theo dõi tạm thời. Dù quá trình đẩy lên Docs bị lỗi mạng, nội dung dịch vẫn được lưu 100% về ổ cứng của bạn trong MD file an toàn.
- **Không cần Docker/máy ảo gì thêm** — `.venv` là đủ cho quy mô dự án này.
