"""
split.py — Tách file PDF thành nhiều phần theo kiểu "gối đầu" (overlap)
=========================================================================

MỤC ĐÍCH
--------
Tách 1 file PDF lớn thành nhiều file PDF nhỏ hơn, mỗi phần có một đoạn
trang trùng với phần trước đó (gối đầu / overlap). Cách chia này hữu ích
khi đưa PDF cho AI đọc theo từng phần: nhờ có phần trùng lặp ở đầu, AI ở
lượt đọc file sau vẫn "thấy lại" vài trang cuối của file trước, giúp nối
mạch ngữ cảnh dù AI không nhớ được giữa các lần gọi riêng biệt.

CÔNG THỨC CHIA (i = số trang mỗi phần, overlap = số trang gối đầu)
-------------------------------------------------------------------
    Phần 1 : trang 1                       -> i
    Phần 2 : trang (i      - overlap)      -> 2*i
    Phần 3 : trang (2*i    - overlap)      -> 3*i
    ...
    Phần n : trang ((n-1)*i - overlap)     -> n*i
Nếu tổng số trang không chia hết cho i, phần cuối cùng chỉ lấy phần dư
(kết thúc đúng bằng trang cuối của PDF gốc).

CÀI ĐẶT (chỉ cần 1 thư viện ngoài)
-----------------------------------
    pip install pymupdf

(Thư viện "pymupdf" khi import vào Python có tên là "fitz", nên trong
code bạn thấy dòng `import fitz` — đó chính là pymupdf, không phải thư
viện nào khác. Python 3.7+ là đủ, không cần cài thêm gì khác.)

CÁCH DÙNG
---------
    python split.py <input.pdf> <i> [overlap] [-o thư_mục_ra] [--dry-run] [--no-note]

Tham số:
    input.pdf     Đường dẫn file PDF cần tách (bắt buộc)
    i             Số trang mỗi phần (bắt buộc, số nguyên dương)
    overlap       Số trang gối đầu giữa 2 phần liên tiếp (tùy chọn, mặc định = 5)
    -o, --outdir  Thư mục lưu các file kết quả (tùy chọn, mặc định = thư mục hiện tại)
    --dry-run     Chỉ in ra cách chia dự kiến, KHÔNG tạo file PDF nào
    --no-note     Không chèn trang ghi chú ngữ cảnh vào đầu mỗi phần (mặc định là CÓ chèn)

Ví dụ:
    # Xem trước cách chia (không tạo file) cho PDF 100 trang, mỗi phần 20 trang, gối đầu 5 trang
    python split.py bao_cao.pdf 20 5 --dry-run

    # Tách thật, lưu kết quả vào thư mục "parts"
    python split.py bao_cao.pdf 20 5 -o parts

    # Tách thật nhưng dùng overlap mặc định (5) và không chèn trang ghi chú
    python split.py bao_cao.pdf 20 --no-note

KẾT QUẢ
-------
Mỗi phần được lưu thành 1 file PDF riêng, đặt tên theo mẫu:
    <tên_file_gốc>_<trang_bắt_đầu>_<trang_kết_thúc>.pdf
Ví dụ: bao_cao_15_23.pdf nghĩa là phần này chứa trang 15 đến 23 của file gốc.

Nếu không dùng --no-note, mỗi phần (trừ phần 1) sẽ có thêm 1 trang đầu
ghi rõ: file gốc, phần thứ mấy/tổng số phần, trang gốc tương ứng, và
những trang nào bị trùng với phần trước — để AI (hoặc người đọc) nhận
biết ngay đây là phần nối tiếp.
"""

import fitz
import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Tách PDF thành nhiều phần theo kiểu gối đầu (overlap)."
    )
    parser.add_argument("pdf_file", help="Đường dẫn file PDF đầu vào")
    parser.add_argument("i", type=int, help="Số trang mỗi phần (chunk size)")
    parser.add_argument(
        "overlap",
        type=int,
        nargs="?",
        default=5,
        help="Số trang gối đầu giữa 2 phần liên tiếp (mặc định: 5)",
    )
    parser.add_argument(
        "-o", "--outdir", default=".", help="Thư mục lưu các file đầu ra (mặc định: thư mục hiện tại)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ in ra cách chia (số phần, trang bắt đầu/kết thúc), không tạo file PDF nào",
    )
    parser.add_argument(
        "--no-note",
        action="store_true",
        help="Không chèn trang ghi chú ngữ cảnh vào đầu mỗi phần (mặc định là có chèn)",
    )
    args = parser.parse_args()

    if args.i <= 0:
        print("i (số trang mỗi phần) phải là số nguyên dương.")
        sys.exit(1)
    if args.overlap < 0:
        print("overlap phải >= 0.")
        sys.exit(1)
    if args.overlap >= args.i:
        print(
            f"Cảnh báo: overlap ({args.overlap}) >= i ({args.i}). "
            "Các phần có thể trùng lặp rất nhiều hoặc không tiến triển đúng như mong đợi."
        )

    try:
        src = fitz.open(args.pdf_file)
    except Exception as e:
        print(f"Không mở được PDF: {e}")
        sys.exit(1)

    total_pages = src.page_count
    if total_pages == 0:
        print("PDF không có trang nào.")
        src.close()
        sys.exit(1)

    pdf_path = Path(args.pdf_file)
    outdir = Path(args.outdir)

    # Tính trước danh sách các phần (start_page, end_page)
    parts = []
    n = 1
    while True:
        if n == 1:
            start_page = 1
        else:
            start_page = max(1, (n - 1) * args.i - args.overlap)

        end_page = min(n * args.i, total_pages)

        if start_page > total_pages:
            break

        parts.append((start_page, end_page))

        if end_page >= total_pages:
            break
        n += 1

    total_parts = len(parts)

    if args.dry_run:
        print(f"[DRY RUN] Tổng số trang PDF: {total_pages}")
        print(f"[DRY RUN] Dự kiến chia thành {total_parts} phần (i={args.i}, overlap={args.overlap}):")
        for idx, (start_page, end_page) in enumerate(parts, start=1):
            output_file = outdir / f"{pdf_path.stem}_{start_page}_{end_page}.pdf"
            print(f"[DRY RUN] Phần {idx}/{total_parts}: trang {start_page} -> {end_page}  =>  {output_file}")
        print("[DRY RUN] Chưa tạo file nào. Bỏ --dry-run để tách file thật.")
        src.close()
        return

    outdir.mkdir(parents=True, exist_ok=True)
    results = []

    for idx, (start_page, end_page) in enumerate(parts, start=1):
        out = fitz.open()
        try:
            # Chèn trang ghi chú ngữ cảnh ở đầu (trừ khi --no-note hoặc là phần đầu tiên)
            if not args.no_note:
                note_page = out.new_page(width=595, height=842)  # khổ A4
                note_lines = [
                    f"File goc: {pdf_path.name}",
                    f"Phan {idx}/{total_parts} - Trang goc: {start_page} - {end_page}",
                ]
                if idx > 1:
                    prev_end = parts[idx - 2][1]
                    overlap_end = min(start_page + args.overlap - 1, prev_end)
                    note_lines.append(
                        f"Luu y: cac trang {start_page}-{overlap_end} trung voi phan truoc, "
                        f"dung de noi mach ngu canh."
                    )
                text = "\n".join(note_lines)
                note_page.insert_text((50, 60), text, fontsize=12)

            out.insert_pdf(src, from_page=start_page - 1, to_page=end_page - 1)
            output_file = outdir / f"{pdf_path.stem}_{start_page}_{end_page}.pdf"
            out.save(str(output_file))
            out.close()
            results.append((start_page, end_page, output_file))
            print(f"Phần {idx}/{total_parts}: trang {start_page} -> {end_page}  =>  {output_file}")
        except Exception as e:
            out.close()
            print(f"Lỗi khi tách phần {idx}: {e}")
            src.close()
            sys.exit(1)

    src.close()

    print()
    print(f"Tổng số trang PDF: {total_pages}")
    print(f"Đã tách thành {len(results)} phần (mỗi phần tối đa {args.i} trang, gối đầu {args.overlap} trang).")


if __name__ == "__main__":
    main()