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

ENTRY_PATTERN = re.compile(
    r"#(?P<headword>[^#\n]+)#\s*\\?<def>?(.*?)\\?</def>?",
    re.DOTALL | re.IGNORECASE
)

# Regex phân tích các thành phần bên trong định nghĩa
TOKEN_RE = re.compile(
    r"(?P<bold>\*\*(?P<b_text>.*?)\*\*)"
    r"|(?P<italic>\*(?P<i_text>.*?)\*)"
    r"|(?P<eq_block>`\$\$(?P<eq_b_code>.*?)\$\$`)"
    r"|(?P<eq_inline>`\$(?P<eq_i_code>.*?)\$`)"
    r"|(?P<image><image>(?P<img_content>.*?)</image>)",
    re.DOTALL
)

SEPARATOR = r'`$$\star\qquad\star\qquad\star$$`'


def append_mixed_markdown(parent_el, raw_text):
    """Phân tích markdown bold, italic, công thức và ảnh vào cây XML."""
    pos = 0
    for m in TOKEN_RE.finditer(raw_text):
        before = raw_text[pos:m.start()]
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

    tail = raw_text[pos:]
    if tail:
        if len(parent_el):
            parent_el[-1].tail = (parent_el[-1].tail or "") + tail
        else:
            parent_el.text = (parent_el.text or "") + tail


def build_lexonomy_xml(md_content):
    root = ET.Element("dictionary")
    
    for match in ENTRY_PATTERN.finditer(md_content):
        headword = match.group("headword").strip()
        raw_def = match.group(2).strip()

        entry_el = ET.SubElement(root, "entry")
        hw_el = ET.SubElement(entry_el, "headword")
        hw_el.text = headword

        # Nếu có phân cách Anh - Việt
        if "`$$\\star\\qquad\\star\\qquad\\star$$`" in raw_def:
            parts = re.split(re.escape(SEPARATOR), raw_def)
            en_part = parts[0].strip() if len(parts) > 0 else ""
            vi_part = parts[1].strip() if len(parts) > 1 else ""

            def_en = ET.SubElement(entry_el, "definition_en")
            for line in [l.strip() for l in en_part.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_en, "line")
                append_mixed_markdown(line_el, line)

            def_vi = ET.SubElement(entry_el, "definition_vi")
            for line in [l.strip() for l in vi_part.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_vi, "line")
                append_mixed_markdown(line_el, line)
        else:
            # Entry đơn
            def_el = ET.SubElement(entry_el, "definition")
            for line in [l.strip() for l in raw_def.split("\n") if l.strip()]:
                line_el = ET.SubElement(def_el, "line")
                append_mixed_markdown(line_el, line)

    return root


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

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✓ Đã tạo thành công {output_file} từ {input_file} để nạp vào Lexonomy!")


if __name__ == "__main__":
    main()