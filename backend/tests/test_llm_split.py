"""AI補助による分解 (STEP 7 補助) の単体テスト。

要は「Claude が何を返してきても、原文に無い語がチェック項目に入らない」ことの確認。
API は呼ばない。応答をキャッシュに仕込んで、検証と組み立てだけを動かす。
"""

from __future__ import annotations

import pytest

from app.core.extractor import ExtractedRule, extract_rules
from app.core.llm_split import (
    ASSIST_NOTE,
    SplitAssist,
    SplitCache,
    SplitPlan,
    is_candidate,
    validate,
)
from app.core.parsers import parse_document
from app.core.pipeline import checks_for_rule
from app.core.structure import assign_structure

SPLIT_ME = "数値項目には桁数および範囲の入力チェックを定義すること"
GOOD_PAYLOAD = {
    "split": True,
    "prefix": "数値項目には",
    "items": ["桁数", "範囲"],
    "suffix": "の入力チェックを定義すること",
    "reason": "桁数と範囲は別々に欠落し得る",
}


def _rule(sentence: str) -> ExtractedRule:
    """1文だけの標準書として通常の抽出を通す。"""
    parsed = parse_document("test.md", f"# テスト標準\n\n{sentence}。\n".encode())
    rules = extract_rules(assign_structure(parsed.blocks))
    assert rules, f"規定として抽出されなかった: {sentence}"
    return rules[0]


def _assist(payloads: dict[str, dict]) -> SplitAssist:
    """応答を仕込んだ補助。path=None なのでファイルにも API にも触れない。"""
    cache = SplitCache(None)
    for sentence, payload in payloads.items():
        cache.put(sentence, payload)
    return SplitAssist(cache=cache)


# --- 候補の足切り -----------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        SPLIT_ME,
        "処理の開始と終了をログに出力すること",
        "連携の実行時刻および実行順序を運用設計書と対応付けて記載すること",
    ],
)
def test_coordination_is_a_candidate(sentence: str) -> None:
    assert is_candidate(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "排他制御方式は楽観ロックまたは悲観ロックのいずれかとする",  # 選択は分けない
        "項目ID、項目名、型等を記載すること",  # 例示は分けない
        "画面項目には項目IDを付与すること",  # 並列がない
        "画面ごとに権限を定義すること",  # 「ごとに」の「と」は並列ではない
        "短い",  # 短すぎる
    ],
)
def test_non_coordination_is_not_a_candidate(sentence: str) -> None:
    assert not is_candidate(sentence)


# --- 提案の検証 -------------------------------------------------------------


def test_valid_plan_reconstructs_the_original() -> None:
    plan = SplitPlan(prefix="数値項目には", items=("桁数", "範囲"), suffix="の入力チェックを定義すること")
    assert validate(SPLIT_ME, plan)
    assert plan.render() == [
        "数値項目には桁数の入力チェックを定義すること",
        "数値項目には範囲の入力チェックを定義すること",
    ]


@pytest.mark.parametrize(
    ("plan", "why"),
    [
        (
            SplitPlan(prefix="数値項目には", items=("桁数", "上限"), suffix="の入力チェックを定義すること"),
            "原文に無い語 (上限) を含む",
        ),
        (
            SplitPlan(prefix="数値項目には", items=("範囲", "桁数"), suffix="の入力チェックを定義すること"),
            "原文と順序が違う",
        ),
        (
            SplitPlan(prefix="", items=("桁数", "範囲"), suffix="の入力チェックを定義すること"),
            "prefix が欠けていて原文を覆えない",
        ),
        (
            SplitPlan(prefix="数値項目には", items=("桁数", "範囲"), suffix="を定義すること"),
            "suffix が原文と一致しない",
        ),
        (
            SplitPlan(prefix="数値項目には", items=("桁数",), suffix="の入力チェックを定義すること"),
            "要素が1件しかない",
        ),
        (
            SplitPlan(prefix="数値項目には", items=("桁数", "桁数"), suffix="の入力チェックを定義すること"),
            "要素が重複している",
        ),
    ],
)
def test_invalid_plan_is_rejected(plan: SplitPlan, why: str) -> None:
    assert not validate(SPLIT_ME, plan), why


def test_connector_must_come_from_the_original() -> None:
    """要素の間に原文の接続語以外が挟まっていたら通さない。"""
    sentence = "AとBを記載すること"
    assert validate(sentence, SplitPlan(prefix="", items=("A", "B"), suffix="を記載すること"))
    # 原文が「と」なのに、要素の間に原文に無い文字があるとみなされる切り方
    assert not validate(sentence, SplitPlan(prefix="", items=("A", "を"), suffix="記載すること"))


# --- パイプラインへの組み込み -----------------------------------------------


def test_assist_splits_what_the_rule_based_path_could_not() -> None:
    rule = _rule(SPLIT_ME)
    without, _ = checks_for_rule(rule)
    assert len(without) == 1, "ルールベースでは1件のままであること (前提)"

    with_assist, reason = checks_for_rule(rule, assist=_assist({SPLIT_ME: GOOD_PAYLOAD}))
    assert reason is None
    points = [c.check_point for c in with_assist]
    assert len(points) == 2
    assert any("桁数" in p and "入力チェック" in p for p in points)
    assert any("範囲" in p and "入力チェック" in p for p in points)


def test_assisted_checks_carry_their_provenance() -> None:
    rule = _rule(SPLIT_ME)
    checks, _ = checks_for_rule(rule, assist=_assist({SPLIT_ME: GOOD_PAYLOAD}))
    assert all(ASSIST_NOTE in (c.note or "") for c in checks)


def test_assisted_check_points_use_only_words_from_the_original() -> None:
    """必須原則 1/3: 標準書に無い語を足さない。"""
    rule = _rule(SPLIT_ME)
    checks, _ = checks_for_rule(rule, assist=_assist({SPLIT_ME: GOOD_PAYLOAD}))
    for check in checks:
        core = check.check_point.rstrip("か？")
        # 語尾変換で足される語だけを除けば、残りは原文に現れる
        for fragment in ("桁数", "範囲", "入力チェック", "数値項目"):
            if fragment in core:
                assert fragment in rule.original_rule


def test_invalid_suggestion_falls_back_to_the_rule_based_result() -> None:
    bad = dict(GOOD_PAYLOAD, items=["桁数", "上限"])  # 原文に無い語
    assist = _assist({SPLIT_ME: bad})
    checks, reason = checks_for_rule(_rule(SPLIT_ME), assist=assist)
    assert reason is None
    assert len(checks) == 1
    assert "上限" not in checks[0].check_point
    assert assist.stats["rejected"] == 1


def test_split_false_leaves_the_rule_untouched() -> None:
    sentence = "業務エラーとシステムエラーを区別して設計すること"
    payload = {"split": False, "prefix": "", "items": [], "suffix": "", "reason": "1つの要求"}
    checks, _ = checks_for_rule(_rule(sentence), assist=_assist({sentence: payload}))
    assert len(checks) == 1


def test_assist_is_not_consulted_when_the_rule_based_path_already_split() -> None:
    sentence = "画面設計書には画面ID、画面名称を記載すること"
    assist = _assist({})
    checks, _ = checks_for_rule(_rule(sentence), assist=assist)
    assert len(checks) == 2
    assert assist.stats == {"asked": 0, "cached": 0, "rejected": 0}


def test_without_assist_nothing_changes() -> None:
    rule = _rule(SPLIT_ME)
    assert checks_for_rule(rule) == checks_for_rule(rule, assist=None)


# --- キャッシュ -------------------------------------------------------------


def test_cache_round_trips_through_a_file(tmp_path) -> None:
    path = tmp_path / "cache.json"
    SplitCache(path).put(SPLIT_ME, GOOD_PAYLOAD)
    assert path.exists()
    assert SplitCache(path).get(SPLIT_ME) == GOOD_PAYLOAD


def test_cache_key_changes_with_the_sentence() -> None:
    assert SplitCache.key(SPLIT_ME) != SplitCache.key(SPLIT_ME + "。")


def test_cached_answer_is_reused_without_asking() -> None:
    assist = _assist({SPLIT_ME: GOOD_PAYLOAD})
    assist.plan_for(SPLIT_ME)
    assist.plan_for(SPLIT_ME)
    assert assist.stats["asked"] == 0
    assert assist.stats["cached"] == 2
