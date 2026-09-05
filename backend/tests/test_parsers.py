"""各入力形式のパーサ。ページ番号を取得できる形式とできない形式を切り分ける。"""

from __future__ import annotations

import io

import pytest

from app.core.extractor import extract_rules
from app.core.parsers import ParseError, parse_document
from app.core.structure import assign_structure

RULES = [
    "画面項目には項目IDを付与すること。",
    "パスワードをログへ出力してはならない。",
]


def _rules_of(filename: str, data: bytes):
    parsed = parse_document(filename, data)
    return parsed, extract_rules(assign_structure(parsed.blocks))


def test_markdown_parses_headings_and_rules() -> None:
    text = "# 画面設計標準\n\n## 3.2 項目定義\n\n" + "\n".join(RULES) + "\n"
    parsed, rules = _rules_of("標準.md", text.encode("utf-8"))
    assert parsed.meta["format"] == "text"
    assert len(rules) == 2
    assert rules[0].section == "3.2"


def test_shift_jis_text_is_decoded() -> None:
    text = "3.2 項目定義\n画面項目には項目IDを付与すること。\n"
    _, rules = _rules_of("標準.txt", text.encode("cp932"))
    assert len(rules) == 1
    assert "項目ID" in rules[0].original_rule


def test_docx_parses_headings_tables_and_has_no_page_numbers() -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("画面設計標準", level=1)
    document.add_heading("3.2 項目定義", level=2)
    for rule in RULES:
        document.add_paragraph(rule)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "必須区分"
    table.rows[0].cells[1].text = "必須項目には必須マークを表示すること。"

    buf = io.BytesIO()
    document.save(buf)
    parsed, rules = _rules_of("標準.docx", buf.getvalue())

    assert parsed.meta["format"] == "docx"
    # Word からはページ番号を取得できないので推測しない
    assert all(block.page is None for block in parsed.blocks)
    texts = [r.original_rule for r in rules]
    assert any("項目ID" in t for t in texts)
    assert any("パスワード" in t for t in texts)
    assert any("必須マーク" in t for t in texts)  # 表の中の規定も拾う
    assert next(r for r in rules if "項目ID" in r.original_rule).section == "3.2"


def test_xlsx_rows_keep_sheet_and_row_locator() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "画面設計標準"
    ws.append(["No", "規定"])
    for index, rule in enumerate(RULES, start=1):
        ws.append([index, rule])

    buf = io.BytesIO()
    wb.save(buf)
    parsed, rules = _rules_of("標準.xlsx", buf.getvalue())

    assert parsed.meta["format"] == "xlsx"
    assert len(rules) == 2
    # ページ番号の代わりにシート名と行番号を所在として残す
    assert rules[0].page is None
    assert rules[0].locator is not None
    assert "画面設計標準!" in rules[0].locator


def test_pdf_pages_are_real_page_numbers() -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    # テキストを抽出できない PDF は「画像PDFの可能性」を明示して失敗させる
    with pytest.raises(ParseError, match="画像PDF"):
        parse_document("標準.pdf", buf.getvalue())


def test_legacy_formats_are_rejected_with_guidance() -> None:
    with pytest.raises(ParseError, match=r"\.docx に変換"):
        parse_document("標準.doc", b"dummy")
    with pytest.raises(ParseError, match=r"\.xlsx に変換"):
        parse_document("標準.xls", b"dummy")
    with pytest.raises(ParseError, match="未対応の拡張子"):
        parse_document("標準.pptx", b"dummy")


def test_pdf_blocks_carry_real_page_numbers() -> None:
    """PDF では pypdf が返す実ページ番号のみを使う (推測しない)。"""
    pytest.importorskip("pypdf")
    from tests.pdf_builder import build_pdf

    data = build_pdf(
        [
            ["3.1 Screen Basics", "The screen ID must be defined."],
            ["3.2 Item Definition", "Every item must have an item ID."],
        ]
    )
    parsed = parse_document("standard.pdf", data)

    assert parsed.meta["format"] == "pdf"
    assert parsed.meta["pages"] == "2"
    pages = {block.page for block in parsed.blocks}
    assert pages == {1, 2}

    first_page_text = " ".join(b.text for b in parsed.blocks if b.page == 1)
    second_page_text = " ".join(b.text for b in parsed.blocks if b.page == 2)
    assert "screen ID" in first_page_text
    assert "item ID" in second_page_text
    assert "item ID" not in first_page_text


def test_pdf_sections_and_pages_reach_the_rule() -> None:
    """章・節とページが規定まで引き継がれる (STEP 2/12)。"""
    pytest.importorskip("pypdf")
    from tests.pdf_builder import build_pdf

    data = build_pdf(
        [
            ["1 Scope", "This standard applies to screen design."],
            ["3.2 Item Definition", "Item IDs are recorded. This must be defined."],
        ]
    )
    parsed = parse_document("standard.pdf", data)
    located = assign_structure(parsed.blocks)
    body = [item for item in located if not item.is_heading and "must be defined" in item.text]
    assert body, "本文ブロックが見つからない"
    assert body[0].page == 2
    assert body[0].section == "3.2"
