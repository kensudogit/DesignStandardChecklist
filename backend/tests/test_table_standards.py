"""表形式（Excel）の標準書と、規範表現の語彙。

実務の標準書は「No / 章 / 節 / 分類 / 規定内容 / 区分 / 重要度」のような表であることが多い。
行を連結してしまうと規定文が壊れ、標準書自身が持つ章・節・区分・重要度も失われる。
"""

from __future__ import annotations

import io

import pytest

from app.core.atomizer import atomize, to_question
from app.core.extractor import classify_rule_type, extract_rules, normalize_requirement
from app.core.parsers import parse_document
from app.core.parsers.table_schema import detect_schema, map_rule_type, map_severity
from app.core.structure import assign_structure

HEADER = ["No", "章", "節", "分類", "規定内容", "区分", "重要度", "備考"]

ROWS = [
    [1, 2, "2.1", "エンドポイント", "エンドポイントはリソース名を複数形で表現すること", "必須", "中", ""],
    [2, 2, "2.1", "エンドポイント", "エンドポイントのパスに動詞を含めてはならない", "禁止", "中", ""],
    [3, 3, "3.1", "リクエスト", "リクエストパラメータの型、桁数、必須有無を定義すること", "必須", "高", ""],
    [4, 4, "4.1", "エラー応答", "エラー応答にはエラーコードとメッセージを含めること", "必須", "高", "要確認"],
    [5, 5, "5.1", "認証", "APIの認証方式を定義すること", "必須", "重大", ""],
    [6, 7, "7.1", "バージョニング", "APIのバージョンはパスに含めることを推奨する", "推奨", "低", ""],
]


def _workbook(header: list[str], rows: list[list], title: str = "API設計標準") -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(["改訂履歴: 2025-08-01 第1.2版"])
    ws.append([])
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _rules(data: bytes):
    parsed = parse_document("標準.xlsx", data)
    return parsed, extract_rules(assign_structure(parsed.blocks))


# --- ヘッダ判定 ---------------------------------------------------------------


def test_header_row_is_detected_below_a_revision_note() -> None:
    rows = [["改訂履歴: 2025-08-01"], [], HEADER, ["1", "2", "2.1", "x", "y", "必須", "高", ""]]
    detected = detect_schema([[str(c) for c in r] for r in rows])
    assert detected is not None
    index, schema = detected
    assert index == 2
    assert schema.column_of("rule") == 4
    assert schema.column_of("chapter") == 1
    assert schema.column_of("section") == 2
    assert schema.column_of("severity") == 6


def test_header_without_a_rule_column_is_not_used() -> None:
    """規定内容の列が特定できない表は、意味を読み違えるので構造化しない。"""
    rows = [["No", "章", "節", "担当", "期限"], ["1", "2", "2.1", "山田", "2025-09-01"]]
    assert detect_schema(rows) is None


def test_value_mappings() -> None:
    assert map_rule_type("必須") == "Mandatory"
    assert map_rule_type("禁止") == "Prohibited"
    assert map_rule_type("条件付き必須") == "Conditional Mandatory"
    assert map_rule_type("推奨") == "Recommended"
    assert map_rule_type("任意") == "Optional"
    assert map_rule_type("") is None
    assert map_severity("重大") == "Critical"
    assert map_severity("高") == "High"
    assert map_severity("中") == "Medium"
    assert map_severity("低") == "Low"
    assert map_severity("") is None


# --- 表形式の標準書 -----------------------------------------------------------


def test_rule_text_is_isolated_from_the_row() -> None:
    """行全体ではなく「規定内容」列だけを規定文として扱う。"""
    parsed, rules = _rules(_workbook(HEADER, ROWS))
    assert parsed.meta["structured_sheets"] == "1"
    assert len(rules) == len(ROWS)
    for rule in rules:
        assert " / " not in rule.original_rule
        assert not rule.original_rule.startswith(("1", "2", "3"))


def test_chapter_and_section_come_from_their_columns() -> None:
    _, rules = _rules(_workbook(HEADER, ROWS))
    first = rules[0]
    assert first.chapter == "2"
    assert first.section == "2.1"
    assert rules[4].chapter == "5"
    assert rules[4].section == "5.1"
    # Excel にページ番号は無い。所在はシート名と行番号で残す。
    assert first.page is None
    assert first.locator is not None and "行" in first.locator


def test_rule_type_column_is_honoured() -> None:
    _, rules = _rules(_workbook(HEADER, ROWS))
    by_text = {r.original_rule: r for r in rules}
    assert by_text["APIのバージョンはパスに含めることを推奨する"].rule_type == "Recommended"
    assert by_text["エンドポイントのパスに動詞を含めてはならない"].rule_type == "Prohibited"


def test_prohibition_in_the_text_wins_over_the_column() -> None:
    """必須原則 7: 区分列が「必須」でも、本文が禁止表現なら禁止を取りこぼさない。"""
    rows = [[1, 5, "5.1", "ログ", "パスワードをログへ出力してはならない", "必須", "重大", ""]]
    _, rules = _rules(_workbook(HEADER, rows))
    assert rules[0].rule_type == "Prohibited"


def test_severity_column_overrides_keyword_inference() -> None:
    """STEP 10: 標準書に重要度の定義がある場合は標準書を優先する。"""
    from app.core.severity import decide_severity

    _, rules = _rules(_workbook(HEADER, ROWS))
    auth = next(r for r in rules if "認証方式" in r.original_rule)
    assert auth.explicit_severity == "Critical"

    versioning = next(r for r in rules if "バージョン" in r.original_rule)
    assert versioning.explicit_severity == "Low"
    severity, reason = decide_severity(
        text=versioning.original_rule,
        category=versioning.category,
        rule_type=versioning.rule_type,
        explicit_severity=versioning.explicit_severity,
    )
    assert severity == "Low"
    assert "標準書" in reason


def test_category_column_beats_the_document_title() -> None:
    """分類は「分類」列が最優先。文書名が全行の分類を潰さないこと。"""
    _, rules = _rules(_workbook(HEADER, ROWS))
    by_text = {r.original_rule: r for r in rules}
    assert by_text["APIの認証方式を定義すること"].category == "セキュリティ"
    assert by_text["エラー応答にはエラーコードとメッセージを含めること"].category == "エラー処理"


def test_note_column_is_kept() -> None:
    _, rules = _rules(_workbook(HEADER, ROWS))
    noted = next(r for r in rules if "エラーコード" in r.original_rule)
    assert noted.notes == "要確認"


def test_enumeration_in_a_table_row_is_split() -> None:
    _, rules = _rules(_workbook(HEADER, ROWS))
    request_rule = next(r for r in rules if "リクエストパラメータ" in r.original_rule)
    checks = atomize(request_rule)
    assert len(checks) == 3
    points = " ".join(c.check_point for c in checks)
    for token in ("型", "桁数", "必須有無"):
        assert token in points


def test_sheet_without_a_header_falls_back_to_joined_rows() -> None:
    rows = [["画面IDを付与すること"], ["項目IDを付与すること"]]
    parsed, rules = _rules(_workbook(["メモ"], rows, title="雑記"))
    assert parsed.meta["structured_sheets"] == "0"
    assert len(rules) == 2


# --- 規範表現の語彙 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("本標準を遵守すること。", "Mandatory"),
        ("命名規則に従うこと。", "Mandatory"),
        ("設計書のレビューが必要である。", "Mandatory"),
        ("単体テストの実施を要する。", "Mandatory"),
        ("冗長なコードは避けること。", "Prohibited"),
        ("同一処理の重複実装は認めない。", "Prohibited"),
        ("認証情報を共有すべきではない。", "Prohibited"),
        ("ハードコードは許容しない。", "Prohibited"),
        ("ログ出力はDEBUGレベルとすべきである。", "Recommended"),
        ("共通部品の利用を基本とする。", "Recommended"),
        ("原則としてSQLは静的とする。", "Recommended"),
    ],
)
def test_expanded_vocabulary(sentence: str, expected: str) -> None:
    assert classify_rule_type(sentence)[0] == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("エラー応答にはエラーコードとメッセージを含めること", "エラー応答にはエラーコードとメッセージを含めているか？"),
        ("入力項目にはラベルを関連付けること", "入力項目にはラベルを関連付けているか？"),
        ("項目の初期値を定めること", "項目の初期値を定めているか？"),
        ("ログは日次で退避を行うこと", "ログは日次で退避を行っているか？"),
        # 五段動詞は活用せず、どの動詞でも成立する形にする
        ("命名規則を守ること", "命名規則を守ることとしているか？"),
        ("設計書の承認を得ること", "設計書の承認を得ることとしているか？"),
    ],
)
def test_ichidan_and_godan_conjugation(sentence: str, expected: str) -> None:
    assert to_question(normalize_requirement(sentence, "Mandatory")) == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("パスワードをログへ出力してはならない", "パスワードをログへ出力しない設計になっているか？"),
        ("色のみで情報を区別する設計としてはならない", "色のみで情報を区別する設計としないこととしているか？"),
        ("パスをURLに含めてはならない", "パスをURLに含めない設計になっているか？"),
        ("認証情報を共有すべきではない", "認証情報を共有することがない設計になっているか？"),
        ("例外を握りつぶすべきではない", "例外を握りつぶすことがない設計になっているか？"),
        ("冗長なコードは避けること", "冗長なコードを避けた設計になっているか？"),
        ("動的SQLの使用は禁止する", "動的SQLの使用を行わない設計になっているか？"),
    ],
)
def test_prohibited_phrasing_is_grammatical(sentence: str, expected: str) -> None:
    assert to_question(normalize_requirement(sentence, "Prohibited")) == expected


def test_table_metadata_survives_the_full_pipeline(tmp_path) -> None:
    """章・節・区分・重要度・備考が、解析パイプラインを通ってチェックリストまで届く。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.pipeline import analyze_document
    from app.db import Base
    from app.models import ChecklistItem, Rule, StandardDocument

    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    path = tmp_path / "API設計標準.xlsx"
    path.write_bytes(_workbook(HEADER, ROWS))

    document = StandardDocument(
        document_id="DOC-001",
        document_name="API設計標準",
        document_type="api",
        id_prefix="API",
        original_filename=path.name,
        stored_path=str(path),
        file_format="xlsx",
    )
    db.add(document)
    db.commit()

    analyze_document(db, document)

    rules = {r.original_rule: r for r in db.query(Rule).all()}
    auth = rules["APIの認証方式を定義すること"]
    assert auth.chapter == "5" and auth.section == "5.1"
    assert auth.explicit_severity == "Critical"
    assert rules["エラー応答にはエラーコードとメッセージを含めること"].notes == "要確認"

    items = {i.check_point: i for i in db.query(ChecklistItem).all()}
    auth_check = next(i for p, i in items.items() if "認証方式" in p)
    assert auth_check.severity == "Critical"
    assert "標準書" in auth_check.severity_reason
    db.close()
