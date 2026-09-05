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
    ("severity", ("重要度", "優先度", "レベル", "ランク")),
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

#: ヘッダ行と判定するのに必要な、役割を特定できた列の数
MIN_HEADER_MATCHES = 3

#: ヘッダを探す範囲 (先頭の改訂履歴などを読み飛ばすため)
HEADER_SEARCH_ROWS = 10

CHAPTER_VALUE = re.compile(r"^第?\s*(\d+)\s*章?$")
SECTION_VALUE = re.compile(r"^(\d+(?:[.\-]\d+)*)$")


def _normalize(text: str) -> str:
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


def detect_schema(rows: list[list[str]]) -> tuple[int, TableSchema] | None:
    """(ヘッダ行のindex, スキーマ) を返す。ヘッダを見つけられなければ None。"""
    for row_index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        roles: dict[int, str] = {}
        used: set[str] = set()
        for column_index, cell in enumerate(row):
            value = _normalize(cell)
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


def map_rule_type(value: str) -> str | None:
    normalized = _normalize(value)
    if not normalized:
        return None
    for rule_type, tokens in RULE_TYPE_VALUES:
        if any(_normalize(t) in normalized for t in tokens):
            return rule_type
    return None


def map_severity(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None
    for severity, tokens in SEVERITY_VALUES:
        if any(t in normalized for t in tokens):
            return severity
    return None


def map_chapter(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip()
    m = CHAPTER_VALUE.match(normalized)
    return m.group(1) if m else (normalized or None)


def map_section(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip()
    m = SECTION_VALUE.match(normalized)
    return m.group(1) if m else (normalized or None)
