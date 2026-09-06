"""表形式の標準書のヘッダ行を解釈する。

実務の標準書は「No / 章 / 節 / 分類 / 規定内容 / 区分 / 重要度 / 備考」のような
表になっていることが多い。行をそのまま連結すると規定文が壊れ、標準書自身が
持っている章・節・区分・重要度も捨ててしまうため、列の役割を判定する。

判定できなかった列は無視する。列名を推測して意味を与えることはしない。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: 列の役割 → ヘッダ名に含まれる語 (先に一致した役割を採る)
HEADER_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("rule", ("規定内容", "規定", "記述内容", "標準内容", "チェック内容", "ルール", "基準内容", "内容")),
    ("chapter", ("章番号", "章")),
    ("section", ("節番号", "節", "条項", "項番")),
    ("category", ("分類", "カテゴリ", "カテゴリー", "観点", "対象")),
    ("rule_type", ("必須区分", "強制力", "区分", "種別")),
    ("severity", ("重要度", "重大度", "優先度", "レベル", "ランク")),
    ("no", ("no", "№", "番号", "通番")),
    ("note", ("備考", "補足", "メモ", "注記")),
]

#: 区分列の値 → 規範レベル (STEP 5)
RULE_TYPE_VALUES: list[tuple[str, tuple[str, ...]]] = [
    ("Conditional Mandatory", ("条件付き必須", "条件付必須", "条件付き", "条件付")),
    ("Prohibited", ("禁止", "不可", "NG")),
    ("Mandatory", ("必須", "MUST", "must", "強制")),
    ("Recommended", ("推奨", "SHOULD", "should", "原則")),
    ("Optional", ("任意", "MAY", "may", "参考")),
]

#: 重要度列の値 → Severity (STEP 10)
SEVERITY_VALUES: list[tuple[str, tuple[str, ...]]] = [
    ("Critical", ("重大", "致命", "最高", "Critical", "critical", "A", "S")),
    ("High", ("高", "High", "high", "B")),
    ("Medium", ("中", "Medium", "medium", "C")),
    ("Low", ("低", "軽微", "Low", "low", "D")),
]

#: ヘッダ行と判定するのに必要な、役割を特定できた列の数。
#: 少なすぎると本文の行を誤ってヘッダと判定する。
MIN_HEADER_MATCHES = 3

CHAPTER_VALUE = re.compile(r"^第?\s*(\d+)\s*章?$")
SECTION_VALUE = re.compile(r"^(\d+(?:[.\-]\d+)*)$")


def _normalize(text: str) -> str:
    """比較用に表記を揃える。全角・半角と大文字・小文字の違いを吸収する。"""
    return unicodedata.normalize("NFKC", text).strip().lower()


@dataclass
class TableSchema:
    """列インデックス → 役割。"""

    roles: dict[int, str] = field(default_factory=dict)

    @property
    def rule_column(self) -> int | None:
        for index, role in self.roles.items():
            if role == "rule":
                return index
        return None

    def column_of(self, role: str) -> int | None:
        for index, name in self.roles.items():
            if name == role:
                return index
        return None


@dataclass(frozen=True)
class TableRegion:
    """1つの表。ヘッダ行と、その列対応が通用する行の範囲。"""

    #: ヘッダ行の index
    header_index: int
    schema: TableSchema
    #: この表に属する最後の行の index (含む)。次の表のヘッダの手前まで。
    end_index: int


def _detect_header(rows: list[list[str]], start: int) -> tuple[int, TableSchema] | None:
    """start 以降で最初に見つかるヘッダ行を返す。"""
    for row_index in range(start, len(rows)):
        roles: dict[int, str] = {}
        used: set[str] = set()
        for column_index, cell in enumerate(rows[row_index]):
            value = _normalize(cell)
            # 長いセルは見出しではなく本文。ヘッダ行の判定から外す
            if not value or len(value) > 12:
                continue
            for role, keywords in HEADER_KEYWORDS:
                if role in used:
                    continue
                if any(_normalize(k) in value for k in keywords):
                    roles[column_index] = role
                    used.add(role)
                    break
        # 規定内容の列が特定できないヘッダは、表の意味を読み違えるので採用しない
        if len(roles) >= MIN_HEADER_MATCHES and "rule" in used:
            return row_index, TableSchema(roles=roles)
    return None


def detect_tables_with_assist(rows: list[list[str]], assist) -> list[TableRegion]:
    """語彙一致で1つも表を見つけられなかったときだけ、Claude に列の役割を尋ねる。

    「強制度」「レベル区分」のように語彙表に無い見出しを使う標準書を拾うため。
    ヘッダらしい行 (短いセルが3つ以上並ぶ行) を上から順に試し、規定本文の列を
    特定できたところで採用する。特定できなければ従来どおり行全体を連結する。
    """
    found = detect_tables(rows)
    if found or assist is None or not hasattr(assist, "column_roles"):
        return found

    for row_index, row in enumerate(rows):
        cells = [c for c in row if c.strip()]
        # 本文の行を投げないための足切り。ヘッダは短い語が並ぶ
        if len(cells) < MIN_HEADER_MATCHES or any(len(c) > 12 for c in cells):
            continue
        roles = assist.column_roles(row)
        # 規定本文の列が定まらない答えは使わない。表の意味を読み違えるうえ、
        # 後段が rule_column を前提にしている。補助側でも検証しているが、
        # 差し替え可能な相手を信用せず、使う側でも確かめる
        if roles and list(roles.values()).count("rule") == 1:
            return [
                TableRegion(
                    header_index=row_index,
                    schema=TableSchema(roles=roles),
                    end_index=len(rows) - 1,
                )
            ]
    return found


def detect_tables(rows: list[list[str]]) -> list[TableRegion]:
    """シート内の表をすべて拾う。

    1枚のシートに表が複数並ぶ標準書がある (記載例の表と、レビュー観点の表など)。
    最初の表のヘッダを全行へ当てると、別の表の列を取り違える。実際、確認内容の
    列を持つ表に記載例の表の列対応を当てて「NG例」を規定内容として読む、という
    取り違えが起きていた。表ごとに自分のヘッダを使う。

    行が上から下へ並ぶ前提で、次のヘッダが現れた行の手前までを1つの表とみなす。
    表と表の間にある見出し行や空行は、その表の規定内容の列が空になるため
    後段で落ちる。
    """
    headers: list[tuple[int, TableSchema]] = []
    index = 0
    while index < len(rows):
        found = _detect_header(rows, index)
        if found is None:
            break
        headers.append(found)
        index = found[0] + 1

    return [
        TableRegion(
            header_index=header_index,
            schema=schema,
            end_index=(headers[position + 1][0] - 1)
            if position + 1 < len(headers)
            else len(rows) - 1,
        )
        for position, (header_index, schema) in enumerate(headers)
    ]


def detect_schema(rows: list[list[str]]) -> tuple[int, TableSchema] | None:
    """先頭の表だけを返す。表が1つしか無い前提の呼び出し向け。"""
    tables = detect_tables(rows)
    if not tables:
        return None
    return tables[0].header_index, tables[0].schema


def map_rule_type(value: str) -> str | None:
    """区分列の値を規範レベルへ写す (STEP 5)。判定できなければ None。

    「条件付き必須」を先に見るのは、「必須」が部分一致で先に当たってしまい、
    条件の存在が消えるのを防ぐため。RULE_TYPE_VALUES の並び順に意味がある。
    """
    normalized = _normalize(value)
    if not normalized:
        return None
    for rule_type, tokens in RULE_TYPE_VALUES:
        if any(_normalize(t) in normalized for t in tokens):
            return rule_type
    return None


def map_severity(value: str) -> str | None:
    """重要度列の値を Severity へ写す (STEP 10)。判定できなければ None。

    大文字小文字を潰さないのは、A/B/C/D や S といった1文字の記号を
    区別する必要があるため。
    """
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None
    for severity, tokens in SEVERITY_VALUES:
        if any(t in normalized for t in tokens):
            return severity
    return None


def map_chapter(value: str) -> str | None:
    """章番号の列を読む。「第3章」からは 3 を取り出し、それ以外は記載のまま返す。"""
    normalized = unicodedata.normalize("NFKC", value).strip()
    m = CHAPTER_VALUE.match(normalized)
    return m.group(1) if m else (normalized or None)


def map_section(value: str) -> str | None:
    """節番号の列を読む。「3.2.1」形式ならそのまま、それ以外は記載のまま返す。"""
    normalized = unicodedata.normalize("NFKC", value).strip()
    m = SECTION_VALUE.match(normalized)
    return m.group(1) if m else (normalized or None)
