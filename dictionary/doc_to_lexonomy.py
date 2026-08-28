#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from docx import Document


# ── 1. Đọc docx, giữ bold/italic ở cấp run ──────────────────────────────────

def runs_to_tagged(paragraph):
    """
    Chuyển các run trong 1 paragraph thành chuỗi có tag nội tuyến:
      <b>…</b>   → bold
      <i>…</i>   → italic
      <bi>…</bi> → bold+italic
    Text thường giữ nguyên.
    """
    parts = []
    for run in paragraph.runs:
        t = run.text
        if not t:
            continue
        bold = run.bold
        italic = run.italic
        if bold and italic:
            parts.append(f"<bi>{t}</bi>")
        elif bold:
            parts.append(f"<b>{t}</b>")
        elif italic:
            parts.append(f"<i>{t}</i>")
        else:
            parts.append(t)
    return "".join(parts)


def read_docx(filename):
    """Đọc docx, GIỮ NGUYÊN từng paragraph riêng biệt bằng \n."""
    doc = Document(filename)
    lines = [runs_to_tagged(p) for p in doc.paragraphs]
    return "\n".join(lines)


# ── 2. Normalize ──────────────────────────────────────────────────────────────

def normalize(text):
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ── 3. Parse entries ──────────────────────────────────────────────────────────

def parse_entries(text):
    # Linh hoạt: Bắt cả <def>, \<def>, <def\> (đề phòng OCR/Word dính backslash)
    pattern = re.compile(
        r"#(?P<headword>[^#\n]+)#\s*\\?<def>?(.*?)\\?</def>?",
        re.DOTALL | re.IGNORECASE
    )
    entries = []
    for match in pattern.finditer(text):
        headword = match.group("headword").strip()
        raw_def = match.group(2).strip()
        paragraphs = [
            line.strip()
            for line in raw_def.split("\n")
            if line.strip()
        ]
        entries.append((headword, paragraphs))
    return entries


# ── 4. Build XML, parse tag nội tuyến & công thức LaTeX ──────────────────────

# Bắt đồng thời: <b>, <i>, <bi>, công thức Block `$$...$$` và Inline `$..$`
TOKEN_RE = re.compile(
    r"(?P<tag><(?P<tagname>b|i|bi)>(?P<tagcontent>.*?)</(?P=tagname)>)"
    r"|(?P<eq_block>`\$\$(?P<eq_b_code>.*?)\$\$`)"
    r"|(?P<eq_inline>`\$(?P<eq_i_code>.*?)\$`)"
    r"|(?P<image><image>(?P<img_content>.*?)</image>)",
    re.DOTALL
)


def append_mixed_content(parent_el, raw_text):
    """
    Phân tích raw_text chứa text, tag style (<b>, <i>) và LaTeX formulas,
    sau đó chuyển thành cây XML lồng nhau hợp lệ.
    """
    pos = 0
    for m in TOKEN_RE.finditer(raw_text):
        # Phần text thường trước token
        before = raw_text[pos:m.start()]
        if before:
            if len(parent_el):
                last = parent_el[-1]
                last.tail = (last.tail or "") + before
            else:
                parent_el.text = (parent_el.text or "") + before

        # Xử lý theo từng loại Token
        if m.group("tag"):
            tag_name = m.group("tagname")
            content = m.group("tagcontent")
            child = ET.SubElement(parent_el, tag_name)
            # Đệ quy kiểm tra bên trong bold/italic có dính công thức không
            append_mixed_content(child, content)

        elif m.group("eq_block"):
            code = m.group("eq_b_code").strip()
            child = ET.SubElement(parent_el, "equation")
            child.text = f"$${code}$$"  # Lexonomy / MathJax sẽ render thẻ này

        elif m.group("eq_inline"):
            code = m.group("eq_i_code").strip()
            child = ET.SubElement(parent_el, "math")
            child.text = f"${code}$"

        elif m.group("image"):
            child = ET.SubElement(parent_el, "image")
            child.text = m.group("img_content").strip()

        pos = m.end()

    # Phần text thuần còn lại phía sau
    tail = raw_text[pos:]
    if tail:
        if len(parent_el):
            last = parent_el[-1]
            last.tail = (last.tail or "") + tail
        else:
            parent_el.text = (parent_el.text or "") + tail


def build_xml(entries):
    root = ET.Element("dictionary")
    for headword, paragraphs in entries:
        entry = ET.SubElement(root, "entry")
        hw = ET.SubElement(entry, "headword")
        hw.text = headword

        defi = ET.SubElement(entry, "definition")
        if len(paragraphs) == 1:
            append_mixed_content(defi, paragraphs[0])
        else:
            for i, para in enumerate(paragraphs):
                line_el = ET.SubElement(defi, "line")
                append_mixed_content(line_el, para)
                if i < len(paragraphs) - 1:
                    spacer = ET.SubElement(defi, "line")
                    spacer.text = "\u00a0"
    return root


# ── 5. Indent + write ─────────────────────────────────────────────────────────

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
        print(f"Usage: {sys.argv[0]} input.docx [output.xml]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = (
        sys.argv[2] if len(sys.argv) >= 3
        else str(Path(input_file).with_suffix(".xml"))
    )

    text = read_docx(input_file)
    text = normalize(text)
    entries = parse_entries(text)
    root = build_xml(entries)
    indent(root)

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Created {output_file} with {len(entries)} entries.")


if __name__ == "__main__":
    main()