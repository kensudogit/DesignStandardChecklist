"""PDF。pypdf が返す 1-origin のページ番号のみを page に入れる。"""

from __future__ import annotations

import io

from app.core.parsers.base import Block, ParsedDocument, ParseError


def parse(data: bytes) -> ParsedDocument:
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
