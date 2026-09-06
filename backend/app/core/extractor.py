"""STEP 3/5/6: 規定候補抽出 → 規範レベル分類 → 要求事項化。

原文 (original_rule) は必ず保持する。normalized_requirement は原文の語尾変換のみで作り、
語彙の追加・断定は行わない (必須原則 1/3, 禁止事項)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import llm_classify
from app.core import taxonomy as tx
from app.core.structure import Located

#: 行頭の箇条書き記号
LEADING_BULLET = re.compile(r"^\s*(?:[-*・●○◆■□▪]|[（(]?\d+[)）.]|[ａ-ｚa-z][)）.])\s*")

MANDATORY_END = re.compile(tx.MANDATORY_END_PATTERN)

#: え段のかな。直前にこれが来る「る」は一段動詞 (含める / 設ける / 加える …)。
E_ROW_KANA = frozenset("えけげせぜてでねへべぺめれ")


def _is_hiragana(char: str) -> bool:
    return "ぁ" <= char <= "ゟ"
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


def classify_rule_type(
    text: str, rule_type_hint: str | None = None, severity_hint: str | None = None
) -> tuple[str | None, list[str]]:
    """規範レベルを判定する。どのマーカーにも当たらなければ None (規定候補ではない)。

    rule_type_hint は表形式の標準書の「区分」列。標準書自身の分類なので原則それに従うが、
    本文に明示的な禁止表現がある場合だけは本文を優先する (必須原則 7: 禁止を取りこぼさない)。

    severity_hint は「重要度 / 重大度」列。区分列を持たない標準書でも、
    「観点 / 確認内容 / 重大度」形式のレビュー観点表には重要度だけが付く。
    標準書がその行に重要度を与えているのは、レビューで確認する対象として
    挙げているということなので、本文に規範表現が無くても規定として扱う。
    区分が書かれていない以上どの強さかは不明なため、レビューで確認すべき項目
    という意味で Mandatory とし、根拠は「重要度列:高」の形で残す。
    """
    body = _strip_tail(text)

    prohibited = _contains(body, tx.PROHIBITED_MARKERS)
    if prohibited:
        return "Prohibited", prohibited

    if rule_type_hint:
        return rule_type_hint, [f"区分列:{rule_type_hint}"]

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

    # 本文の規範表現が優先。それが無いときだけ重要度列を根拠にする
    if severity_hint:
        return "Mandatory", [f"重要度列:{severity_hint}"]

    return None, []


def _match_category(haystack: str) -> str | None:
    for category, keywords in tx.CATEGORY_KEYWORDS:
        if any(k in haystack for k in keywords):
            return category
    return None


def infer_category(text: str, heading_path: str, category_hint: str | None = None) -> str:
    """分類を決める。

    表形式の標準書が「分類」列を持っているならそれが標準書自身の分類なので最優先。
    次に規定文そのもの。見出しは最後 (文書名が全行に効いて細かい分類を潰すため)。
    """
    # 分類列が分類名そのものを書いている場合 (「完全性」「セキュリティ」等) は
    # そのまま使う。語彙一致に任せると、分類名が語彙に無いために標準書の分類が
    # 捨てられ、本文から別の分類が付いてしまう。
    if category_hint:
        stripped = category_hint.strip()
        if stripped in {name for name, _ in tx.CATEGORY_KEYWORDS}:
            return stripped

    for candidate in (category_hint, text, heading_path):
        if not candidate:
            continue
        matched = _match_category(candidate)
        if matched:
            return matched
    return tx.DEFAULT_CATEGORY


def extract_condition(text: str) -> str | None:
    """条件句をそのまま切り出す (削除しない / 要約しない)。"""
    m = re.search(r"([^、。]{2,60}?(?:場合|とき|際|に限って|に限り|であれば))(?:は|には|に|、|の)", text)
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


#: 禁止規定の語尾 → 語幹に付け替える表現。長い語尾から順に判定する。
#: 五段動詞の活用は語によって変わるため、語幹をそのまま活かせる形だけを使う。
PROHIBITED_ENDINGS: tuple[tuple[str, str], ...] = (
    ("としてはならない", "としないこととしている"),
    ("としてはいけない", "としないこととしている"),
    ("してはならない", "しない設計になっている"),
    ("してはいけない", "しない設計になっている"),
    ("べきではない", "ことがない設計になっている"),
    ("べきでない", "ことがない設計になっている"),
    ("てはならない", "ない設計になっている"),
    ("てはいけない", "ない設計になっている"),
    ("しないこと", "しない設計になっている"),
    ("は避けること", "を避けた設計になっている"),
    ("を避けること", "を避けた設計になっている"),
    ("は認めない", "を行わない設計になっている"),
    ("は許容しない", "を行わない設計になっている"),
    ("は禁止する", "を行わない設計になっている"),
    ("を禁止する", "を行わない設計になっている"),
    ("禁止する", "を行わない設計になっている"),
    ("禁止とする", "を行わない設計になっている"),
    ("は禁止", "を行わない設計になっている"),
    ("を禁止", "を行わない設計になっている"),
)


def normalize_requirement(text: str, rule_type: str) -> str:
    """STEP 6: 規定文 → 要求事項 (状態の記述)。語尾変換のみを行う。"""
    s = _strip_tail(text)

    if rule_type == "Prohibited":
        # 「〜すべきではない」は、サ変 (名詞+する) か五段動詞かで語幹の切り方が変わる。
        # 「す」の直前がひらがなでなければサ変とみなす (共有すべき / 握りつぶすべき)。
        if s.endswith("すべきではない"):
            stem = s[: -len("べきではない")]
            before = stem[-2] if len(stem) >= 2 else ""
            if before and not _is_hiragana(before):
                stem = stem[:-1] + "する"
            return stem + "ことがない設計になっている"

        for ending, suffix in PROHIBITED_ENDINGS:
            if s.endswith(ending):
                return s[: -len(ending)] + suffix
        return f"{s}という禁止規定に適合している"

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
        ("うこと", "っている"),
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

    if s.endswith("ること"):
        stem = s[: -len("ること")]
        # 「える」「ける」「める」等 (え段+る) は一段動詞なので「〜ている」に活用できる
        if stem and stem[-1] in E_ROW_KANA:
            return stem + "ている"
        # 五段動詞は促音便・撥音便が語によって変わるため活用しない。
        # どの動詞でも成立する「〜こととしている」に寄せる。
        return s + "としている"

    if s.endswith("こと"):
        return s + "としている"

    if s.endswith("とする"):
        return s[: -len("とする")] + "としている"
    return s


def split_sentences(text: str) -> list[str]:
    cleaned = LEADING_BULLET.sub("", text.strip())
    parts = [p.strip() for p in re.split(r"(?<=。)", cleaned) if p.strip()]
    return parts or ([cleaned] if cleaned else [])


def _starts_with_exception(sentence: str) -> bool:
    return sentence.lstrip().startswith(tx.EXCEPTION_CONNECTIVES)


def extract_rules(located: list[Located], assist=None) -> list[ExtractedRule]:
    """規定候補を抽出する。

    assist を渡すと、ルールベースが規範表現を見つけられなかった表の行について
    「規定か記述例か」を Claude に尋ねる (`llm_classify`)。既定は None で、
    その場合は従来どおり完全にルールベースで動く。
    """
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
            rule_type, markers = classify_rule_type(
                sentence, item.rule_type_hint, item.severity_hint
            )
            if rule_type is None and assist is not None and item.is_table:
                # 表の行だけを対象にする。本文はルールベースで足りており、
                # 記載例の表まで投げると費用が増えるうえ誤判定の機会も増える
                judged = assist.classify(_strip_tail(sentence))
                if judged is not None:
                    rule_type, evidence = judged
                    markers = [f"{llm_classify.ASSIST_MARKER}:{evidence}"]
            if rule_type is None:
                continue
            body = _strip_tail(sentence)
            rule = ExtractedRule(
                rule_type=rule_type,
                category=infer_category(sentence, item.heading_path, item.category_hint),
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
                notes=item.note_hint,
                # STEP 10: 標準書に重要度の定義があればそれを優先する
                explicit_severity=item.severity_hint or detect_explicit_severity(body),
                matched_markers=markers,
            )
            rules.append(rule)
            last_in_block = rule
    return rules
