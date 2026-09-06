"""PDF。pypdf が返す 1-origin のページ番号のみを page に入れる。"""

from __future__ import annotations

import io

from app.core.parsers.base import Block, ParsedDocument, ParseError


def parse(data: bytes) -> ParsedDocument:
    """PDF から1行ずつ Block を作る。

    ページ番号を持てる唯一の形式。pypdf が返す 1-origin の番号をそのまま使い、
    ここで採番し直すことはしない。

    1文字も取れなかった場合は空の結果を返さずエラーにする。スキャンPDFを
    黙って「規定0件」として通すと、解析できたのか中身が無いのか区別できない。
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ParseError("pypdf が未インストールです: pip install pypdf") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ParseError(f"PDFを読み込めません: {exc}") from exc

    blocks: list[Block] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        # 特定ページだけ壊れていることがある。そのページを空として残りを続ける
        except Exception:
            text = ""
        for raw in text.splitlines():
            line = raw.strip()
            if line:
                blocks.append(Block(text=line, page=page_no))
    if not blocks:
        raise ParseError(
            "PDFからテキストを抽出できませんでした。画像PDFの可能性があります (OCR済みPDFを使用してください)。"
        )
    return ParsedDocument(blocks=blocks, meta={"format": "pdf", "pages": str(len(reader.pages))})
