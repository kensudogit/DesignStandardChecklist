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

#: 列挙の区切り (読点 / 中黒 / スラッシュ / 並列の接続詞)。
#: 「および」「と」は「AもBも必要」なので分けてよい。「または」は選択なので分けてはいけない。
#: 「と」は「として」「ごとに」等の一部でもあるため、前後の字で除外する。
ENUM_SPLIT = re.compile(r"[、,・／/]|および|及び|(?<![ごこ])と(?![しすいものは同])")

#: 文末の列挙述部。「〜を記載すること」のように文末に来る場合だけ列挙分解する。
ENUM_PREDICATE_END = re.compile(
    r"(?:を|が)\s*(?:記載|記述|定義|設定|付与|明記|指定|管理|出力|表示|添付|使用|見積も|定め|含め)"
    r"(?:する|される|し|る)?(?:こと|必要がある|ものとする|とする)?$"
)

#: 列挙の前置き (「画面設計書には」「機能ごとに」「外部API呼出しを行う場合は」)
ENUM_PREFIX = re.compile(r"^(.*?(?:には|では|について|ごとに|場合は|ときは|は))(.+)$")

#: 列挙要素が「Xの Y」の形のとき、修飾部を全要素で共有する前置きとして切り出す
#: (「リクエストパラメータの型、桁数、必須有無」→ 桁数・必須有無にも「リクエストパラメータの」)
NOUN_MODIFIER = re.compile(r"^(.{2,20}の)(.+)$")

#: 分解を抑止する語 (分けると意味が壊れるもの)。選択・例示は分けない。
NO_SPLIT_MARKERS = ("かつ", "いずれか", "または", "もしくは", "等", "など")

#: 主題を示す助詞。列挙の前置きとして切り出す。
TOPIC_PARTICLES = ("には", "では", "について", "ごとに", "は")

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

    # 末尾の要素が「の」を含むときは分解しない。「桁数および範囲の入力チェック」のように
    # 最後の名詞を全要素で共有している可能性が高く、切ると「桁数を定義する」のような
    # 意味の違う確認事項になってしまう。途中の要素の「の」はその要素自身の修飾なので許す。
    if len(items) >= 2 and "の" in items[-1]:
        return None

    prefix = ""
    # 各要素が自前の主題を持つ列挙 (「参照はGET、登録はPOST、…」) は前置きを切り出さない
    self_contained = sum(1 for item in items if ENUM_PREFIX.match(item)) >= 2
    pm = None if self_contained else ENUM_PREFIX.match(items[0])
    if pm:
        prefix, items[0] = pm.group(1), pm.group(2)
    elif not self_contained and items[0].endswith(TOPIC_PARTICLES) and len(items) >= 3:
        # 「AテーブルにはX、Y、Zを記載する」のように前置きが独立した要素になっている場合
        prefix, items = items[0], items[1:]
    elif not self_contained:
        nm = NOUN_MODIFIER.match(items[0])
        if nm:
            prefix, items[0] = nm.group(1), nm.group(2)
    items = [i for i in items if i]
    if len(items) < 2 or any(len(i) > MAX_ENUM_ITEM_LEN for i in items):
        return None
    # 「Aは、Bを記載すること」のような主題+述部は列挙ではない
    if any(i.endswith(TRAILING_PARTICLES) or VERB_LIKE.search(i) for i in items):
        return None
    return [f"{prefix}{item}{predicate}" for item in items]


#: 先頭節の主題 (「必須項目は」)。後続節に引き継いで主語の欠落を防ぐ。
CLAUSE_TOPIC = re.compile(r"^(.{2,20}?は)(?!.*?は$)")


def _split_clauses(sentence: str) -> list[str] | None:
    parts = [p.strip() for p in CLAUSE_SPLIT.split(sentence) if p.strip()]
    if len(parts) < 2 or any(len(p) < MIN_FRAGMENT_LEN for p in parts):
        return None

    # 「必須項目は識別可能な表示を行い、未入力の場合はエラー表示すること」を分けると、
    # 2つ目が「未入力の場合はエラー表示すること」になり単体では何の話か分からない。
    # 主題は原文の文字列をそのまま複製する (語彙を足さない: 必須原則 1/3)。
    topic = CLAUSE_TOPIC.match(parts[0])
    if topic:
        head = topic.group(1)
        parts = [parts[0]] + [p if p.startswith(head) else head + p for p in parts[1:]]
    return parts


def base_sentence(rule: ExtractedRule) -> str:
    """分解対象の本文。例外句は分解せず属性として保持する。"""
    base = rule.original_rule.strip().rstrip("。")
    if rule.exception and base.endswith(rule.exception):
        base = base[: -len(rule.exception)].strip().rstrip("、。")
    return base


def build_checks(
    rule: ExtractedRule,
    fragments: list[tuple[str, str | None]],
    extra_note: str | None = None,
) -> list[AtomicCheck]:
    """分解済みの断片から Atomic Check を組み立てる。

    分解の仕方 (ルールベース / AI補助) によらずここを通す。要求事項化・質問文化・
    例外チェックの付与を1箇所にまとめておくため。
    """
    sub_category = rule.heading_path.split(" > ")[-1] if rule.heading_path else ""
    note = " / ".join(n for n in (rule.ambiguity, extra_note) if n) or None

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
                note=note,
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


def atomize(rule: ExtractedRule) -> list[AtomicCheck]:
    """1規定 → 1件以上の Atomic Check (STEP 8: 1規定から複数チェック可)。"""
    base = base_sentence(rule)

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

    return build_checks(rule, fragments)
