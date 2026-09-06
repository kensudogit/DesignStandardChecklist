# -*- coding: utf-8 -*-
"""STEP 5 補助（規定か記述例かの判定）の検証。

Claude は呼ばない。応答を模した dict を validate に通して、受け入れる条件と
捨てる条件を確かめる。パイプラインへの組み込みは、判定を返すだけの偽の補助で見る。
"""

from __future__ import annotations

import io

import pytest

from app.core import llm_classify
from app.core.extractor import extract_rules
from app.core.parsers import parse_document
from app.core.structure import assign_structure

SENTENCE = "要件IDを必ず紐付ける"


# --- 応答の検証 ---------------------------------------------------------------


def test_a_valid_answer_is_accepted() -> None:
    payload = {"is_rule": True, "rule_type": "Mandatory", "evidence": "必ず"}
    assert llm_classify.validate(SENTENCE, payload) == ("Mandatory", "必ず")


def test_an_answer_saying_it_is_an_example_is_dropped() -> None:
    """記述例と判定されたら規定にしない。"""
    payload = {"is_rule": False, "rule_type": "Mandatory", "evidence": "必ず"}
    assert llm_classify.validate(SENTENCE, payload) is None


def test_evidence_that_is_not_in_the_original_is_dropped() -> None:
    """根拠が原文に無ければ捨てる。

    標準書に無い語を持ち込ませないための検証 (必須原則 1)。要約や言い換えを
    根拠として返してきた場合はここで落ちる。
    """
    payload = {"is_rule": True, "rule_type": "Mandatory", "evidence": "義務付けられている"}
    assert llm_classify.validate(SENTENCE, payload) is None


def test_evidence_is_compared_ignoring_spaces() -> None:
    """空白の違いだけで捨てない。"""
    payload = {"is_rule": True, "rule_type": "Mandatory", "evidence": "要件 ID"}
    assert llm_classify.validate(SENTENCE, payload) == ("Mandatory", "要件 ID")


def test_an_unknown_rule_type_is_dropped() -> None:
    """規範レベルが選択肢に無ければ捨てる。"""
    payload = {"is_rule": True, "rule_type": "Obligatory", "evidence": "必ず"}
    assert llm_classify.validate(SENTENCE, payload) is None


def test_reference_is_not_offered_as_a_choice() -> None:
    """Reference は「規定ではない」と同義なので選択肢に入れない。"""
    assert "Reference" not in llm_classify.ALLOWED_RULE_TYPES


def test_only_reasonable_lengths_are_sent() -> None:
    """短すぎる / 長すぎる行は問い合わせない。"""
    assert not llm_classify.is_candidate("あ")
    assert llm_classify.is_candidate(SENTENCE)
    assert not llm_classify.is_candidate("あ" * 300)


def test_the_assist_is_off_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """無効化されていれば、資格情報の有無にかかわらず None。"""
    assert llm_classify.build_assist(False, None) is None

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert llm_classify.build_assist(True, None) is None


# --- パイプラインへの組み込み -------------------------------------------------


class _FakeAssist:
    """Claude を呼ばずに、決められた答えを返す補助。"""

    def __init__(self, answers: dict[str, tuple[str, str]]):
        self.answers = answers
        self.asked: list[str] = []

    def classify(self, sentence: str):
        self.asked.append(sentence)
        return self.answers.get(sentence)


HEADER = ["No.", "設計対象", "記述ルール", "サンプル", "備考"]
ROWS = [
    [1, "機能概要", "要件IDを必ず紐付ける", "受注登録：顧客注文を登録", ""],
    [2, "機能一覧", "1機能1責務を原則", "F-ORD-001 受注登録", ""],
]


def _workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "基本設計標準"
    ws.append(HEADER)
    for row in ROWS:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _located():
    return assign_structure(parse_document("標準.xlsx", _workbook()).blocks)


def test_without_the_assist_the_result_is_rule_based_only() -> None:
    """補助を渡さなければ従来どおり。規範表現を持つ行しか拾わない。"""
    rules = extract_rules(_located())
    assert [r.original_rule for r in rules] == ["1機能1責務を原則"]


def test_the_assist_recovers_a_rule_the_rules_missed() -> None:
    """ルールベースが落とした体言止めの規定を、判定補助が拾う。"""
    assist = _FakeAssist({"要件IDを必ず紐付ける": ("Mandatory", "必ず")})
    rules = extract_rules(_located(), assist)

    by_text = {r.original_rule: r for r in rules}
    assert set(by_text) == {"要件IDを必ず紐付ける", "1機能1責務を原則"}

    recovered = by_text["要件IDを必ず紐付ける"]
    assert recovered.rule_type == "Mandatory"
    # 来歴が残り、規定抽出一覧から判定の根拠を追える
    assert recovered.matched_markers == ["AI判定:必ず"]

    # ルールベースで判定できた行には問い合わせない
    assert "1機能1責務を原則" not in assist.asked


def test_the_assist_does_not_override_the_rule_based_result() -> None:
    """ルールベースが規定と判定した行は、補助の答えで上書きしない。"""
    assist = _FakeAssist({"1機能1責務を原則": ("Prohibited", "原則")})
    rules = extract_rules(_located(), assist)

    original = next(r for r in rules if r.original_rule == "1機能1責務を原則")
    assert original.rule_type == "Recommended"  # ルールベースの判定のまま


def test_an_example_row_stays_out() -> None:
    """補助が答えを返さない行は、これまでどおり規定にしない。"""
    assist = _FakeAssist({})
    rules = extract_rules(_located(), assist)
    assert [r.original_rule for r in rules] == ["1機能1責務を原則"]
