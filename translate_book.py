"""
translate_book.py  (bản BÁN TỰ ĐỘNG - dùng khi sách bị chia thành nhiều file PDF gối đầu)
============================================================================================

BẠN LÀM TAY (trên web notebooklm.google.com):
    - Thêm / xoá nguồn (source) cho từng phần PDF (mỗi lần chỉ giữ 1 nguồn trong notebook).

SCRIPT LÀM TỰ ĐỘNG:
    - Gõ "Bắt đầu" / "Tiếp tục" thay bạn, lặp lại nhiều vòng.
    - Nhận diện khi nào dịch xong nguồn hiện tại (dừng lại chờ bạn đổi file).
    - Đẩy phần bản dịch (KHÔNG kèm ghi chú hệ thống) lên một Google Doc duy nhất,
      giữ định dạng (heading, in đậm, bảng...).

CẤU HÌNH: nằm trong file config.json (cùng thư mục) — KHÔNG sửa trong file .py này.
    Mỗi khi đổi sang sách mới, chỉ cần sửa config.json, không cần đụng vào script.

CÁCH DÙNG:

    1) Dịch bình thường trong file đang active (chạy nhiều lần liên tiếp tuỳ ý):
           python translate_book.py

    2) Khi màn hình báo "HẾT NGUỒN HIỆN TẠI - hãy đổi file":
           - Vào web NotebookLM: xoá nguồn cũ, thêm file phần tiếp theo (ví dụ tenfile_15_23.pdf)
           - Nếu ĐÂY LÀ FILE CUỐI CÙNG của cuốn sách, chạy:
                 python translate_book.py --new-part --last-part
           - Nếu KHÔNG PHẢI file cuối, chạy:
                 python translate_book.py --new-part

    3) Muốn dịch 1 cuốn sách MỚI: xoá 3 file translation.md, checkpoint.json, notes.log,
       rồi sửa notebook_id / doc_title trong config.json. Nhớ tự upload prompt.txt của
       sách mới làm nguồn trên web NotebookLM (đặt tên đúng GUIDE_TITLE bên dưới).

    4) "DỊCH CHỈ ĐỊNH" — khi cần làm mới hội thoại (lỗi, hội thoại quá dài, muốn sửa
       đoạn dịch sai...): checkpoint.json luôn tự lưu sẵn câu neo (last_anchor) của
       vòng thành công gần nhất, chỉ cần chạy:
           python translate_book.py --restart
       Muốn neo vào 1 điểm CŨ hơn: tự sửa tay trường "last_anchor" trong checkpoint.json
       trước khi chạy lệnh trên.
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from notebooklm import NotebookLMClient
from notebooklm.exceptions import RPCResponseTooLargeError, NetworkError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# ============ ĐƯỜNG DẪN FILE - CỐ ĐỊNH, KHÔNG CẦN SỬA ============

CONFIG_FILE = Path("config.json")         # <-- MỌI THỨ HAY ĐỔI (notebook, tên sách...) nằm ở đây
OUTPUT_FILE = Path("translation.md")
CHECKPOINT_FILE = Path("checkpoint.json")
LOG_FILE = Path("notes.log")
CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")
DOC_LINK_FILE = Path("google_doc_link.txt")   # nơi lưu link Doc để bạn mở lại dễ dàng
DOC_SAFE_CHAR_LIMIT = 900_000   # Google Docs giới hạn cứng 1.024.000 ký tự/tài liệu — chừa đệm an toàn
BACKUP_FILE = Path("translation.backup.md")   # bản sao lưu tự động, cập nhật sau mỗi vòng thành công
CUT_MARKER = "<!-- CUT_HERE -->"   # dán dòng này vào translation.md để đánh dấu điểm cắt, thay vì tự xoá tay
ADDITIONAL_GUIDANCE_TITLE = "addition"   # tên nguồn KHẨN CẤP (tuỳ chọn) — thêm tay trên
                                          # NotebookLM khi cần hiệu chỉnh gấp, xoá đi khi xong

# Bắt câu trích dẫn tiếng Anh trong khối "Đã dịch đến hết đoạn/câu: "..."" —
# dùng để TỰ ĐỘNG lấy điểm neo gần nhất, lưu vào checkpoint.json (trường
# "last_anchor"), cập nhật sau MỖI vòng thành công. Khi cần "dịch chỉ định",
# chỉ cần chạy: python translate_book.py --restart (không cần sửa file nào).
ANCHOR_PATTERN = re.compile(r'Đã dịch đến hết đoạn/câu:\s*"(.+?)"', re.DOTALL)

# Bắt số % tiến độ AI tự ước lượng trong khối "Ghi chú hệ thống" (ước lượng
# gần đúng, không cần chính xác tuyệt đối — chỉ để bạn theo dõi cho an tâm).
PROGRESS_PATTERN = re.compile(r'Tiến độ ước tính trong nguồn hiện tại:\s*(\d{1,3})\s*%')


def extract_progress(footer_text):
    """Trích % tiến độ (nếu có) từ một đoạn footer_text cụ thể."""
    if not footer_text:
        return None
    m = PROGRESS_PATTERN.search(footer_text)
    if not m:
        return None
    value = int(m.group(1))
    return min(value, 100)   # chặn trên 100% phòng AI ước lượng lệch


def get_last_good_anchor():
    """Đọc notes.log, trả về câu neo (trích dẫn tiếng Anh) của vòng THÀNH CÔNG
    gần nhất — dùng khi cần tự phục hồi mà checkpoint.json chưa kịp có
    last_anchor (ví dụ checkpoint cũ từ trước khi có tính năng này)."""
    if not LOG_FILE.exists():
        return None
    content = LOG_FILE.read_text(encoding="utf-8")
    matches = ANCHOR_PATTERN.findall(content)
    if not matches:
        return None
    return matches[-1].strip()


def extract_anchor(footer_text):
    """Trích câu neo (tiếng Anh) từ MỘT đoạn footer_text cụ thể (không đọc
    lại cả notes.log) — dùng để cập nhật state["last_anchor"] thụ động sau
    mỗi vòng thành công."""
    if not footer_text:
        return None
    m = ANCHOR_PATTERN.search(footer_text)
    return m.group(1).strip() if m else None

PART_DONE_MARKER = "HẾT NGUỒN HIỆN TẠI"    # AI sẽ in đúng dòng này khi hết nội dung nguồn hiện tại
FOOTER_TEXT_ANCHOR = "Ghi chú hệ thống"   # tìm theo cụm từ này, không tìm icon (icon có thể đổi)
GUIDE_TITLE = "prompt.txt"   # <-- SỬA cho khớp đúng TÊN bạn đặt khi upload prompt.txt làm nguồn
AUTOMATION_TITLE = "automation_rules.txt"   # <-- SỬA cho khớp TÊN bạn đặt khi upload file luật automation
AUTOMATION_EXPORT_FILE = Path("automation_rules.txt")   # script tự ghi file này để bạn copy lên NotebookLM
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Các quy tắc "hệ thống" phục vụ automation — KHÔNG nằm trong prompt.txt của bạn,
# để bạn tự do tuỳ biến prompt.txt theo từng sách mà không phải lo phần này.
# Script sẽ tự động ghép các quy tắc này vào lệnh "Bắt đầu" đầu tiên.
AUTOMATION_RULES = """Báo hiệu hết nguồn: Nếu bạn nhận thấy đã dịch xong toàn bộ nội dung hiện có trong nguồn đang được cung cấp (không còn đoạn văn bản tiếng Anh nào chưa dịch trong tài liệu hiện tại), hãy in dòng chữ HẾT NGUỒN HIỆN TẠI ở ngay dòng đầu tiên của câu trả lời, sau đó dừng lại, không bịa thêm nội dung.

Xử lý trang gối đầu: Nếu ở đầu tài liệu có một trang ghi chú dạng "File goc: ... / Phan X/Y - Trang goc: ... / Luu y: cac trang ... trung voi phan truoc, dung de noi mach ngu canh", đó là dấu hiệu tài liệu này là một phần được cắt ra từ sách lớn, và vài trang đầu bị lặp lại từ phần trước. Các trang lặp lại này CHỈ dùng để bạn hiểu bối cảnh nối mạch — TUYỆT ĐỐI KHÔNG dịch lại nội dung của các trang đó, hãy bắt đầu dịch từ đoạn nội dung mới ngay sau phần trùng lặp.

Xử lý câu bị cắt cụt ở cuối nguồn: Vì nguồn được cắt theo SỐ TRANG (không theo câu), rất có thể câu/đoạn văn cuối cùng trong tài liệu hiện tại bị cắt ngang, chưa trọn vẹn. Nếu bạn thấy nội dung nguồn kết thúc giữa chừng một câu, một đoạn văn, hoặc một bảng biểu (không hoàn chỉnh), TUYỆT ĐỐI KHÔNG dịch phần dang dở đó — hãy dừng lại ở câu/đoạn hoàn chỉnh gần nhất trước đó, rồi báo HẾT NGUỒN HIỆN TẠI như bình thường. Phần dang dở này sẽ xuất hiện đầy đủ và được dịch chính xác khi bạn nhận được nguồn của phần tiếp theo (đã lặp lại đủ các trang gối đầu để hoàn thiện câu/đoạn đó).

Không hỏi lại, không bình luận thêm: Chỉ trả lời đúng 2 phần theo định dạng bắt buộc (bản dịch + khối "📌 Ghi chú hệ thống"). TUYỆT ĐỐI KHÔNG hỏi lại tôi có muốn tiếp tục không, không thêm bất kỳ câu dẫn dắt, bình luận, tóm tắt tiến độ, hay câu hỏi nào khác ở đầu hoặc cuối câu trả lời ngoài 2 phần đã quy định. Luôn dùng ĐÚNG icon 📌 (không đổi icon khác) và giữ khối "Ghi chú hệ thống" đúng NGUYÊN VĂN mẫu đã quy định.

Tự soát lại trước khi trả lời (quan trọng nhất): Trước khi gửi câu trả lời, hãy tự đọc lại toàn bộ phần BẢN DỊCH bạn vừa viết (không tính khối "Ghi chú hệ thống" ở cuối) và tự hỏi: "Mỗi câu trong phần này có phải là bản dịch THUẦN TÚY từ nội dung sách gốc hay không?" Nếu phát hiện BẤT KỲ câu/đoạn nào không phải là nội dung sách — dù là lời chào, lời dẫn dắt, câu hỏi hướng đến tôi (người ra lệnh), bình luận về tiến độ, dự báo nội dung sắp tới, xin phép làm việc gì đó, hay bất kỳ hình thức giao tiếp nào khác ngoài việc thuật lại đúng nội dung sách — hãy TỰ XÓA hoàn toàn những câu/đoạn đó trước khi gửi câu trả lời, CHỈ giữ lại phần dịch sách thật sự. Đây là quy tắc tổng quát, áp dụng cho MỌI hình thức nội dung ngoài phạm vi sách, không chỉ giới hạn ở các ví dụ đã liệt kê.

Không chèn số hiệu trích dẫn: KHÔNG được thêm bất kỳ số hiệu trích dẫn nào dạng [1], [2], [8]... vào bất kỳ đâu trong câu trả lời — kể cả trong phần bản dịch lẫn trong câu trích dẫn tiếng Anh ở phần "Ghi chú hệ thống". Chỉ đưa ra văn bản thuần tuý, không kèm ký hiệu trích dẫn nào.

Không nhảy cóc, tự kiểm tra vị trí trước khi trả lời: Luôn dịch TUẦN TỰ, LIÊN TỤC theo đúng thứ tự xuất hiện trong nguồn. TUYỆT ĐỐI KHÔNG bỏ qua (nhảy cóc) bất kỳ đoạn nội dung nào chỉ vì nó khó dịch (công thức phức tạp, bảng dày đặc, đoạn OCR lỗi nặng) — nếu gặp khó, hãy cố gắng dịch hết khả năng và giữ placeholder theo đúng quy tắc, KHÔNG được bỏ qua để dịch tiếp đoạn sau. Trước khi trả lời, hãy tự xác nhận rằng điểm bắt đầu của lượt này nối tiếp ĐÚNG NGAY SAU điểm kết thúc của lượt trước theo lịch sử hội thoại — nếu cảm thấy không chắc chắn về vị trí, hãy dừng lại và nói rõ sự không chắc chắn đó thay vì tự đoán và nhảy tới một vị trí khác trong sách.

Trích dẫn điểm kết thúc đủ dài để tránh nhầm lẫn: Khi trích dẫn câu tiếng Anh cuối cùng trong "Ghi chú hệ thống", hãy trích ĐỦ DÀI (câu cuối cùng VÀ câu ngay trước đó, khoảng 2 câu liền nhau) — KHÔNG trích một cụm từ ngắn hoặc chung chung dễ trùng lặp. Lý do: sách có thể lặp lại công thức/thuật ngữ/câu mẫu ở nhiều chương khác nhau, trích dẫn quá ngắn dễ khiến việc xác định điểm tiếp tục ở lượt sau bị nhầm sang một vị trí khác có nội dung tương tự.

Dịch từ trang đầu tiên có văn bản, không bỏ qua phần mở đầu: Ngay từ lượt "Bắt đầu" đầu tiên, bạn PHẢI bắt đầu dịch từ chính TRANG ĐẦU TIÊN có nội dung văn bản thật sự trong nguồn — bao gồm cả Lời tựa (Preface), Lời giới thiệu (Introduction), Lời cảm ơn (Acknowledgments), Danh mục thuật ngữ/tổ chức được nhắc đến, và mọi phần văn bản khác xuất hiện TRƯỚC Chương 1/Chapter 1. TUYỆT ĐỐI KHÔNG tự ý phán đoán rằng những phần này "không quan trọng" hay "không phải nội dung chính" rồi nhảy thẳng vào Chương 1 — mọi trang có chữ đều phải được dịch tuần tự, kể cả khi đó chỉ là lời cảm ơn hay danh sách tên người. Chỉ được bỏ qua các trang THỰC SỰ không có văn bản (bìa trang trí thuần hình ảnh, bản đồ không chữ, trang trắng).

Không được tìm kiếm internet khi hết nguồn: Khi đã dịch hết toàn bộ nội dung hiện có trong nguồn được cung cấp, TUYỆT ĐỐI KHÔNG cố gắng tìm kiếm, tra cứu, hay mở rộng thông tin từ Internet hoặc bất kỳ nguồn nào khác ngoài (các) nguồn đã được cung cấp trong notebook này — kể cả khi hệ thống có gợi ý hỏi bạn có muốn tìm kiếm internet không, hãy TỪ CHỐI và bỏ qua gợi ý đó. Chỉ cần in dòng chữ HẾT NGUỒN HIỆN TẠI ở đầu câu trả lời (theo đúng quy tắc "Báo hiệu hết nguồn" ở trên) rồi dừng lại ngay lập tức. Không thực hiện bất kỳ hành động nào khác.

Kèm ước lượng tiến độ: Trong khối "Ghi chú hệ thống", NGAY SAU dòng "Đã dịch đến hết đoạn/câu...", thêm đúng một dòng mới theo mẫu: Tiến độ ước tính trong nguồn hiện tại: X% (X là số nguyên từ 0 đến 100). Đây chỉ là ước lượng gần đúng của bạn về vị trí hiện tại so với tổng độ dài nội dung trong nguồn đang được cung cấp (ví dụ dựa theo số trang, số chương, hoặc cảm nhận tổng thể) — không cần chính xác tuyệt đối, chỉ cần là một con số hợp lý giúp người dùng theo dõi tiến độ."""


def load_config():
    if not CONFIG_FILE.exists():
        sample = json.dumps(
            {
                "notebook_id": "dán-id-notebook-vào-đây",
                "doc_title": "Tên hiển thị cho Google Doc",
                "target_folder_id": "",
                "rounds_per_run": 5,
                "rounds_before_refresh": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        print(
            f"KHÔNG TÌM THẤY {CONFIG_FILE}.\n"
            "Hãy tạo file config.json cùng thư mục, nội dung mẫu:\n" + sample
        )
        raise SystemExit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))



# ===================================================


def get_drive_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def push_markdown_to_doc(drive_service, doc_id, title, target_folder_id, content):
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/markdown", resumable=True)
    if doc_id is None:
        metadata = {"name": title, "mimeType": "application/vnd.google-apps.document"}
        if target_folder_id:
            metadata["parents"] = [target_folder_id]
        file = drive_service.files().create(body=metadata, media_body=media, fields="id").execute()
        return file["id"]
    else:
        drive_service.files().update(fileId=doc_id, media_body=media).execute()
        return doc_id


def parse_answer(raw_answer: str):
    text = raw_answer.strip()
    part_done = False

    lines = text.split("\n")
    if lines and PART_DONE_MARKER in lines[0]:
        part_done = True
        text = "\n".join(lines[1:]).strip()

    # Tìm theo CỤM TỪ "Ghi chú hệ thống" thay vì chỉ tìm đúng icon 📌 — vì AI
    # thỉnh thoảng đổi icon khác (🎧, 📚, 📖, 🔍, 📊...) nhưng luôn giữ đúng cụm
    # từ này. Nếu chỉ tìm icon cố định, các biến thể icon khác sẽ "lọt lưới"
    # và bị coi nhầm là bản dịch thật, lẫn vào translation.md.
    footer_idx = text.find(FOOTER_TEXT_ANCHOR)
    footer_missing = footer_idx == -1
    if not footer_missing:
        line_start = text.rfind("\n", 0, footer_idx)
        split_at = line_start + 1 if line_start != -1 else 0
        translation_text = text[:split_at].strip()
        footer_text = text[split_at:].strip()
    else:
        translation_text = text
        footer_text = ""

    return translation_text, footer_text, part_done, footer_missing


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        state = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        state.setdefault("doc_offset", 0)          # tương thích ngược cho checkpoint cũ
        state.setdefault("doc_part_number", 1)      # tương thích ngược cho checkpoint cũ
        state.setdefault("rounds_since_refresh", 0)  # tương thích ngược cho checkpoint cũ
        state.setdefault("last_anchor", None)        # tương thích ngược cho checkpoint cũ
        state.setdefault("last_progress_percent", None)  # tương thích ngược cho checkpoint cũ
        return state
    return {
        "conversation_id": None,
        "round": 0,
        "part_number": 1,
        "waiting_for_new_part": False,
        "book_finished": False,
        "doc_id": None,
        "doc_offset": 0,
        "doc_part_number": 1,
        "rounds_since_refresh": 0,
        "last_anchor": None,
        "last_progress_percent": None,
    }


def save_checkpoint(state):
    CHECKPOINT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_translation(text):
    with OUTPUT_FILE.open("a", encoding="utf-8") as f:
        f.write(text.strip() + "\n\n")


VN_SNIPPET_LENGTH = 250   # số ký tự tiếng Việt cuối cùng trích kèm câu neo, để dễ dò trong translation.md


def append_log(footer_text, translation_text):
    if not footer_text:
        return
    vn_snippet = translation_text.strip()[-VN_SNIPPET_LENGTH:] if translation_text else ""
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(footer_text.strip() + "\n")
        if vn_snippet:
            f.write(
                "--- Đoạn tiếng Việt tương ứng (cuối vòng này, để dò trong "
                f"{OUTPUT_FILE}) ---\n...{vn_snippet}\n"
            )
        f.write("\n")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--new-part", action="store_true",
        help="Dùng NGAY SAU KHI bạn đã tự đổi nguồn (xoá file cũ, thêm file mới) trên web NotebookLM."
    )
    parser.add_argument(
        "--last-part", action="store_true",
        help="Kết hợp với --new-part: báo đây là file CUỐI CÙNG của cuốn sách."
    )
    parser.add_argument(
        "--restart", action="store_true",
        help=(
            "DỊCH CHỈ ĐỊNH: xoá hội thoại cũ trên server, tạo hội thoại mới tinh, neo "
            "vào state['last_anchor'] trong checkpoint.json (câu tiếng Anh của vòng "
            "thành công gần nhất — tự động cập nhật sau mỗi vòng, không cần bạn tự "
            "tìm/sửa file nào). Muốn neo vào 1 điểm CŨ hơn thay vì điểm gần nhất: tự "
            "mở checkpoint.json, sửa tay trường \"last_anchor\" trước khi chạy lệnh này."
        )
    )
    parser.add_argument(
        "--rounds", type=int, default=None, metavar="N",
        help=(
            "Số vòng dịch tối đa cho lần chạy này — ƯU TIÊN HƠN rounds_per_run trong "
            "config.json. Nếu dùng cờ này, giá trị cũng sẽ được LƯU LẠI vào "
            "config.json, làm mặc định cho các lần chạy sau (khi không dùng cờ này)."
        )
    )
    args = parser.parse_args()

    state = load_checkpoint()

    # DỊCH CHỈ ĐỊNH: kích hoạt bằng cờ --restart, dùng câu neo đã tự động lưu
    # sẵn trong checkpoint.json (trường "last_anchor", cập nhật sau MỖI vòng
    # thành công) — không cần file riêng, không cần tự tìm/copy trong notes.log.
    restart_anchor = None
    conversation_id_to_delete = None
    if args.restart:
        restart_anchor = state.get("last_anchor") or get_last_good_anchor()
        if not restart_anchor:
            print(
                "Bật --restart nhưng chưa có câu neo nào trong checkpoint.json "
                "(trường last_anchor) và cũng không tìm thấy trong notes.log — "
                "có thể đây là lần chạy đầu tiên, chưa có vòng nào thành công."
            )
            return
        conversation_id_to_delete = state["conversation_id"]   # lưu lại để xoá thật sau khi có client
        state["conversation_id"] = None
        state["rounds_since_refresh"] = 0   # hội thoại mới -> đếm lại từ đầu
        print(f"-> Chế độ DỊCH CHỈ ĐỊNH: sẽ tạo hội thoại mới, neo vào: \"{restart_anchor}\"\n")

        # Nếu bạn đã dán dòng CUT_MARKER vào translation.md thay vì tự tay xoá,
        # script tự cắt bỏ mọi thứ TỪ dòng đó trở đi (không cần bạn tự xoá tay).
        if OUTPUT_FILE.exists():
            current = OUTPUT_FILE.read_text(encoding="utf-8")
            if CUT_MARKER in current:
                kept = current.split(CUT_MARKER)[0].rstrip() + "\n\n"
                OUTPUT_FILE.write_text(kept, encoding="utf-8")
                print(f"-> Đã tự động cắt translation.md tại vị trí dòng {CUT_MARKER}.\n")

    if state["book_finished"]:
        print(
            "Checkpoint báo đã dịch xong TOÀN BỘ sách rồi.\n"
            f"Xem bản dịch: mở file {DOC_LINK_FILE} để lấy link Google Doc.\n"
            "Muốn dịch sách khác: xoá checkpoint.json, translation.md, notes.log, "
            "rồi sửa config.json."
        )
        return

    # Luôn ghi ra file automation_rules.txt (ghi đè, cực nhẹ) để bạn tiện copy dán
    # lên NotebookLM làm nguồn cố định — script KHÔNG tự upload (theo đúng quyết
    # định trước đó: không phụ thuộc thư viện Python để dễ chuyển sang Go sau này).
    AUTOMATION_EXPORT_FILE.write_text(AUTOMATION_RULES, encoding="utf-8")
    if state["conversation_id"] is None:
        print(
            f"Lưu ý: nếu CHƯA upload nguồn '{AUTOMATION_TITLE}' lên NotebookLM, "
            f"hãy mở file {AUTOMATION_EXPORT_FILE}, copy toàn bộ, lên web NotebookLM: "
            f"Add source -> Paste text -> dán vào, đặt tên nguồn đúng: {AUTOMATION_TITLE}\n"
            "(chỉ cần làm 1 lần cho cả cuốn sách, đã làm rồi thì bỏ qua bước này)\n"
        )

    if state["waiting_for_new_part"] and not args.new_part:
        print(
            f"Đang chờ bạn đổi sang file phần {state['part_number']}.\n"
            "Vào web NotebookLM: xoá nguồn cũ, thêm file phần tiếp theo, rồi chạy lại với:\n"
            "    python translate_book.py --new-part\n"
            "(thêm --last-part nữa nếu đây là file cuối cùng của sách)"
        )
        return

    if not CREDENTIALS_FILE.exists():
        print(f"KHÔNG TÌM THẤY {CREDENTIALS_FILE}.")
        return

    config = load_config()
    notebook_id = config["notebook_id"]
    doc_title = config["doc_title"]
    target_folder_id = config.get("target_folder_id", "")
    rounds_before_refresh = config.get("rounds_before_refresh", 0)   # 0 = tắt, không tự làm mới

    if args.rounds is not None:
        # Cờ --rounds ưu tiên hơn config.json, đồng thời LƯU LẠI làm mặc định mới
        # cho các lần chạy sau (khi không dùng cờ này) — đỡ phải mở file sửa tay.
        rounds_per_run = args.rounds
        config["rounds_per_run"] = args.rounds
        CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> Dùng --rounds {args.rounds} (đã lưu lại vào {CONFIG_FILE} làm mặc định mới).\n")
    else:
        rounds_per_run = config.get("rounds_per_run", 5)

    print("Đang đăng nhập Google Drive...")
    drive_service = get_drive_service()

    print(f"Đang kết nối tới notebook: {notebook_id}")

    if args.new_part:
        state["part_number"] += 1
        state["waiting_for_new_part"] = False
        print(f"-> Chuyển sang phần {state['part_number']} (đã đổi nguồn trên web).")

    print(f"Sẽ dịch tối đa {rounds_per_run} đoạn trong lần chạy này...\n")

    rounds_completed = 0

    while rounds_completed < rounds_per_run:
        if state.get("book_finished") or state.get("waiting_for_new_part"):
            break

        try:
            async with NotebookLMClient.from_storage(keepalive=300) as client:
                if conversation_id_to_delete:
                    try:
                        await client.chat.delete_conversation(notebook_id, conversation_id_to_delete)
                        print(f"-> Đã xoá hội thoại cũ ({conversation_id_to_delete}) trên server — hội thoại mới sẽ tách biệt thật sự.\n")
                    except Exception as e:
                        print(f"-> Không xoá được hội thoại cũ ({e})\n")
                    conversation_id_to_delete = None

                addition_note = ""
                try:
                    current_sources = await client.sources.list(notebook_id)
                    if any((s.title or "").strip().lower() == ADDITIONAL_GUIDANCE_TITLE for s in current_sources):
                        addition_note = (
                            f'\n\nLƯU Ý KHẨN CẤP: Notebook này hiện có thêm nguồn "'
                            f'{ADDITIONAL_GUIDANCE_TITLE}" chứa hướng dẫn hiệu chỉnh bổ sung — '
                            "hãy đọc kỹ nguồn đó và áp dụng NGAY vào câu trả lời này."
                        )
                        print(f'-> Phát hiện nguồn hiệu chỉnh khẩn cấp "{ADDITIONAL_GUIDANCE_TITLE}" — sẽ nhắc AI đọc thêm.\n')
                except Exception as e:
                    pass

                while rounds_completed < rounds_per_run:
                    if state.get("book_finished") or state.get("waiting_for_new_part"):
                        break

                    if restart_anchor:
                        question = (
                            f'Hãy đọc kỹ nguồn "{GUIDE_TITLE}" và nguồn "{AUTOMATION_TITLE}", '
                            "làm theo ĐÚNG vai trò, quy tắc, định dạng và các luật automation "
                            "trong 2 nguồn đó để dịch nội dung của (các) nguồn sách khác trong "
                            "notebook này."
                            "\n\nLƯU Ý ĐẶC BIỆT (chỉ áp dụng cho ĐÚNG câu trả lời này thôi, "
                            "không áp dụng cho các lượt 'Tiếp tục' sau này): Đây là một phiên KHÔI "
                            "PHỤC SAU LỖI. Bạn đang tiếp tục dịch một cuốn sách đã dịch dở, KHÔNG "
                            f'phải bắt đầu lại từ đầu. Đoạn đã dịch ĐÚNG và được giữ lại kết thúc ở '
                            f'câu tiếng Anh: "{restart_anchor}". Hãy tiếp tục dịch NGAY SAU câu đó, '
                            "tuyệt đối không dịch lại bất kỳ nội dung nào trước đó. Sau khi hoàn "
                            "thành câu trả lời NÀY, hãy quên hẳn hướng dẫn khôi phục này đi — từ "
                            "lượt 'Tiếp tục' kế tiếp trở đi, chỉ cần tiếp nối ĐÚNG NGAY SAU nội dung "
                            "bạn vừa dịch ở câu trả lời gần nhất, không quay lại tham chiếu câu neo "
                            "này nữa.\n\nTiếp tục"
                        )
                        print(f"[{rounds_completed + 1}/{rounds_per_run}] Gửi lệnh khôi phục (neo vào: \"{restart_anchor[:60]}...\")...")
                        restart_anchor = None
                    elif state["conversation_id"] is None:
                        question = (
                            f'Hãy đọc kỹ nguồn "{GUIDE_TITLE}" và nguồn "{AUTOMATION_TITLE}", '
                            "làm theo ĐÚNG vai trò, quy tắc, định dạng và các luật automation "
                            "trong 2 nguồn đó để dịch nội dung của (các) nguồn sách khác trong "
                            "notebook này.\n\nBắt đầu"
                        )
                        print(f"[{rounds_completed + 1}/{rounds_per_run}] Gửi lệnh 'Bắt đầu' (trỏ tới 2 nguồn hướng dẫn)...")
                    elif args.new_part and rounds_completed == 0:
                        question = (
                            "Tôi vừa chuyển sang phần dữ liệu tiếp theo của cùng cuốn sách "
                            "(đã xoá phần cũ, thêm nguồn mới). Nếu đầu tài liệu có trang ghi chú "
                            "báo các trang bị trùng lặp, đừng dịch lại các trang đó, chỉ dùng làm "
                            "ngữ cảnh. Tiếp tục dịch nối liền mạch từ chỗ dừng trước.\n\nTiếp tục"
                        )
                        print(f"[{rounds_completed + 1}/{rounds_per_run}] Gửi thông báo CHUYỂN FILE + lệnh 'Tiếp tục'...")
                    else:
                        question = "Tiếp tục"
                        print(f"[{rounds_completed + 1}/{rounds_per_run}] Gửi lệnh 'Tiếp tục'...")

                    question += addition_note

                    try:
                        result = await client.chat.ask(
                            notebook_id,
                            question,
                            conversation_id=state["conversation_id"],
                        )
                    except (RPCResponseTooLargeError, NetworkError) as e:
                        import traceback
                        error_traceback = traceback.format_exc()
                        print(
                            "\n⚠️  NotebookLM phản hồi bất thường (quá lớn hoặc mất kết nối giữa chừng).\n"
                            f"🔍 CHI TIẾT LỖI (DEBUG): {type(e).__name__} - {str(e)}\n"
                        )
                        print("-> TỰ ĐỘNG RESTART LẠI HỘI THOẠI (bảo toàn neo)...\n")
                        restart_anchor = state.get("last_anchor") or get_last_good_anchor()
                        if restart_anchor:
                            conversation_id_to_delete = state["conversation_id"]
                            state["conversation_id"] = None
                            state["rounds_since_refresh"] = 0
                            save_checkpoint(state)
                            break
                        else:
                            print("Không tìm thấy điểm neo để restart! Dừng lại.")
                            return
                    except Exception as e:
                        raise e

                    translation_text, footer_text, part_done, footer_missing = parse_answer(result.answer)
                    if footer_missing:
                        anchor = state.get("last_anchor") or get_last_good_anchor()
                        if anchor:
                            state["last_anchor"] = anchor
                            save_checkpoint(state)
                            print(
                                f"   ⚠️  Câu trả lời vòng này KHÔNG có khối \"{FOOTER_TEXT_ANCHOR}\" "
                                "— có thể bị lỗi/cắt cụt giữa chừng. KHÔNG lưu nội dung vòng này "
                                f"vào {OUTPUT_FILE} (để tránh lẫn nội dung không đáng tin).\n"
                                "   -> TỰ ĐỘNG RESTART LẠI HỘI THOẠI (bảo toàn neo)...\n"
                            )
                            restart_anchor = anchor
                            conversation_id_to_delete = state["conversation_id"]
                            state["conversation_id"] = None
                            state["rounds_since_refresh"] = 0
                            break
                        else:
                            print(
                                f"   ⚠️  CẢNH BÁO: câu trả lời vòng này KHÔNG có khối "
                                f'"{FOOTER_TEXT_ANCHOR}", và không tìm thấy điểm neo cũ nào trong '
                                f"{LOG_FILE} để tự phục hồi. Nội dung vẫn được lưu vào {OUTPUT_FILE}."
                            )
                            append_translation(translation_text)
                            return

                    state["conversation_id"] = result.conversation_id
                    state["round"] += 1
                    rounds_completed += 1

                    append_translation(translation_text)
                    append_log(footer_text, translation_text)

                    new_anchor = extract_anchor(footer_text)
                    if new_anchor:
                        state["last_anchor"] = new_anchor

                    progress = extract_progress(footer_text)
                    if progress is not None:
                        state["last_progress_percent"] = progress
                        print(f"   -> Tiến độ ước tính trong nguồn hiện tại: {progress}%")

                    save_checkpoint(state)

                    full_content = OUTPUT_FILE.read_text(encoding="utf-8")
                    doc_offset = state.get("doc_offset", 0)
                    segment = full_content[doc_offset:]

                    is_new_doc = state["doc_id"] is None
                    if state["doc_id"] is not None and len(segment) > DOC_SAFE_CHAR_LIMIT:
                        state["doc_part_number"] = state.get("doc_part_number", 1) + 1
                        doc_offset = len(full_content) - len(translation_text) - 2
                        doc_offset = max(doc_offset, 0)
                        segment = full_content[doc_offset:]
                        is_new_doc = True
                        state["doc_id"] = None
                        print(f"   -> Google Doc hiện tại đã gần đầy — tự động mở Doc PHẦN {state['doc_part_number']} mới.")

                    part_doc_title = doc_title if state.get("doc_part_number", 1) == 1 else (
                        f"{doc_title} (Phần {state['doc_part_number']})"
                    )

                    try:
                        new_doc_id = push_markdown_to_doc(
                            drive_service, state["doc_id"], part_doc_title, target_folder_id, segment
                        )
                        state["doc_id"] = new_doc_id
                        state["doc_offset"] = doc_offset
                        save_checkpoint(state)
                        BACKUP_FILE.write_text(full_content, encoding="utf-8")

                        doc_link = f"https://docs.google.com/document/d/{state['doc_id']}/edit"
                        if is_new_doc:
                            with DOC_LINK_FILE.open("a", encoding="utf-8") as f:
                                f.write(f"Phần {state.get('doc_part_number', 1)}: {doc_link}\n")
                            print(f"   -> Đã tạo Google Doc mới: {doc_link}")
                        else:
                            print(f"   -> xong ({len(translation_text)} ký tự đã đẩy lên Google Doc)")
                    except Exception as e:
                        print(f"\n⚠️  Đẩy lên Google Doc bị lỗi: {e}\nBản dịch vẫn lưu an toàn nội bộ.\n")

                    state["rounds_since_refresh"] = state.get("rounds_since_refresh", 0) + 1
                    if rounds_before_refresh > 0 and state["rounds_since_refresh"] >= rounds_before_refresh:
                        if state.get("last_anchor"):
                            print("\n-> Tự động làm mới hội thoại định kỳ (giữ nguyên câu neo)...")
                            restart_anchor = state.get("last_anchor")
                            conversation_id_to_delete = state["conversation_id"]
                            state["conversation_id"] = None
                            state["rounds_since_refresh"] = 0
                            save_checkpoint(state)
                            break

                    if part_done:
                        if args.last_part:
                            state["book_finished"] = True
                            save_checkpoint(state)
                            print("HOÀN TẤT: Đã dịch xong TOÀN BỘ sách (đây là file cuối cùng)!")
                        else:
                            state["waiting_for_new_part"] = True
                            save_checkpoint(state)
                            print(
                                f"Đã dịch xong hết nội dung phần {state['part_number']}.\n"
                                "=> Vào web NotebookLM: xoá nguồn hiện tại, thêm file phần tiếp theo.\n"
                                "=> Rồi chạy lại: python translate_book.py --new-part\n"
                                "   (thêm --last-part nếu đó là file cuối cùng của sách)"
                            )
                        break

        except Exception as e:
            print(f"\n⚠️ Lỗi kết nối hoặc xác thực: {e}")
            print("-> Tự động gọi login.bat để thử relogin...")
            import subprocess
            subprocess.run(["login.bat"], shell=True)
            print("-> Đã relogin, đang thử lại...\n")
            import time
            time.sleep(2)

    if not state.get("book_finished") and not state.get("waiting_for_new_part"):
        progress_note = ""
        if state.get("last_progress_percent") is not None:
            progress_note = f" (~{state['last_progress_percent']}% nguồn hiện tại)"
        print(
            f"Xong {state.get('round')} vòng (đang ở phần {state.get('part_number')}){progress_note}. "
            "Chạy lại 'python translate_book.py' để dịch tiếp."
        )

if __name__ == "__main__":
    asyncio.run(main())
