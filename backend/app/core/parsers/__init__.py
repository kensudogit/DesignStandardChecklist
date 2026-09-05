"""拡張子でパーサを振り分ける (SKILL.md 2. 入力形式)。"""

from __future__ import annotations

from pathlib import Path

from app.core.parsers import docx_parser, pdf_parser, text_parser, xlsx_parser
from app.core.parsers.base import Block, ParsedDocument, ParseError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".markdown", ".txt", ".csv"}


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return pdf_parser.parse(data)
    if ext == ".docx":
        return docx_parser.parse(data)
    if ext in (".xlsx", ".xlsm"):
        return xlsx_parser.parse(data)
    if ext in (".md", ".markdown", ".txt", ".csv"):
        return text_parser.parse(data)
    if ext == ".doc":
        raise ParseError(".doc は未対応です。.docx に変換してください。")
    if ext == ".xls":
        raise ParseError(".xls は未対応です。.xlsx に変換してください。")
    raise ParseError(f"未対応の拡張子です: {ext or '(拡張子なし)'}")


__all__ = ["Block", "ParsedDocument", "ParseError", "SUPPORTED_EXTENSIONS", "parse_document"]
