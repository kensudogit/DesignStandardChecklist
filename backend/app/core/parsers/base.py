"""パーサ共通の型。

ページ番号は「実際に取得できた場合のみ」入れる (必須原則 9 / 禁止事項)。
取得できない形式 (Word / Markdown 等) では None のままにし、出力時に「不明」と表示する。

表形式の標準書 (Excel 等) では、標準書自身が章・節・区分・重要度を列として持っている。
それらは推測ではなく標準書の記載そのものなので、hint として引き渡す。
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

    # --- 表形式の標準書が列として持っている情報 (推測ではなく記載そのもの) ---
    #: 章番号の列
    chapter: str | None = None
    #: 節番号の列
    section: str | None = None
    #: 分類・カテゴリの列
    category_hint: str | None = None
    #: 区分の列 (必須 / 禁止 / 推奨 / 任意)。正規化済みの規範レベル。
    rule_type_hint: str | None = None
    #: 重要度の列。正規化済みの Critical / High / Medium / Low。
    severity_hint: str | None = None
    #: 備考の列
    note_hint: str | None = None


@dataclass
class ParsedDocument:
    blocks: list[Block] = field(default_factory=list)
    #: 総ページ数など、文書識別 (STEP 1) に使える情報
    meta: dict[str, str] = field(default_factory=dict)


class ParseError(RuntimeError):
    pass
