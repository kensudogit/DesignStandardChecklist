"""STEP 7/6: Atomic Check 分解と質問文化。

1チェック=1確認事項 (必須原則 4)。列挙 (「A、B、Cを記載する」) と
並列動作 (「〜し、〜すること」) を分割する。条件・例外は欠落させない (必須原則 5/6)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.extractor import ExtractedRule, extract_condition, normalize_requirement

#: 「Aし、Bすること」のような並列動作の区切り
CLAUSE_SPLIT = re.compile(r"(?:し、|を行い、|とし、|したうえで、|した上で、)")

#: 列挙の区切り (読点 / 中黒 / スラッシュ)
ENUM_SPLIT = re.compile(r"[、,・／/]")

#: 文末の列挙述部。「〜を記載すること」のように文末に来る場合だけ列挙分解する。
ENUM_PREDICATE_END = re.compile(
    r"(?:を|が)\s*(?:記載|記述|定義|設定|付与|明記|指定|管理|出力|表示|添付)"
    r"(?:する|される|し)?(?:こと|必要がある|ものとする|とする)?$"
)

#: 列挙の前置き (「画面設計書には」「外部API呼出しを行う場合は」)
ENUM_PREFIX = re.compile(r"^(.*?(?:には|では|について|場合は|ときは|は))(.+)$")

#: 分解を抑止する語 (分けると意味が壊れるもの)
NO_SPLIT_MARKERS = ("かつ", "いずれか", "または", "もしくは", "等", "など", "および", "及び")

#: 主題を示す助詞。列挙の前置きとして切り出す。
TOPIC_PARTICLES = ("には", "では", "について", "は")

#: 列挙要素がこれらの助詞で終わる場合、それは列挙ではなく主題提示なので分解しない
TRAILING_PARTICLES = ("は", "が", "を", "に", "へ", "で", "と", "も", "から", "まで", "より")

#: 列挙要素に述語が含まれる場合も分解しない (「〜を行い」等)
VERB_LIKE = re.compile(r"(?:する|した|して|される|できる|行う|行い)$")

MIN_FRAGMENT_LEN = 5
MAX_ENUM_ITEM_LEN = 30


@dataclass
class AtomicCheck:
    check_point: str
    requirement: str
    sub_category: str
    condition: str | None
    exception: str | None
    ambiguity: str | None
    note: str | None = None


def to_question(requirement: str) -> str:
    """要求事項 → Yes/No/N-A で答えられる質問 (必須原則 10)。"""
    s = requirement.strip().rstrip("。？?")
    if s.endswith("か"):
        return s + "？"
    for old, new in (
        ("なっている", "なっているか"),
        ("されている", "されているか"),
        ("している", "しているか"),
        ("である", "であるか"),
        ("がある", "があるか"),
        ("ている", "ているか"),
    ):
        if s.endswith(old):
            return s[: -len(old)] + new + "？"
    return s + "になっているか？"


def _with_condition(question: str, condition: str | None) -> str:
    """条件を落とさない (conversion-rules.md 3)。"""
    if not condition:
        return question
    trimmed = condition.rstrip("、")
    if trimmed in question:
        return question
    return f"{trimmed}、{question}"


def _split_enumeration(sentence: str) -> list[str] | None:
    """「項目ID、項目名、型を記載すること」→ 各項目ごとの規定文に分ける。"""
    if any(m in sentence for m in NO_SPLIT_MARKERS):
        return None
    m = ENUM_PREDICATE_END.search(sentence)
    if not m:
        return None
    head = sentence[: m.start()].strip()
    predicate = sentence[m.start() :].strip()
    items = [i.strip() for i in ENUM_SPLIT.split(head) if i.strip()]
    if len(items) < 2:
        return None

    prefix = ""
    pm = ENUM_PREFIX.match(items[0])
    if pm:
        prefix, items[0] = pm.group(1), pm.group(2)
    elif items[0].endswith(TOPIC_PARTICLES) and len(items) >= 3:
        # 「AテーブルにはX、Y、Zを記載する」のように前置きが独立した要素になっている場合
        prefix, items = items[0], items[1:]
    items = [i for i in items if i]
    if len(items) < 2 or any(len(i) > MAX_ENUM_ITEM_LEN for i in items):
        return None
    # 「Aは、Bを記載すること」のような主題+述部は列挙ではない
    if any(i.endswith(TRAILING_PARTICLES) or VERB_LIKE.search(i) for i in items):
        return None
    return [f"{prefix}{item}{predicate}" for item in items]


def _split_clauses(sentence: str) -> list[str] | None:
    parts = [p.strip() for p in CLAUSE_SPLIT.split(sentence) if p.strip()]
    if len(parts) < 2 or any(len(p) < MIN_FRAGMENT_LEN for p in parts):
        return None
    return parts


def atomize(rule: ExtractedRule) -> list[AtomicCheck]:
    """1規定 → 1件以上の Atomic Check (STEP 8: 1規定から複数チェック可)。"""
    base = rule.original_rule.strip().rstrip("。")
    # 例外句は分解対象から外し、属性として保持する
    if rule.exception and base.endswith(rule.exception):
        base = base[: -len(rule.exception)].strip().rstrip("、。")

    clauses = _split_clauses(base)
    if clauses is not None:
        # 並列動作: 条件はそれを含む節にだけ効く (別の節へ勝手に広げない)
        fragments = [(c, extract_condition(c)) for c in clauses]
    else:
        enum = _split_enumeration(base)
        if enum is not None:
            # 列挙: 前置きの条件は全項目に共通するため引き継ぐ
            fragments = [(e, rule.condition) for e in enum]
        else:
            fragments = [(base, rule.condition)]

    sub_category = rule.heading_path.split(" > ")[-1] if rule.heading_path else ""

    checks: list[AtomicCheck] = []
    for fragment, condition in fragments:
        requirement = normalize_requirement(fragment, rule.rule_type)
        question = _with_condition(to_question(requirement), condition)
        checks.append(
            AtomicCheck(
                check_point=question,
                requirement=requirement,
                sub_category=sub_category,
                condition=condition,
                exception=rule.exception,
                ambiguity=rule.ambiguity,
                note=rule.ambiguity,
            )
        )

    # 例外規定は独立したチェックとして残す (必須原則 6)
    if rule.exception:
        checks.append(
            AtomicCheck(
                check_point=f"例外規定「{rule.exception}」の適用有無が設計上明確になっているか？",
                requirement=f"例外規定: {rule.exception}",
                sub_category="例外",
                condition=rule.condition,
                exception=rule.exception,
                ambiguity=rule.ambiguity,
                note="標準書の例外規定に対応するチェック",
            )
        )
    return checks
