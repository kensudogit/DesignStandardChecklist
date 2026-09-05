"""統合レビュー表（複数標準書の横断チェックリスト）の結合テスト。

SKILL.md 10.「画面設計標準と詳細設計標準を横断してレビュー表を作って」の
実行手順1〜6をそのまま検証する。
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_api import client  # noqa: F401  (fixture)

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _upload(client: TestClient, filename: str, document_type: str, name: str) -> dict:
    path = SAMPLES / filename
    response = client.post(
        "/api/documents",
        files={"file": (path.name, path.read_bytes(), "text/markdown")},
        data={"document_type": document_type, "document_name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _two_documents(client: TestClient) -> tuple[dict, dict]:
    screen = _upload(client, "画面設計標準.md", "screen", "画面設計標準")
    detail = _upload(client, "詳細設計標準.md", "detail", "詳細設計標準")
    return screen, detail


def _create_set(client: TestClient, *documents: dict, name: str = "横断レビュー表") -> dict:
    response = client.post(
        "/api/review-sets",
        json={"name": name, "document_ids": [d["id"] for d in documents]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_rule_ids_stay_per_document_type(client: TestClient) -> None:
    """実行手順2: 規定IDは文書種別ごとに付与する（統合しても振り直さない）。"""
    screen, detail = _two_documents(client)
    assert screen["id_prefix"] == "UI"
    assert detail["id_prefix"] == "DD"

    _create_set(client, screen, detail)

    screen_rules = client.get(f"/api/documents/{screen['id']}/rules").json()
    detail_rules = client.get(f"/api/documents/{detail['id']}/rules").json()
    assert all(r["standard_id"].startswith("STD-UI-") for r in screen_rules)
    assert all(r["standard_id"].startswith("STD-DD-") for r in detail_rules)


def test_consolidated_checklist_merges_cross_document_duplicates(client: TestClient) -> None:
    """実行手順3/4/5: 横断的に重複を統合し、複数出典を紐付ける。"""
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)

    assert review_set["merged_count"] > 0, "文書をまたぐ重複が検出されていない"
    assert review_set["check_count"] == screen["check_count"] + detail["check_count"] - review_set[
        "merged_count"
    ]

    rows = client.get(f"/api/review-sets/{review_set['id']}/checklist").json()
    merged_rows = [r for r in rows if r["merged_check_ids"]]
    assert merged_rows

    row = merged_rows[0]
    # 統合された行は複数の標準書を出典として保持する
    documents = {s["source_document"] for s in row["sources"]}
    assert len(documents) >= 2
    standard_ids = {s["standard_id"] for s in row["sources"]}
    assert any(s.startswith("STD-UI-") for s in standard_ids)
    assert any(s.startswith("STD-DD-") for s in standard_ids)


def test_consolidated_row_keeps_the_heaviest_severity(client: TestClient) -> None:
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)
    rows = client.get(f"/api/review-sets/{review_set['id']}/checklist").json()

    order = ["Critical", "High", "Medium", "Low"]
    by_check_id = {}
    for doc in (screen, detail):
        for item in client.get(f"/api/documents/{doc['id']}/checklist").json():
            by_check_id[item["check_id"]] = item["severity"]

    for row in rows:
        if not row["merged_check_ids"]:
            continue
        involved = [row["check_id"], *row["merged_check_ids"]]
        expected = min(
            (by_check_id[c] for c in involved if c in by_check_id),
            key=order.index,
        )
        assert row["severity"] == expected


def test_review_result_propagates_to_every_source_document(client: TestClient) -> None:
    """統合表で判定した結果は、統合元すべてに書き戻す（結果の食い違いを防ぐ）。"""
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)
    rows = client.get(f"/api/review-sets/{review_set['id']}/checklist").json()
    target = next(r for r in rows if r["merged_check_ids"])

    updated = client.patch(
        f"/api/review-sets/{review_set['id']}/checklist/{target['id']}",
        json={"result": "NG", "comment": "両標準で未対応", "reviewer": "佐藤"},
    )
    assert updated.status_code == 200
    assert updated.json()["result"] == "NG"

    involved = {target["check_id"], *target["merged_check_ids"]}
    seen = 0
    for doc in (screen, detail):
        for item in client.get(f"/api/documents/{doc['id']}/checklist").json():
            if item["check_id"] in involved:
                assert item["result"] == "NG"
                assert item["reviewer"] == "佐藤"
                seen += 1
    assert seen == len(involved)


def test_per_document_coverage_is_reported(client: TestClient) -> None:
    """実行手順6: 標準書別Coverageも算出する。"""
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)

    coverage = client.get(f"/api/review-sets/{review_set['id']}/coverage").json()
    assert len(coverage["by_document"]) == 2
    names = {row["document_name"] for row in coverage["by_document"]}
    assert names == {"画面設計標準", "詳細設計標準"}
    for row in coverage["by_document"]:
        assert row["mandatory_coverage"] == 100.0
        assert row["prohibited_coverage"] == 100.0

    assert coverage["consolidated_checks"] == review_set["check_count"]
    assert coverage["merged_checks"] == review_set["merged_count"]
    assert coverage["total_checks_before_merge"] == (
        coverage["consolidated_checks"] + coverage["merged_checks"]
    )
    assert any("統合" in f for f in coverage["findings"])


def test_single_document_review_set_merges_nothing(client: TestClient) -> None:
    screen, _ = _two_documents(client)
    review_set = _create_set(client, screen, name="画面のみ")
    assert review_set["merged_count"] == 0
    assert review_set["check_count"] == screen["check_count"]


def test_review_set_can_be_rebuilt_after_reanalysis(client: TestClient) -> None:
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)

    assert client.post(f"/api/documents/{screen['id']}/analyze").status_code == 200
    rebuilt = client.post(f"/api/review-sets/{review_set['id']}/consolidate")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["check_count"] == review_set["check_count"]

    rows = client.get(f"/api/review-sets/{review_set['id']}/checklist").json()
    assert len(rows) == review_set["check_count"]


def test_review_set_exports(client: TestClient) -> None:
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen, detail)
    base = f"/api/review-sets/{review_set['id']}/export"

    checklist = client.get(f"{base}/consolidated-checklist")
    assert checklist.status_code == 200
    text = checklist.content.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][:2] == ["No", "Check ID"]
    assert "Standard IDs" in rows[0] and "Source Documents" in rows[0]
    assert len(rows) - 1 == review_set["check_count"]
    # 統合行は複数の Standard ID を持つ
    assert any(";" in row[rows[0].index("Standard IDs")] for row in rows[1:])

    trace = client.get(f"{base}/cross-traceability-matrix").content.decode("utf-8")
    trace_rows = list(csv.reader(io.StringIO(trace.lstrip("﻿"))))
    # 出典ごとに1行なので、統合分だけチェックリストより行数が多い
    assert len(trace_rows) - 1 == review_set["check_count"] + review_set["merged_count"]
    assert "Primary" in trace and "Merged" in trace

    coverage_md = client.get(f"{base}/cross-coverage-report").content.decode("utf-8")
    assert "標準書別 Coverage" in coverage_md
    assert "画面設計標準" in coverage_md and "詳細設計標準" in coverage_md

    bundle = client.get(base)
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        names = set(zf.namelist())
    assert {
        "consolidated-checklist.csv",
        "consolidated-checklist.md",
        "cross-traceability-matrix.csv",
        "cross-coverage-report.md",
    } == names


def test_review_set_crud(client: TestClient) -> None:
    screen, detail = _two_documents(client)
    review_set = _create_set(client, screen)

    updated = client.patch(
        f"/api/review-sets/{review_set['id']}",
        json={"name": "画面+詳細", "document_ids": [screen["id"], detail["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "画面+詳細"
    assert len(updated.json()["documents"]) == 2

    assert client.delete(f"/api/review-sets/{review_set['id']}").status_code == 204
    assert client.get(f"/api/review-sets/{review_set['id']}").status_code == 404


def test_unknown_document_is_rejected(client: TestClient) -> None:
    response = client.post("/api/review-sets", json={"name": "x", "document_ids": [9999]})
    assert response.status_code == 400
    assert "標準書が見つかりません" in response.json()["detail"]
