"""抽出エンジンの単体テスト。SKILL.md の必須原則をそのままテストにしている。"""

from __future__ import annotations

import pytest

from app.core.atomizer import atomize, to_question
from app.core.dedupe import find_duplicates
from app.core.extractor import (
    classify_rule_type,
    detect_ambiguity,
    extract_condition,
    extract_exception,
    extract_rules,
    infer_category,
    normalize_requirement,
)
from app.core.parsers import parse_document
from app.core.severity import decide_severity
from app.core.structure import assign_structure


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("画面項目には項目IDを付与すること。", "Mandatory"),
        ("入力項目にはラベルを関連付けること。", "Mandatory"),
        ("画面名称は業務用語を用いて記載する。", "Mandatory"),
        ("メッセージ区分は情報、警告、エラーのいずれかとする。", "Mandatory"),
        ("パスワードをログへ出力してはならない。", "Prohibited"),
        ("パスワードをURLパラメータに含めてはならない。", "Prohibited"),
        ("色のみで情報を区別する設計としてはならない。", "Prohibited"),
        ("動的SQLの使用は禁止する。", "Prohibited"),
        ("外部API呼出しを行う場合はタイムアウト値を定義すること。", "Conditional Mandatory"),
        ("検索結果は100件以内とすることを推奨する。", "Recommended"),
        ("補足資料の添付は任意とする。", "Optional"),
        ("参照専用項目の初期値は定義を省略できる。", "Optional"),
        ("本章では画面設計書の記述方法を説明します。", None),
    ],
)
def test_classify_rule_type(sentence: str, expected: str | None) -> None:
    assert classify_rule_type(sentence)[0] == expected


def test_mandatory_and_prohibited_are_not_confused() -> None:
    """必須原則 7: 必須・禁止・推奨・任意を混同しない。"""
    # 「しなければならない」は禁止ではなく必須
    assert classify_rule_type("設計書は承認を受けなければならない。")[0] == "Mandatory"


def test_condition_is_preserved() -> None:
    """必須原則 5 / conversion-rules.md 3: 条件を削除しない。"""
    sentence = "外部API呼出しを行う場合はタイムアウト値を定義すること。"
    condition = extract_condition(sentence)
    assert condition == "外部API呼出しを行う場合"

    rules = _rules_from_markdown(f"# 標準\n\n## 1 API\n\n{sentence}\n")
    checks = atomize(rules[0])
    assert len(checks) == 1
    assert "外部API呼出しを行う場合" in checks[0].check_point
    assert checks[0].check_point.endswith("か？")


def test_exception_is_preserved_across_sentences() -> None:
    """必須原則 6: 例外規定を欠落させない (「ただし」が次の文でも拾う)。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 1 項目\n\n項目の初期値を定義すること。ただし、参照専用項目は省略できる。\n"
    )
    assert len(rules) == 1
    assert rules[0].exception is not None
    assert "参照専用項目" in rules[0].exception

    checks = atomize(rules[0])
    assert any("例外規定" in c.check_point for c in checks)


def test_exception_inside_sentence() -> None:
    text = "帳票は日次で出力すること。ただし、月次帳票を除く。"
    assert extract_exception("帳票は日次で出力すること、ただし月次帳票を除く") is not None
    rules = _rules_from_markdown(f"# 標準\n\n## 1 帳票\n\n{text}\n")
    assert rules[0].exception is not None


def test_atomic_split_of_enumeration() -> None:
    """STEP 7: 複数確認事項を含む規定は分割する。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 3.2 項目定義\n\n"
        "項目定義表には項目ID、項目名称、データ型、桁数、必須区分を記載すること。\n"
    )
    checks = atomize(rules[0])
    assert len(checks) == 5
    points = " ".join(c.check_point for c in checks)
    for token in ("項目ID", "項目名称", "データ型", "桁数", "必須区分"):
        assert token in points
    # 前置きは各チェックに引き継がれる
    assert all(c.check_point.startswith("項目定義表には") for c in checks)


def test_topic_marker_is_not_treated_as_enumeration() -> None:
    """「Aは、Bを記載すること」は列挙ではないので分割しない。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 3.2 項目\n\nコード値を持つ項目は、参照するコードマスタ名を記載すること。\n"
    )
    checks = atomize(rules[0])
    assert len(checks) == 1
    assert "コード値を持つ項目は" in checks[0].check_point


def test_parallel_clause_split_keeps_condition_local() -> None:
    """並列節の分割時、条件を無関係な節へ広げない。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 3.4 入力\n\n必須項目は識別可能な表示を行い、未入力の場合はエラー表示すること。\n"
    )
    checks = atomize(rules[0])
    assert len(checks) == 2
    assert "未入力の場合" not in checks[0].check_point
    assert "未入力の場合" in checks[1].check_point


def test_prohibited_check_is_answerable_as_yes_when_compliant() -> None:
    """conversion-rules.md 2: 禁止規定は「〜しない設計になっているか？」に変換する。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 5 セキュリティ\n\nパスワードをログへ出力してはならない。\n"
    )
    check = atomize(rules[0])[0]
    assert check.check_point == "パスワードをログへ出力しない設計になっているか？"


def test_prohibited_design_phrase_has_no_duplicated_wording() -> None:
    rules = _rules_from_markdown(
        "# 標準\n\n## 6 アクセシビリティ\n\n色のみで情報を区別する設計としてはならない。\n"
    )
    check = atomize(rules[0])[0]
    assert check.check_point == "色のみで情報を区別する設計としないこととしているか？"


def test_ambiguity_is_flagged_not_invented() -> None:
    """conversion-rules.md 5: 曖昧表現に対し勝手な基準を作らない。"""
    note = detect_ambiguity("画面項目には適切な名称を設定すること。")
    assert note is not None
    assert "確認要" in note and "適切な" in note


def test_every_check_point_is_a_question() -> None:
    """必須原則 10: Yes / No / N/A で判定可能な粒度。"""
    rules = _rules_from_file()
    for rule in rules:
        for check in atomize(rule):
            assert check.check_point.endswith("か？"), check.check_point


def test_to_question_handles_known_endings() -> None:
    assert to_question("項目IDが付与されている") == "項目IDが付与されているか？"
    assert to_question("マスク表示としている") == "マスク表示としているか？"


@pytest.mark.parametrize(
    ("text", "category", "rule_type", "expected"),
    [
        ("パスワードをマスク表示とすること", "セキュリティ", "Mandatory", "Critical"),
        ("個人情報の暗号化を行うこと", "セキュリティ", "Mandatory", "Critical"),
        ("排他制御方式を定義すること", "排他", "Mandatory", "High"),
        ("動的SQLを使用してはならない", "DB", "Prohibited", "High"),
        ("命名は統一すること", "命名", "Recommended", "Medium"),
        ("検索結果は100件以内を推奨する", "性能", "Recommended", "Low"),
        ("補足資料の添付は任意とする", "完全性", "Optional", "Low"),
    ],
)
def test_severity(text: str, category: str, rule_type: str, expected: str) -> None:
    assert decide_severity(text=text, category=category, rule_type=rule_type)[0] == expected


def test_explicit_severity_wins() -> None:
    """STEP 10: 標準書に定義がある場合は標準書を優先する。"""
    severity, reason = decide_severity(
        text="パスワードは暗号化すること",
        category="セキュリティ",
        rule_type="Mandatory",
        explicit_severity="Low",
    )
    assert severity == "Low"
    assert "標準書" in reason


def test_category_inference() -> None:
    assert infer_category("主キーを定義すること", "") == "DB"
    assert infer_category("タイムアウト値を定義すること", "") == "性能"
    assert infer_category("代替テキストを設定すること", "") == "アクセシビリティ"


def test_normalize_requirement_does_not_add_vocabulary() -> None:
    """必須原則 1/3: 語尾変換のみ。名詞や条件を足さない。"""
    out = normalize_requirement("画面項目には項目IDを付与すること", "Mandatory")
    assert out == "画面項目には項目IDを付与している"


def test_duplicate_detection() -> None:
    """STEP 11: 完全重複は統合、類似は候補として残す。"""
    points = [
        "項目IDが付与されているか？",
        "項目IDが付与されているか？",  # 完全重複
        "項目名称が記載されているか？",
    ]
    groups, merged = find_duplicates(points)
    assert merged == {1}
    assert groups[0].exact_duplicates == [1]


def test_structure_assigns_chapter_and_section() -> None:
    """STEP 2/12: 章・節を本文中の表記からのみ取る。"""
    located = _located_from_markdown(
        "# 標準\n\n## 3 画面設計書の記述\n\n### 3.2 項目定義\n\n画面項目には項目IDを付与すること。\n"
    )
    body = [item for item in located if not item.is_heading]
    assert body[0].chapter == "3"
    assert body[0].section == "3.2"


def test_markdown_has_no_page_numbers() -> None:
    """禁止事項: ページ番号を推測しない。Markdown では page は None。"""
    located = _located_from_markdown("# 標準\n\n## 1 章\n\n項目IDを付与すること。\n")
    assert all(item.page is None for item in located)


# --- helpers -----------------------------------------------------------------


def _located_from_markdown(text: str):
    parsed = parse_document("sample.md", text.encode("utf-8"))
    return assign_structure(parsed.blocks)


def _rules_from_markdown(text: str):
    return extract_rules(_located_from_markdown(text))


def _rules_from_file():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "samples" / "画面設計標準.md"
    parsed = parse_document(path.name, path.read_bytes())
    return extract_rules(assign_structure(parsed.blocks))


def test_enumeration_with_standalone_prefix_is_split() -> None:
    """前置きが独立した要素になっている列挙も分割し、前置きを各チェックへ引き継ぐ。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 7 履歴\n\n"
        "更新履歴を保持するテーブルには、登録日時、更新日時、更新者を記載すること。\n"
    )
    checks = atomize(rules[0])
    assert len(checks) == 3
    assert all(c.check_point.startswith("更新履歴を保持するテーブルには") for c in checks)
    points = " ".join(c.check_point for c in checks)
    for token in ("登録日時", "更新日時", "更新者"):
        assert token in points


def test_two_element_topic_phrase_is_still_not_split() -> None:
    """要素が2つだけの「Aは、Bを記載する」は主題+述部なので分割しない。"""
    rules = _rules_from_markdown(
        "# 標準\n\n## 3.2 項目\n\nコード値を持つ項目は、参照するコードマスタ名を記載すること。\n"
    )
    assert len(atomize(rules[0])) == 1
