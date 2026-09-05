"""パーサ共通の型。

ページ番号は「実際に取得できた場合のみ」入れる (必須原則 9 / 禁止事項)。
取得できない形式 (Word / Markdown 等) では None のままにし、出力時に「不明」と表示する。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    """文書中の1かたまり (段落 / 表の1行 / 箇条書き1行)。"""

    text: str
    page: int | None = None
    #: 表由来かどうか (STEP 2 の「表」)
    is_table: bool = False
    #: 見出しレベル (1=章相当)。本文は None。
    heading_level: int | None = None
    #: パーサが直接得た所在情報 (Excel のシート名など)
    locator: str | None = None


@dataclass
class ParsedDocument:
    blocks: list[Block] = field(default_factory=list)
    #: 総ページ数など、文書識別 (STEP 1) に使える情報
    meta: dict[str, str] = field(default_factory=dict)


class ParseError(RuntimeError):
    pass
