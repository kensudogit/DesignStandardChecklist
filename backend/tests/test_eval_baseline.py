"""変換精度が baseline から落ちていないことを確認する。

eval/gold/ の正解データと突き合わせた結果を eval/baseline.json と比べる。
STEP 3-7 のロジック (taxonomy / extractor / atomizer) を触ると、テストの数は変わらないのに
チェックリストの中身だけが静かに悪化することがある。ここで止める。

精度を上げたときは baseline を更新する:
    python -m eval.runner --update-baseline
"""

from __future__ import annotations

import json

import pytest

from eval.gold import load_gold_sets
from eval.runner import (
    BASELINE_PATH,
    GOLD_DIR,
    REPO_ROOT,
    build_report,
    compare_baseline,
)


@pytest.fixture(scope="module")
def report():
    return build_report()


def test_gold_itself_is_consistent(report):
    """正解データ側の不備 (ID重複、存在しない参照など) が無いこと。"""
    assert report.gold_problems == []


def test_all_gold_sets_are_evaluated():
    """manifest に並べた標準書がすべて評価対象になっていること。"""
    gold_sets = load_gold_sets(GOLD_DIR, REPO_ROOT)
    assert len(gold_sets) >= 5
    for gold in gold_sets:
        assert gold.rules, f"{gold.name}: 規定の正解が空"
        assert gold.checks, f"{gold.name}: 確認事項の正解が空"


def test_no_regression_against_baseline(report):
    """baseline.json のどの指標も下がっていないこと。"""
    assert BASELINE_PATH.exists(), "baseline.json がありません (--update-baseline で作成)"
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    regressions = compare_baseline(report, baseline)
    assert not regressions, "変換精度が baseline から悪化しています:\n  " + "\n  ".join(regressions)


def test_extraction_stays_lossless(report):
    """標準書に書いてある規定を取りこぼさない (必須原則 1 の裏返し)。

    誤抽出 0 は「標準書に無い規定を作らない」の確認でもあるので、率ではなく件数で見る。
    """
    total = report.total
    assert total.rule.fp == 0, "標準書に無い規定を抽出している"
    assert total.rule.recall >= 0.95
