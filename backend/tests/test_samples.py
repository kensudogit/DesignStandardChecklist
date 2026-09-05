"""samples/ の標準書サンプルが、どれも最後まで変換できることを確認する。

文書種別ごとに文体も章立ても違うため、ここは「壊れないこと」を広く見る場所にする。
変換の中身が正しいかは eval/ の正解データで測る (tests/test_eval_baseline.py)。

サンプルを追加したら EXPECTED_DOC_TYPE に1行足すこと。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.extractor import extract_rules
from app.core.parsers import SUPPORTED_EXTENSIONS, parse_document
from app.core.pipeline import checks_for_rule, suggest_document_type
from app.core.structure import assign_structure

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"

#: ファイル名から推定されるべき文書種別 (STEP 1)
EXPECTED_DOC_TYPE = {
    "API設計標準.xlsx": "api",
    "DB設計標準.md": "database",
    "コーディング標準.md": "coding",
    "セキュリティ設計標準.md": "security",
    "テスト設計標準.md": "test",
    "バッチ設計標準.md": "batch",
    "基本設計標準.md": "basic",
    "外部IF設計標準.md": "interface",
    "帳票設計標準.docx": "report",
    "画面設計標準.md": "screen",
    "詳細設計標準.md": "detail",
}

#: 先頭がこれらの助詞で始まる確認事項は、分解で前半を失っている
LEADING_PARTICLES = ("に", "を", "が", "と", "の", "は", "へ", "で", "も")

SAMPLE_FILES = sorted(p.name for p in SAMPLES_DIR.iterdir() if p.is_file())


def _convert(path: Path):
    parsed = parse_document(path.name, path.read_bytes())
    rules = extract_rules(assign_structure(parsed.blocks))
    converted = [(rule, *checks_for_rule(rule)) for rule in rules]
    return rules, converted


def test_samples_dir_is_not_empty():
    assert SAMPLE_FILES, "samples/ にファイルがありません"


def test_every_sample_is_registered():
    """サンプルを足したら期待値も足す (テストが素通りするのを防ぐ)。"""
    assert set(SAMPLE_FILES) == set(EXPECTED_DOC_TYPE)


def test_all_document_types_have_a_sample():
    """SKILL.md の文書種別が一通りサンプルで試せること ("other" は種別なしの受け皿)。"""
    from app.core import taxonomy as tx

    covered = set(EXPECTED_DOC_TYPE.values())
    missing = sorted(set(tx.DOC_TYPE_PREFIX) - covered - {"other"})
    assert not missing, f"サンプルの無い文書種別: {missing}"


def test_multiple_input_formats_are_covered():
    """Markdown だけでなく Word / Excel のサンプルもあること。"""
    extensions = {Path(name).suffix.lower() for name in SAMPLE_FILES}
    assert {".md", ".docx", ".xlsx"} <= extensions
    assert extensions <= SUPPORTED_EXTENSIONS


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_document_type_is_inferred_from_filename(name):
    assert suggest_document_type(name) == EXPECTED_DOC_TYPE[name]


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_converts_end_to_end(name):
    rules, converted = _convert(SAMPLES_DIR / name)

    assert len(rules) >= 10, f"{name}: 規定が少なすぎる ({len(rules)}件)"
    for rule in rules:
        assert rule.original_rule.strip(), f"{name}: 原文が空の規定がある"
        assert rule.normalized_requirement.strip(), f"{name}: {rule.original_rule} の要求事項が空"

    checks = [check for _, items, _ in converted for check in items]
    assert len(checks) >= len(rules), f"{name}: チェック項目が規定数を下回っている"


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_check_points_are_answerable(name):
    """すべての確認事項が Yes/No/N/A で答えられる形になっていること (必須原則 10)。"""
    _, converted = _convert(SAMPLES_DIR / name)
    for rule, items, _ in converted:
        for check in items:
            point = check.check_point
            assert point.endswith("か？"), f"{name}: 疑問文になっていない -> {point}"
            assert len(point) >= 10, f"{name}: 短すぎて判定できない -> {point}"
            assert not point.startswith(LEADING_PARTICLES), (
                f"{name}: 助詞で始まっており分解で前半を失っている -> {point}"
                f" (規定: {rule.original_rule})"
            )


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_mandatory_rules_are_all_converted(name):
    """必須・禁止・条件付き必須は Coverage 100% が目標 (STEP 13)。"""
    from app.core import taxonomy as tx

    _, converted = _convert(SAMPLES_DIR / name)
    unconverted = [
        (rule.original_rule, reason)
        for rule, _, reason in converted
        if reason is not None and rule.rule_type in tx.CRITICAL_COVERAGE_TYPES
    ]
    assert not unconverted, f"{name}: 変換できなかった必須/禁止規定がある -> {unconverted}"


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_conditions_and_exceptions_survive(name):
    """条件・例外を持つ規定は、その情報がチェック項目まで残ること (必須原則 5/6)。"""
    _, converted = _convert(SAMPLES_DIR / name)
    for rule, items, reason in converted:
        if reason is not None:
            continue
        if rule.exception:
            assert any(rule.exception in (c.exception or "") for c in items), (
                f"{name}: 例外が落ちている -> {rule.original_rule}"
            )
        if rule.condition:
            assert any(c.condition for c in items), (
                f"{name}: 条件が落ちている -> {rule.original_rule}"
            )
