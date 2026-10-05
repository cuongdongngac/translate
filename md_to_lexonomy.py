#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_lexonomy.py
Chuyển đổi trực tiếp từ translation.md sang file XML chuẩn của Lexonomy.
Bỏ qua hoàn toàn khâu trung gian Word (.docx).
"""

import sys
import re
from pathlib import Path
import xml.etree.ElementTree as ET

# Thẻ <def>/<image> có thể xuất hiện dưới 3 kiểu, thử theo thứ tự này:
#   1) `<tag>`   - bọc backtick (KHUYẾN NGHỊ - chuẩn hiện tại của prompt.txt)
#   2) \<tag>    - gạch chéo ngược phía trước (kiểu cũ, giữ để tương thích ngược)
#   3) <tag>     - trần, không escape gì (phòng hờ cuối cùng)
# Backtick được ưu tiên vì KHÔNG dùng chung ký tự \ với cú pháp xuống hàng
# \\ trong LaTeX (ma trận, hệ phương trình) - tránh nguy cơ escape chồng lấn
# (vd. \\ trong ma trận bị lẫn với \ che thẻ, thành \\\ sai nghĩa).
def _tag_pattern(tag, closing=False):
    bare = f"<{'/' if closing else ''}{tag}>"
    return rf"(?:`{bare}`|\\{bare}|{bare})"


DEF_OPEN = _tag_pattern("def")
DEF_CLOSE = _tag_pattern("def", closing=True)
IMAGE_OPEN = _tag_pattern("image")
IMAGE_CLOSE = _tag_pattern("image", closing=True)

ENTRY_PATTERN = re.compile(
    r"#(?P<headword>[^#\n]+)#\s*" + DEF_OPEN + r"(?P<content>.*?)" + DEF_CLOSE,
    re.DOTALL | re.IGNORECASE
)

# Regex phân tích các thành phần bên trong định nghĩa
TOKEN_RE = re.compile(
    r"(?P<bold>\*\*(?P<b_text>.*?)\*\*)"
    r"|(?P<italic>\*(?P<i_text>.*?)\*)"
    r"|(?P<eq_block>`\$\$(?P<eq_b_code>.*?)\$\$`)"
    r"|(?P<eq_inline>`\$(?P<eq_i_code>.*?)\$`)"
    r"|(?P<image>" + IMAGE_OPEN + r"(?P<img_content>.*?)" + IMAGE_CLOSE + r")",
    re.DOTALL
)

SEPARATOR = r'`$$\star\qquad\star\qquad\star$$`'

# Dải phân cách THẬT SỰ ghi ra XML, khác với SEPARATOR ở trên (SEPARATOR chỉ
# dùng để TÌM/TÁCH trong markdown nguồn, không xuất hiện trong XML - xem lý
# do dùng \\ (backslash đôi) ở ghi chú tại LEXONOMY_BACKSLASH_DOUBLE bên
# dưới). Test import thực tế trên Lexonomy thật của user cho thấy TOÀN BỘ
# 7007 entry dữ liệu gốc đều dùng \\star\\qquad\\star (backslash đôi) cho
# dải phân cách - đây là bằng chứng thực tế, không phải suy đoán.
LEXONOMY_SEPARATOR_LINE = r"$$\\star\\qquad\\star\\qquad\\star$$"

# Ký tự điều khiển KHÔNG hợp lệ trong XML 1.0 (chỉ cho phép tab/LF/CR trong
# nhóm điều khiển). Nếu văn bản nguồn (do OCR lỗi/rác) lọt một trong các
# ký tự này vào, ElementTree vẫn ghi ra file bình thường KHÔNG báo lỗi gì,
# nhưng file XML kết quả sẽ KHÔNG hợp lệ (not well-formed) — Lexonomy hoặc
# bất kỳ trình đọc XML nào khác sẽ từ chối nạp, thường hiện ra trắng trang
# mà không rõ lý do. Phải lọc sạch TRƯỚC khi build cây XML.
ILLEGAL_XML_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff﷐-﷯￾￿]"
)


def sanitize_xml_text(text):
    """Xóa sạch ký tự điều khiển không hợp lệ trong XML, trả về (text_sach,
    so_ky_tu_da_xoa) để có thể cảnh báo người dùng biết chỗ nào cần soát lại."""
    cleaned, n = ILLEGAL_XML_CHARS_RE.subn("", text)
    return cleaned, n

# Các đoạn CÓ THỂ bị model/NotebookLM xuống dòng ở giữa (công thức dài, ma
# trận, hệ phương trình, ảnh) - phải gộp về MỘT dòng trước khi tách <line>,
# nếu không mỗi dòng con sẽ bị tách rời và TOKEN_RE ở trên sẽ không nhận
# diện được nữa (rơi về text thô, lộ nguyên dấu ` và $ ra ngoài).
EQUATION_OR_IMAGE_SPAN_RE = re.compile(
    r"`\$\$.*?\$\$`"      # công thức block  `$$...$$`
    r"|`\$.*?\$`"         # công thức inline `$...$`
    r"|" + IMAGE_OPEN + r".*?" + IMAGE_CLOSE,  # thẻ ảnh (backtick/\/trần)
    re.DOTALL
)


def normalize_multiline_tokens(text):
    """Gộp mọi khoảng trắng/xuống dòng NẰM BÊN TRONG một công thức hoặc thẻ
    ảnh thành một khoảng trắng đơn, để công thức luôn nằm gọn trên 1 dòng
    logic trước khi bị .split("\\n") tách theo dòng ở bước sau."""

    def _collapse(m):
        return re.sub(r"\s+", " ", m.group(0)).strip()

    return EQUATION_OR_IMAGE_SPAN_RE.sub(_collapse, text)


# Số hiệu trích dẫn NotebookLM TỰ CHÈN THÊM, dạng [1], [2, 3], [12-15]...
# Bằng chứng thực tế (2 lần test độc lập): dù prompt_tu_dien.txt đã yêu cầu
# RÕ RÀNG "XÓA BỎ toàn bộ nội dung trong ngoặc vuông", NotebookLM vẫn chèn
# nguyên các số này vào output — kể cả với PDF test không hề có trích dẫn
# nào trong nguồn gốc. Nhiều khả năng đây là tính năng "trích dẫn nguồn tự
# động" của chính nền tảng NotebookLM (chèn SAU khi model sinh văn bản),
# không phải token do model tự viết theo prompt — nên lời nhắc trong prompt
# không thể xử lý được, PHẢI lọc bằng code làm lưới an toàn.
# Chỉ khớp ngoặc vuông chứa THUẦN số/dấu phẩy/gạch ngang (vd. [1], [2, 3],
# [12-15]) — CỐ Ý không khớp ngoặc vuông có chữ cái, để không đụng nhầm nếu
# sau này khôi phục lại việc giữ trích dẫn học thuật kiểu [KA1 Chapter 8.].
CITATION_MARKER_RE = re.compile(r"\s?\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")


def strip_citation_markers(text):
    """Xoá số hiệu trích dẫn tự động của NotebookLM khỏi văn bản thuần
    (không áp dụng cho nội dung công thức/ảnh - xem chỗ gọi hàm này)."""
    return CITATION_MARKER_RE.sub("", text)


def append_mixed_markdown(parent_el, raw_text):
    """Phân tích markdown bold, italic, công thức và ảnh vào cây XML."""
    pos = 0
    for m in TOKEN_RE.finditer(raw_text):
        before = strip_citation_markers(raw_text[pos:m.start()])
        if before:
            if len(parent_el):
                parent_el[-1].tail = (parent_el[-1].tail or "") + before
            else:
                parent_el.text = (parent_el.text or "") + before

        if m.group("bold"):
            child = ET.SubElement(parent_el, "b")
            append_mixed_markdown(child, m.group("b_text"))

        elif m.group("italic"):
            child = ET.SubElement(parent_el, "i")
            append_mixed_markdown(child, m.group("i_text"))

        elif m.group("eq_block"):
            code = m.group("eq_b_code").strip()
            child = ET.SubElement(parent_el, "equation")
            child.text = f"$${code}$$"

        elif m.group("eq_inline"):
            code = m.group("eq_i_code").strip()
            child = ET.SubElement(parent_el, "math")
            child.text = f"${code}$"

        elif m.group("image"):
            child = ET.SubElement(parent_el, "image")
            child.text = m.group("img_content").strip()

        pos = m.end()

    tail = strip_citation_markers(raw_text[pos:])
    if tail:
        if len(parent_el):
            parent_el[-1].tail = (parent_el[-1].tail or "") + tail
        else:
            parent_el.text = (parent_el.text or "") + tail


def build_lexonomy_xml(md_content):
    md_content, n_stripped = sanitize_xml_text(md_content)
    if n_stripped:
        print(
            f"⚠ Đã lọc bỏ {n_stripped} ký tự điều khiển không hợp lệ (rác OCR) "
            "trước khi tạo XML — nên rà lại translation.md ở các mục từ liên quan."
        )

    # Thẻ gốc và cấu trúc <definition> khớp ĐÚNG với XML thật của Lexonomy
    # (kiểm chứng bằng cách soát file xuất thật 7007 entry của user): thẻ
    # gốc là <efsapap>, và mỗi entry chỉ có MỘT <definition> DUY NHẤT chứa
    # tuần tự các <line> - không tách definition_en/definition_vi như bản
    # cũ. Dải phân cách nằm NGAY TRONG <definition>, là một <line> bình
    # thường ở giữa các dòng tiếng Anh và tiếng Việt.
    root = ET.Element("efsapap")

    for match in ENTRY_PATTERN.finditer(md_content):
        headword = match.group("headword").strip()
        raw_def = match.group("content").strip()

        # Gộp công thức/ảnh nhiều dòng thành 1 dòng TRƯỚC khi tách <line>.
        raw_def = normalize_multiline_tokens(raw_def)

        entry_el = ET.SubElement(root, "entry")
        hw_el = ET.SubElement(entry_el, "headword")
        hw_el.text = headword

        def_el = ET.SubElement(entry_el, "definition")

        # Nếu có phân cách Anh - Việt
        if SEPARATOR in raw_def:
            parts = re.split(re.escape(SEPARATOR), raw_def)
            en_part = parts[0].strip() if len(parts) > 0 else ""
            vi_part = parts[1].strip() if len(parts) > 1 else ""

            for line in [l.strip() for l in en_part.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_el, "line")
                append_mixed_markdown(line_el, line)

            # Ghi lại chính dải phân cách vào XML (bản cũ bỏ hẳn dải này đi
            # sau khi tách - SAI so với dữ liệu thật, nơi dải phân cách vẫn
            # xuất hiện dưới dạng 1 <line> ở giữa).
            sep_line_el = ET.SubElement(def_el, "line")
            sep_line_el.text = LEXONOMY_SEPARATOR_LINE

            for line in [l.strip() for l in vi_part.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_el, "line")
                append_mixed_markdown(line_el, line)
        else:
            # Entry đơn (không có phân cách - không đúng chuẩn nhưng vẫn xử lý được)
            for line in [l.strip() for l in raw_def.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_el, "line")
                append_mixed_markdown(line_el, line)

    return root


CDATA_TAGS = ("equation", "math")
_CDATA_TARGET_RE = re.compile(
    r"<(?P<tag>" + "|".join(CDATA_TAGS) + r")>(?P<content>.*?)</(?P=tag)>",
    re.DOTALL,
)


def _unescape_xml_entities(s):
    # Thứ tự quan trọng: &amp; phải giải mã SAU CÙNG, nếu không "&amp;lt;"
    # sẽ bị giải sai thành "<" thay vì đúng ra là "&lt;".
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _safe_cdata(content):
    # CDATA không được chứa chuỗi "]]>" ở giữa - nếu công thức lỡ có (cực
    # hiếm), phải tách thành nhiều khối CDATA nối tiếp để không vỡ cấu trúc.
    return content.replace("]]>", "]]]]><![CDATA[>")


def _double_backslashes(content):
    """Lexonomy có một tầng xử lý phía sau (rất có thể là giải mã kiểu
    chuỗi JS/JSON) tự động "ăn" một lớp dấu \\ trước khi hiển thị công
    thức. Bằng chứng thực tế (không phải suy đoán): trong 7007 entry gốc
    của user, MỌI mã LaTeX đều dùng \\\\ (backslash đôi, vd. \\\\ce,
    \\\\star) - và khi test import 1 công thức MỚI viết \\ đơn (`\\frac`),
    Lexonomy hiển thị TRẮNG XÓA cả mục từ đó thay vì báo lỗi cụ thể.
    Cơ chế nhiều khả năng: \\f trong "\\frac" trùng đúng escape "form feed"
    của JS/JSON (\\b \\f \\n \\r \\t đều có nghĩa đặc biệt), một tầng
    unescape nội bộ của Lexonomy biến \\f thành ký tự điều khiển ẩn, làm
    hỏng cả JSON/khối dữ liệu chứa mục từ đó => cả trang trắng.
    => Quy tắc bắt buộc khi ghi XML cho Lexonomy: MỌI dấu \\ trong mã
    LaTeX phải được nhân đôi thành \\\\ trước khi ghi ra file, để sau khi
    Lexonomy tự "ăn" một lớp, phần còn lại là mã LaTeX \\ đơn đúng chuẩn."""
    return content.replace("\\", "\\\\")


def wrap_formulas_in_cdata(xml_string):
    """Sau khi ElementTree đã escape &lt; &gt; &amp; như bình thường, bọc
    riêng nội dung <equation> và <math> (mã LaTeX thô) vào CDATA, để giữ
    nguyên ký tự gốc thay vì entity — dễ đọc/dễ soát tay hơn khi mở XML,
    và tránh phụ thuộc vào việc Lexonomy có giải mã entity đúng hay không.
    Đồng thời nhân đôi dấu \\ (xem _double_backslashes) để khớp đúng quy
    ước Lexonomy đang dùng thật, tránh lặp lại lỗi "trắng trang" đã gặp."""

    def _repl(m):
        tag = m.group("tag")
        content = _unescape_xml_entities(m.group("content"))
        content = _double_backslashes(content)
        content = _safe_cdata(content)
        return f"<{tag}><![CDATA[{content}]]></{tag}>"

    return _CDATA_TARGET_RE.sub(_repl, xml_string)


def indent(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            indent(e, level + 1)
        if not e.tail or not e.tail.strip():
            e.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def main():
    if len(sys.argv) < 2:
        print(f"Cách dùng: python {sys.argv[0]} translation.md [output.xml]")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) >= 3 else input_file.with_suffix(".xml")

    raw_md = input_file.read_text(encoding="utf-8")
    root = build_lexonomy_xml(raw_md)
    indent(root)

    body = ET.tostring(root, encoding="unicode")
    body = wrap_formulas_in_cdata(body)
    xml_text = "<?xml version='1.0' encoding='utf-8'?>\n" + body + "\n"
    output_file.write_text(xml_text, encoding="utf-8")
    print(f"✓ Đã tạo thành công {output_file} từ {input_file} để nạp vào Lexonomy!")


if __name__ == "__main__":
    main()