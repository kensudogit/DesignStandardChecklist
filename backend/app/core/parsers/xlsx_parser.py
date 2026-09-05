"""Excel。1行=1ブロック。所在はシート名と行番号で表す (ページ番号は無い)。"""

from __future__ import annotations

import io

from app.core.parsers.base import Block, ParsedDocument, ParseError


def parse(data: bytes) -> ParsedDocument:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise ParseError("openpyxl が未インストールです: pip install openpyxl") from exc

    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise ParseError(f"Excelを読み込めません: {exc}") from exc

    blocks: list[Block] = []
    for ws in wb.worksheets:
        blocks.append(Block(text=str(ws.title), heading_level=1, locator=str(ws.title)))
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
            if not cells:
                continue
            blocks.append(
                Block(
                    text=" / ".join(cells),
                    is_table=True,
                    locator=f"{ws.title}!{row_idx}行",
                )
            )
    wb.close()
    if not blocks:
        raise ParseError("Excelからテキストを抽出できませんでした。")
    return ParsedDocument(blocks=blocks, meta={"format": "xlsx"})
