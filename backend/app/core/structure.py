"""STEP 2: 文書構造解析。

ブロック列を走査して各ブロックに「章 / 節」を割り当てる。
章番号・節番号は本文中に実在する表記からのみ採る (禁止事項: ページ番号の推測)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.parsers.base import Block

# 「第3章 画面設計」「3章」
CHAPTER_JP = re.compile(r"^第?\s*(\d+)\s*章[\s　.:：]*(.*)$")
# 「3.2 項目定義」「3.2.1 …」 — 数字ドット始まりの見出し
NUMBERED = re.compile(r"^(\d+(?:\.\d+)+)[\s　.:：]+(\S.*)$")
# 「3 画面設計」 (単独数字 + 空白 + 見出し語)
TOP_NUMBERED = re.compile(r"^(\d+)[\s　.:：]+(\S.{0,40})$")
# 「(1) …」「1) …」のような箇条書きは見出しではない
BULLET = re.compile(r"^[（(]?\d+[)）]")


@dataclass
class Located:
    """所在情報を付与した1ブロック。"""

    text: str
    page: int | None
    chapter: str | None
    section: str | None
    heading_path: str
    is_table: bool
    locator: str | None
    order: int
    #: 見出し行そのものか (規定候補から除外する)
    is_heading: bool = False
    # --- 表形式の標準書が列として持っていた情報 (推測ではなく記載そのもの) ---
    category_hint: str | None = None
    rule_type_hint: str | None = None
    severity_hint: str | None = None
    note_hint: str | None = None


def _is_headingish(block: Block) -> bool:
    if block.heading_level is not None:
        return True
    if block.is_table:
        return False
    # 短くて句点で終わらない行は見出しとみなす余地がある
    return len(block.text) <= 60 and not block.text.rstrip().endswith("。")


def assign_structure(blocks: list[Block]) -> list[Located]:
    chapter: str | None = None
    chapter_title: str | None = None
    section: str | None = None
    section_title: str | None = None
    out: list[Located] = []

    for order, block in enumerate(blocks):
        text = block.text.strip()
        if not text:
            continue

        matched_heading = False
        if _is_headingish(block) and not BULLET.match(text):
            m = CHAPTER_JP.match(text)
            if m:
                chapter, chapter_title = m.group(1), (m.group(2).strip() or None)
                section, section_title = None, None
                matched_heading = True
            else:
                m = NUMBERED.match(text)
                if m:
                    section, section_title = m.group(1), m.group(2).strip()
                    chapter = section.split(".")[0]
                    matched_heading = True
                else:
                    m = TOP_NUMBERED.match(text)
                    if m:
                        chapter, chapter_title = m.group(1), m.group(2).strip()
                        section, section_title = None, None
                        matched_heading = True
                    elif block.heading_level is not None:
                        # 番号なし見出し (Word の Heading スタイル等)
                        if block.heading_level <= 1:
                            chapter, chapter_title = None, text
                            section, section_title = None, None
                        else:
                            section, section_title = None, text
                        matched_heading = True

        # 表の行が自前で章・節を持っている場合は、見出しの追跡結果より優先する
        row_chapter = block.chapter or chapter
        row_section = block.section or section
        row_section_title = section_title if block.section is None else None

        parts = [
            p
            for p in (
                chapter_title or (f"第{row_chapter}章" if row_chapter else None),
                block.category_hint or row_section_title,
            )
            if p
        ]
        heading_path = " > ".join(parts)

        out.append(
            Located(
                text=text,
                page=block.page,
                chapter=row_chapter,
                section=row_section,
                heading_path=heading_path,
                is_table=block.is_table,
                locator=block.locator,
                order=order,
                is_heading=matched_heading,
                category_hint=block.category_hint,
                rule_type_hint=block.rule_type_hint,
                severity_hint=block.severity_hint,
                note_hint=block.note_hint,
            )
        )

    return out
