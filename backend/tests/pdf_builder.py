"""テスト用の最小PDFビルダ。

外部依存を増やさずに「本物のページ番号を持つPDF」を作るために使う。
本文は WinAnsi の範囲 (ASCII) のみ。日本語の抽出精度は他形式のテストで担保する。
"""

from __future__ import annotations


def build_pdf(pages: list[list[str]]) -> bytes:
    """pages[i] は i+1 ページ目に置く行のリスト。"""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # 1-origin のオブジェクト番号

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    content_ids: list[int] = []
    pages_id = len(objects) + 2 * len(pages) + 1  # Pages は最後に確保する

    for lines in pages:
        text = b"BT /F1 12 Tf 50 750 Td 14 TL\n"
        for line in lines:
            escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            text += b"(" + escaped.encode("ascii") + b") Tj T*\n"
        text += b"ET"
        stream = b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream"
        content_ids.append(add(stream))

        page = (
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 " + str(font_id).encode() + b" 0 R >> >> "
            b"/Contents " + str(content_ids[-1]).encode() + b" 0 R >>"
        )
        page_ids.append(add(page))

    kids = b" ".join(f"{pid} 0 R".encode() for pid in page_ids)
    actual_pages_id = add(
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode() + b" >>"
    )
    assert actual_pages_id == pages_id, "Pages オブジェクト番号の予約がずれている"
    catalog_id = add(b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode()
        + b" /Root " + str(catalog_id).encode() + b" 0 R >>\n"
        b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)
