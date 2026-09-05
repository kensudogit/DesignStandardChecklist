"""STEP 3/5/6: 規定候補抽出 → 規範レベル分類 → 要求事項化。

原文 (original_rule) は必ず保持する。normalized_requirement は原文の語尾変換のみで作り、
語彙の追加・断定は行わない (必須原則 1/3, 禁止事項)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import taxonomy as tx
from app.core.structure import Located

#: 行頭の箇条書き記号
LEADING_BULLET = re.compile(r"^\s*(?:[-*・●○◆■□▪]|[（(]?\d+[)）.]|[ａ-ｚa-z][)）.])\s*")

MANDATORY_END = re.compile(tx.MANDATORY_END_PATTERN)
OPTIONAL_END = re.compile(tx.OPTIONAL_END_PATTERN)


@dataclass
class ExtractedRule:
    rule_type: str
    category: str
    original_rule: str
    normalized_requirement: str
    chapter: str | None
    section: str | None
    page: int | None
    heading_path: str
    condition: str | None = None
    exception: str | None = None
    ambiguity: str | None = None
    notes: str | None = None
    locator: str | None = None
    order: int = 0
    #: 明示的な重要度が原文にあった場合のみ入る
    explicit_severity: str | None = None
    matched_markers: list[str] = field(default_factory=list)


def _contains(text: str, markers: tuple[str, ...]) -> list[str]:
    return [m for m in markers if m in text]


def _strip_tail(text: str) -> str:
    return text.strip().rstrip("。．.")


def classify_rule_type(text: str) -> tuple[str | None, list[str]]:
    """規範レベルを判定する。どのマーカーにも当たらなければ None (規定候補ではない)。"""
    body = _strip_tail(text)

    prohibited = _contains(body, tx.PROHIBITED_MARKERS)
    if prohibited:
        return "Prohibited", prohibited

    mandatory = _contains(body, tx.MANDATORY_MARKERS)
    if MANDATORY_END.search(body):
        mandatory = mandatory + [f"文末:{MANDATORY_END.search(body).group(0)}"]  # type: ignore[union-attr]

    recommended = _contains(body, tx.RECOMMENDED_MARKERS)

    optional = _contains(body, tx.OPTIONAL_MARKERS)
    if OPTIONAL_END.search(body):
        optional = optional + [f"文末:{OPTIONAL_END.search(body).group(0)}"]  # type: ignore[union-attr]

    # 「任意とする」のように任意表現と汎用的な必須語尾が同居する場合、
    # 明示的な必須表現が無ければ任意と判定する (必須原則 7)
    if optional and not _contains(body, tx.STRONG_MANDATORY_MARKERS):
        return "Optional", optional

    if mandatory:
        conditions = _contains(body, tx.CONDITION_MARKERS)
        if conditions:
            # 「〜する場合は〜すること」= 条件付き必須 (必須原則 5)
            return "Conditional Mandatory", mandatory + conditions
        if recommended:
            # 「原則として〜すること」は推奨側に寄せる
            return "Recommended", mandatory + recommended
        return "Mandatory", mandatory

    if recommended:
        return "Recommended", recommended

    return None, []


def infer_category(text: str, heading_path: str) -> str:
    haystack = f"{heading_path} {text}"
    for category, keywords in tx.CATEGORY_KEYWORDS:
        if any(k in haystack for k in keywords):
            return category
    return tx.DEFAULT_CATEGORY


def extract_condition(text: str) -> str | None:
    """条件句をそのまま切り出す (削除しない / 要約しない)。"""
    m = re.search(r"([^、。]{2,60}?(?:場合|とき|際|に限り|であれば))(?:は|には|に|、)", text)
    if m:
        return m.group(1).strip()
    return None


def extract_exception(text: str) -> str | None:
    for marker in tx.EXCEPTION_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            return _strip_tail(text[idx:])
    return None


def detect_ambiguity(text: str) -> str | None:
    hits = _contains(text, tx.AMBIGUOUS_MARKERS)
    if not hits:
        return None
    return "確認要: 曖昧表現「" + "」「".join(hits) + "」の判定基準が標準書内で明確化されていない"


def detect_explicit_severity(text: str) -> str | None:
    for severity, markers in tx.EXPLICIT_SEVERITY_MARKERS:
        if any(m in text for m in markers):
            return severity
    return None


#: 禁止規定の語尾 → (除去する語尾, 質問の接尾)
PROHIBITED_ENDINGS: tuple[tuple[str, str], ...] = (
    ("としてはならない", "としない"),
    ("としてはいけない", "としない"),
    ("してはならない", "しない"),
    ("してはいけない", "しない"),
    ("てはならない", "ない"),
    ("てはいけない", "ない"),
    ("しないこと", "しない"),
    ("は禁止する", "を行わない"),
    ("を禁止する", "を行わない"),
    ("禁止する", "を行わない"),
    ("禁止とする", "を行わない"),
    ("は禁止", "を行わない"),
    ("を禁止", "を行わない"),
)


def normalize_requirement(text: str, rule_type: str) -> str:
    """STEP 6: 規定文 → 要求事項 (状態の記述)。語尾変換のみを行う。"""
    s = _strip_tail(text)

    if rule_type == "Prohibited":
        for ending, negated in PROHIBITED_ENDINGS:
            if s.endswith(ending):
                stem = s[: -len(ending)]
                # 「〜設計としてはならない」で「設計としない設計」と重複するのを避ける
                if negated == "としない" and stem.endswith(("設計", "構成", "方式")):
                    return f"{stem}としないこととしている"
                return f"{stem}{negated}設計になっている"
        return f"{s}（禁止規定）に違反していない"

    replacements = [
        ("しなければならない", "している"),
        ("する必要がある", "している"),
        ("とすること", "としている"),
        ("であること", "である"),
        ("されていること", "されている"),
        ("していること", "している"),
        ("を必須とする", "を必須としている"),
        ("必須とする", "必須としている"),
        ("を推奨する", "としている"),
        ("推奨する", "としている"),
        ("が望ましい", "としている"),
        ("すること", "している"),
        ("けること", "けている"),
        ("うこと", "っている"),
        ("ること", "っている"),
        ("こと", "ている"),
        ("とする", "としている"),
        ("記載する", "記載している"),
        ("記述する", "記述している"),
        ("定義する", "定義している"),
        ("設定する", "設定している"),
        ("付与する", "付与している"),
        ("添付する", "添付している"),
        ("明記する", "明記している"),
        ("管理する", "管理している"),
        ("適用する", "適用している"),
        ("作成する", "作成している"),
        ("準拠する", "準拠している"),
    ]
    for old, new in replacements:
        if s.endswith(old):
            return s[: -len(old)] + new
    return s


def split_sentences(text: str) -> list[str]:
    cleaned = LEADING_BULLET.sub("", text.strip())
    parts = [p.strip() for p in re.split(r"(?<=。)", cleaned) if p.strip()]
    return parts or ([cleaned] if cleaned else [])


def _starts_with_exception(sentence: str) -> bool:
    return sentence.lstrip().startswith(tx.EXCEPTION_CONNECTIVES)


def extract_rules(located: list[Located]) -> list[ExtractedRule]:
    rules: list[ExtractedRule] = []
    for item in located:
        if item.is_heading:
            continue
        last_in_block: ExtractedRule | None = None
        for sentence in split_sentences(item.text):
            # 「〜すること。ただし、〜」の例外文を直前の規定へ引き継ぐ (必須原則 6)
            if _starts_with_exception(sentence) and last_in_block is not None:
                clause = _strip_tail(sentence)
                last_in_block.exception = (
                    f"{last_in_block.exception} / {clause}" if last_in_block.exception else clause
                )
                continue
            if len(sentence) < 6:
                continue
            rule_type, markers = classify_rule_type(sentence)
            if rule_type is None:
                continue
            body = _strip_tail(sentence)
            rule = ExtractedRule(
                rule_type=rule_type,
                category=infer_category(sentence, item.heading_path),
                original_rule=body,
                normalized_requirement=normalize_requirement(body, rule_type),
                chapter=item.chapter,
                section=item.section,
                page=item.page,
                heading_path=item.heading_path,
                condition=extract_condition(body),
                exception=extract_exception(body),
                ambiguity=detect_ambiguity(body),
                locator=item.locator,
                order=item.order,
                explicit_severity=detect_explicit_severity(body),
                matched_markers=markers,
            )
            rules.append(rule)
            last_in_block = rule
    return rules
