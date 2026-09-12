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


# --- 分類の割り当て -----------------------------------------------------------


def test_a_category_outside_the_list_is_dropped() -> None:
    """選択肢に無い分類が返ってきたら使わない。"""
    from app.core.llm_classify import CATEGORY_NAMES

    assert "例外処理" in CATEGORY_NAMES
    assert "構造" not in CATEGORY_NAMES  # 標準書が書いていても選択肢にはならない


class _FakeCategorizer:
    """Claude を呼ばずに分類だけ返す補助。"""

    def __init__(self, answer: str | None):
        self.answer = answer
        self.asked: list[tuple[str, str | None]] = []

    def classify(self, sentence: str):
        return None

    def categorize(self, sentence: str, hint: str | None):
        self.asked.append((sentence, hint))
        return self.answer


def test_the_assist_is_asked_only_when_the_vocabulary_misses() -> None:
    """語彙一致で決まる分類は Claude に尋ねない。"""
    from app.core.extractor import _category_for
    from app.core.structure import Located

    item = Located(
        text="", page=None, chapter=None, section=None, heading_path="",
        is_table=True, locator=None, order=0, category_hint="セキュリティ",
    )
    assist = _FakeCategorizer("ログ")
    assert _category_for("認証方式を定義すること", item, assist) == "セキュリティ"
    assert assist.asked == []


def test_the_assist_fills_in_a_category_the_vocabulary_lacks() -> None:
    """語彙表に無い分類名 (「例外」) を橋渡しする。"""
    from app.core.extractor import _category_for
    from app.core.structure import Located

    item = Located(
        text="", page=None, chapter=None, section=None, heading_path="",
        is_table=True, locator=None, order=0, category_hint="例外",
    )
    assist = _FakeCategorizer("例外処理")
    assert _category_for("握りつぶさない", item, assist) == "例外処理"
    assert assist.asked == [("握りつぶさない", "例外")]


def test_the_default_is_used_when_the_assist_gives_nothing() -> None:
    """補助が答えなければ既定値。従来の動作に戻る。"""
    from app.core import taxonomy as tx
    from app.core.extractor import _category_for
    from app.core.structure import Located

    item = Located(
        text="", page=None, chapter=None, section=None, heading_path="",
        is_table=True, locator=None, order=0, category_hint="構造",
    )
    assert _category_for("握りつぶさない", item, _FakeCategorizer(None)) == tx.DEFAULT_CATEGORY
    assert _category_for("握りつぶさない", item, None) == tx.DEFAULT_CATEGORY


# --- 列の役割判定 -------------------------------------------------------------


#: 語彙表に無い見出しだけで作った表。組織ごとの言い回しを想定する。
UNKNOWN_HEADER = ["通し", "大分類", "記載事項", "強制度", "レベル区分", "良い例", "悪い例"]
UNKNOWN_ROWS = [
    ["1", "セキュリティ", "パスワードは平文で保存してはならない", "必須", "重大", "ハッシュ化", "平文DB保存"],
]


class _FakeColumns:
    """Claude を呼ばずに列の役割だけ返す補助。"""

    def __init__(self, roles):
        self.roles = roles
        self.asked: list[list[str]] = []

    def column_roles(self, header):
        self.asked.append(list(header))
        return self.roles


def _unknown_workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "コーディング標準"
    ws.append(UNKNOWN_HEADER)
    for row in UNKNOWN_ROWS:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_an_unknown_header_falls_back_to_joining_the_row() -> None:
    """補助が無ければ従来どおり。行全体が1ブロックになる。"""
    blocks = parse_document("標準.xlsx", _unknown_workbook()).blocks
    assert any(" / " in b.text for b in blocks)


def test_the_assist_makes_an_unknown_header_usable() -> None:
    """語彙表に無い見出しでも、列の役割が分かれば規定本文だけを取り出せる。"""
    roles = {0: "no", 1: "category", 2: "rule", 3: "rule_type", 4: "severity"}
    assist = _FakeColumns(roles)

    blocks = parse_document("標準.xlsx", _unknown_workbook(), assist).blocks
    body = [b for b in blocks if b.is_table]
    assert len(body) == 1
    assert body[0].text == "パスワードは平文で保存してはならない"  # 行の連結ではない
    assert body[0].category_hint == "セキュリティ"
    assert body[0].severity_hint == "Critical"  # レベル区分「重大」
    assert body[0].rule_type_hint == "Mandatory"  # 強制度「必須」
    # 「良い例」「悪い例」は取り込まれない
    assert "ハッシュ化" not in body[0].text


def test_a_known_header_does_not_reach_the_assist() -> None:
    """語彙一致で読める表は Claude に尋ねない。"""
    assist = _FakeColumns({0: "rule"})
    parse_document("標準.xlsx", _two_table_bytes(), assist)
    assert assist.asked == []


def _two_table_bytes() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "標準"
    ws.append(["No", "章", "節", "分類", "規定内容", "区分", "重要度", "備考"])
    ws.append([1, 2, "2.1", "認証", "認証方式を定義すること", "必須", "高", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_a_result_without_a_rule_column_is_dropped() -> None:
    """規定本文の列が定まらない答えは使わない。表の意味を読み違えるため。"""
    assist = _FakeColumns({0: "no", 1: "category"})  # rule が無い
    blocks = parse_document("標準.xlsx", _unknown_workbook(), assist).blocks
    # 従来どおり行を連結した扱いに戻る
    assert any(" / " in b.text for b in blocks)
