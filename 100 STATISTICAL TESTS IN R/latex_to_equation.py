#!/usr/bin/env python3
"""
Tìm các đoạn LaTeX thô dạng \\[ ... \\] trong file .docx, dùng pandoc để
chuyển sang công thức Word gốc (OMML - Office Math Markup Language), rồi
chèn thẳng vào document.xml thay cho đoạn text LaTeX cũ.

Kết quả: công thức trở thành Equation thật của Word -> mở trong Word là
sửa được bằng Equation Editor, không còn là text "\\[ ... \\]" nữa.

Cách dùng:
    python3 latex_to_equation.py input.docx output.docx

Yêu cầu: pandoc, lxml  (pip install lxml --break-system-packages)
"""
import sys
import re
import subprocess
import zipfile
import shutil
import os
import tempfile
from copy import deepcopy
from lxml import etree

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS = {'w': W_NS, 'm': M_NS}

# Regex bắt công thức LaTeX theo 4 quy ước phổ biến nhất:
#   - Công thức khối (display math):  \[ ... \]   (backslash rồi ngoặc vuông)
#   - Công thức chèn dòng (inline math): \( ... \)  (backslash rồi ngoặc tròn)
#   - Công thức khối kiểu Markdown:  $$ ... $$
#   - Công thức chèn dòng kiểu Markdown: $ ... $
#
# Với 2 nhánh dùng dấu $, cần đề phòng nhận NHẦM ký hiệu tiền tệ (vd "$5,000")
# thành công thức toán. Áp dụng đúng quy ước mà pandoc/Markdown dùng: ký tự
# NGAY SAU dấu $ mở và NGAY TRƯỚC dấu $ đóng không được là khoảng trắng — quy
# ước này loại được hầu hết trường hợp tiền tệ trong văn xuôi (vì sau số tiền
# thường có khoảng trắng hoặc dấu câu trước dấu $ tiếp theo). Trường hợp hiếm
# còn sót (vd "$5,000-$10,000" viết liền không cách) sẽ được pandoc từ chối
# và báo lỗi như bình thường — KHÔNG làm mất dữ liệu, chỉ là không convert.
#
# Nhánh $$...$$ đặt TRƯỚC nhánh $...$ trong alternation để regex ưu tiên khớp
# cặp $$ trước, tránh nhánh $ đơn "ăn nhầm" 1 nửa của cặp $$.
LATEX_PATTERN = re.compile(
    r'\\\[(.*?)\\\]'                # 1: \[ ... \]
    r'|\\\((.*?)\\\)'               # 2: \( ... \)
    r'|\$\$(.*?)\$\$'                # 3: $$ ... $$
    r'|\$(?!\s)(.+?)(?<!\s)\$',      # 4: $ ... $  (không được có khoảng trắng sát 2 đầu)
    re.DOTALL
)


def extract_latex(m):
    """Lấy nội dung LaTeX từ 1 match, bất kể khớp bởi nhánh nào trong 4 nhánh trên."""
    latex = next(g for g in m.groups() if g is not None)
    return clean_latex(latex)


def clean_latex(latex: str) -> str:
    """Dọn các lỗi cú pháp phổ biến do hệ dịch/OCR sinh ra trước khi đưa cho pandoc.

    Lỗi phổ biến nhất (chiếm đa số các ca thất bại quan sát được): dư 1 dấu
    backslash ngay TRƯỚC dấu đóng công thức, kiểu '...\\varepsilon_i\\'
    (đáng lẽ chỉ là '...\\varepsilon_i'). Đây là artefact do pipeline dịch/OCR
    thượng nguồn sinh ra, không phải do người dùng gõ tay — có thể tự động
    cắt bỏ an toàn vì một dấu backslash trơ trọi ở cuối công thức không bao
    giờ là cú pháp LaTeX hợp lệ.
    """
    latex = latex.strip()
    while latex.endswith('\\'):
        latex = latex[:-1].rstrip()
    # Lỗi phổ biến thứ hai: '\left{' / '\right}' thiếu backslash trước dấu
    # ngoặc nhọn (đúng ra phải là '\left\{' / '\right\}'). Tự sửa an toàn vì
    # '\left{' không phải cú pháp LaTeX hợp lệ trong bất kỳ trường hợp nào.
    latex = latex.replace('\\left{', '\\left\\{').replace('\\right}', '\\right\\}')
    return latex


def latex_to_omath_node(latex: str):
    """Dùng pandoc để chuyển 1 chuỗi LaTeX thành node OMML (m:oMathPara hoặc m:oMath)."""
    latex = latex.strip()
    with tempfile.TemporaryDirectory() as tmp:
        md_path = os.path.join(tmp, 'eq.md')
        docx_path = os.path.join(tmp, 'eq.docx')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f'$${latex}$$\n')
        subprocess.run(
            ['pandoc', md_path, '-o', docx_path],
            check=True, capture_output=True
        )
        with zipfile.ZipFile(docx_path) as z:
            xml_bytes = z.read('word/document.xml')
    root = etree.fromstring(xml_bytes)
    # Luôn lấy m:oMath (không lấy m:oMathPara) vì công thức sẽ được chèn
    # xen giữa các w:r văn bản trong cùng một đoạn (w:p) — oMathPara chỉ
    # hợp lệ khi nó là nội dung DUY NHẤT của cả đoạn, nếu không Word/LibreOffice
    # sẽ không render.
    node = root.find('.//m:oMath', NS)
    if node is None:
        raise ValueError(f'Pandoc khong tao duoc cong thuc cho: {latex!r}')
    node = deepcopy(node)
    fix_element_order(node)
    return node


# Thu tu chuan (theo XSD OOXML Math) cho cac the <m:xPr> hay bi pandoc
# sinh sai thu tu (Word thuong van mo duoc nhung XSD strict se bao loi).
_PR_CHILD_ORDER = {
    f'{{{M_NS}}}dPr': [
        'begChr', 'sepChr', 'endChr', 'grow', 'shp', 'ctrlPr',
    ],
    f'{{{M_NS}}}naryPr': [
        'chr', 'limLoc', 'grow', 'subHide', 'supHide', 'ctrlPr',
    ],
}


def fix_element_order(root_node):
    """Duyet toan bo cay va sap xep lai con cua cac the <m:*Pr> theo dung
    thu tu XSD, tranh loi 'Element ... is not expected' khi Word/validator
    kiem tra schema."""
    for tag, order in _PR_CHILD_ORDER.items():
        for pr_el in root_node.iter(tag):
            order_map = {f'{{{M_NS}}}{name}': i for i, name in enumerate(order)}
            children = list(pr_el)
            children.sort(key=lambda c: order_map.get(c.tag, len(order)))
            for c in children:
                pr_el.remove(c)
            for c in children:
                pr_el.append(c)


def make_run(text: str, rpr_template):
    """Tạo 1 phần tử w:r mới, giữ định dạng (rPr) từ run gốc nếu có."""
    r = etree.Element(f'{{{W_NS}}}r')
    if rpr_template is not None:
        r.append(deepcopy(rpr_template))
    t = etree.SubElement(r, f'{{{W_NS}}}t')
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return r


def process_paragraph(p, stats, failures, p_index):
    runs = p.findall('w:r', NS)
    if not runs:
        return

    run_info = []  # (run_elem, start, end, text, rpr)
    offset = 0
    for r in runs:
        t_elems = r.findall('w:t', NS)
        run_text = ''.join(t.text or '' for t in t_elems)
        rpr = r.find('w:rPr', NS)
        run_info.append((r, offset, offset + len(run_text), run_text, rpr))
        offset += len(run_text)
    full_text = ''.join(ri[3] for ri in run_info)

    matches = list(LATEX_PATTERN.finditer(full_text))
    if not matches:
        return

    def emit_text_range(start, end):
        """Trả về list các w:r mới cho khoảng text [start, end), giữ định dạng gốc."""
        out = []
        if start >= end:
            return out
        for (r, s, e, txt, rpr) in run_info:
            seg_start = max(start, s)
            seg_end = min(end, e)
            if seg_start < seg_end:
                sub = txt[seg_start - s: seg_end - s]
                if sub:
                    out.append(make_run(sub, rpr))
        return out

    new_elements = []
    cursor = 0
    for m in matches:
        new_elements.extend(emit_text_range(cursor, m.start()))
        latex_code = extract_latex(m)
        try:
            eq_node = latex_to_omath_node(latex_code)
            new_elements.append(eq_node)
            stats['converted'] += 1
        except Exception as ex:
            stats['failed'] += 1
            print(f'  [CANH BAO] Khong chuyen duoc cong thuc: {latex_code!r} ({ex})',
                  file=sys.stderr)
            context = full_text.strip()
            if len(context) > 160:
                s = max(0, m.start() - 60)
                e = min(len(full_text), m.end() + 40)
                context = '...' + full_text[s:e].strip() + '...'
            # Lưu p_index (vị trí đoạn văn theo thứ tự duyệt) để sau này tự
            # chèn mã đánh dấu ASCII vào đúng đoạn này trên 1 bản sao tạm,
            # dùng để tra số trang — KHÔNG ảnh hưởng file kết quả thật.
            failures.append({'latex': latex_code, 'context': context, 'p_index': p_index})
            # giữ nguyên text gốc nếu lỗi, để không mất dữ liệu
            new_elements.extend(emit_text_range(m.start(), m.end()))
        cursor = m.end()
    new_elements.extend(emit_text_range(cursor, len(full_text)))

    # Xoá các w:r cũ, chèn các phần tử mới vào đúng vị trí trong w:p
    first_run = runs[0]
    idx = list(p).index(first_run)
    for r in runs:
        p.remove(r)
    for i, el in enumerate(new_elements):
        p.insert(idx + i, el)


def ensure_math_namespace(root):
    """Đảm bảo document.xml có khai báo xmlns:m (cần cho công thức)."""
    nsmap = root.nsmap
    if 'm' in nsmap and nsmap['m'] == M_NS:
        return root
    # Nếu thiếu, ta cần build lại root với nsmap mới (lxml không cho thêm ns runtime)
    new_nsmap = dict(nsmap)
    new_nsmap['m'] = M_NS
    new_root = etree.Element(root.tag, nsmap=new_nsmap)
    new_root.attrib.update(root.attrib)
    for child in root:
        new_root.append(child)
    return new_root


def write_failure_report(failures: list, report_path: str):
    """Ghi ra danh sách công thức lỗi kèm câu văn xung quanh, để tìm bằng
    Ctrl+F trong Word — không cần LibreOffice/PDF, không cần tính số trang."""
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f'# Danh sach {len(failures)} cong thuc chua chuyen duoc\n\n')
        f.write('# Dung Ctrl+F trong Word, dan doan "Cau van" vao o tim kiem\n')
        f.write('# de nhay thang toi vi tri can sua.\n\n')
        for i, fail in enumerate(failures, 1):
            f.write(f'--- Loi #{i} ---\n')
            f.write(f'LaTeX: {fail["latex"]!r}\n')
            f.write(f'Cau van: {fail["context"]}\n\n')


def convert(input_path: str, output_path: str):
    work_dir = tempfile.mkdtemp()
    try:
        extract_dir = os.path.join(work_dir, 'unpacked')
        with zipfile.ZipFile(input_path) as z:
            z.extractall(extract_dir)

        doc_xml_path = os.path.join(extract_dir, 'word', 'document.xml')
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(doc_xml_path, parser)
        root = tree.getroot()
        root = ensure_math_namespace(root)

        stats = {'converted': 0, 'failed': 0}
        failures = []
        body = root.find('w:body', NS)
        for p_index, p in enumerate(body.findall('.//w:p', NS)):
            process_paragraph(p, stats, failures, p_index)

        tree = etree.ElementTree(root)
        tree.write(doc_xml_path, xml_declaration=True, encoding='UTF-8', standalone=True)

        # Đóng gói lại thành .docx (zip)
        if os.path.exists(output_path):
            os.remove(output_path)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for foldername, _, filenames in os.walk(extract_dir):
                for filename in filenames:
                    filepath = os.path.join(foldername, filename)
                    arcname = os.path.relpath(filepath, extract_dir)
                    zf.write(filepath, arcname)

        print(f'Xong. Da chuyen {stats["converted"]} cong thuc thanh cong, '
              f'{stats["failed"]} loi.')

        if failures:
            report_path = os.path.splitext(output_path)[0] + '_loi_kem_cau_van.txt'
            write_failure_report(failures, report_path)
            print(f'Da ghi bao cao vi tri loi: {report_path}', file=sys.stderr)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Cach dung: python3 latex_to_equation.py input.docx output.docx')
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
