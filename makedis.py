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
    """Đọc docx, GIỮ NGUYÊN từng paragraph riêng biệt bằng \\n.
    Mỗi dòng là chuỗi đã có tag <b>/<i>/<bi>."""
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
    pattern = re.compile(
        r"#(.*?)#\s*<def>(.*?)</def>",
        re.DOTALL | re.IGNORECASE
    )
    entries = []
    for match in pattern.finditer(text):
        headword = match.group(1).strip()
        raw_def = match.group(2).strip()
        paragraphs = [
            line.strip()
            for line in raw_def.split("\n")
            if line.strip()
        ]
        entries.append((headword, paragraphs))
    return entries


# ── 4. Build XML, parse tag nội tuyến thành sub-element ──────────────────────

# Regex nhận dạng tag nội tuyến do chúng ta tạo ra
INLINE_RE = re.compile(r"<(b|i|bi)>(.*?)</\1>", re.DOTALL)


def append_inline(parent_el, raw_text):
    """
    Phân tích raw_text chứa <b>/<i>/<bi> rồi thêm vào parent_el
    dưới dạng text + sub-element xen kẽ (mixed content).
    """
    pos = 0
    for m in INLINE_RE.finditer(raw_text):
        # Phần text thuần trước tag
        before = raw_text[pos:m.start()]
        if before:
            # Nối vào tail của element trước, hoặc text của parent
            if len(parent_el):
                last = parent_el[-1]
                last.tail = (last.tail or "") + before
            else:
                parent_el.text = (parent_el.text or "") + before

        tag_name = m.group(1)   # "b", "i", hoặc "bi"
        content  = m.group(2)
        child = ET.SubElement(parent_el, tag_name)
        child.text = content
        pos = m.end()

    # Phần text thuần còn lại sau tag cuối
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
            append_inline(defi, paragraphs[0])
        else:
            for i, para in enumerate(paragraphs):
                line_el = ET.SubElement(defi, "line")
                append_inline(line_el, para)
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

    input_file  = sys.argv[1]
    output_file = (
        sys.argv[2] if len(sys.argv) >= 3
        else str(Path(input_file).with_suffix(".xml"))
    )

    text    = read_docx(input_file)
    text    = normalize(text)
    entries = parse_entries(text)
    root    = build_xml(entries)
    indent(root)

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Created {output_file} with {len(entries)} entries.")


if __name__ == "__main__":
    main()