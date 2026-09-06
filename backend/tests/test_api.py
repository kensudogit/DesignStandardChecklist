"""API の結合テスト。アップロード → 解析 → レビュー記入 → 出力までを通す。"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "画面設計標準.md"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(type(settings), "storage_path", property(lambda self: tmp_path))

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload(client: TestClient, **form: str) -> dict:
    payload = {"document_type": "screen", "document_name": "画面設計標準", **form}
    response = client.post(
        "/api/documents",
        files={"file": (SAMPLE.name, SAMPLE.read_bytes(), "text/markdown")},
        data=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_meta(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert {"screen", "database", "api"} <= {d["value"] for d in meta["document_types"]}
    assert meta["result_values"] == ["OK", "NG", "N/A", "Pending"]


def test_upload_analyzes_and_assigns_ids(client: TestClient) -> None:
    doc = _upload(client)
    assert doc["status"] == "analyzed"
    assert doc["id_prefix"] == "UI"
    assert doc["rule_count"] > 20
    assert doc["check_count"] > doc["rule_count"] * 0.9
    # Markdown はページ番号を持たない
    assert doc["has_page_numbers"] is False

    rules = client.get(f"/api/documents/{doc['id']}/rules").json()
    assert rules[0]["standard_id"] == "STD-UI-001"
    assert all(r["standard_id"].startswith("STD-UI-") for r in rules)

    checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    assert checks[0]["check_id"] == "CHK-UI-001"
    assert all(c["check_point"].endswith("か？") for c in checks)
    # STEP 12: すべてのチェックが規定IDへ辿れる
    assert all(c["standard_id"] for c in checks)


def test_unknown_metadata_defaults_to_unknown(client: TestClient) -> None:
    """STEP 1: 不明な項目は「不明」とする。"""
    doc = _upload(client)
    assert doc["version"] == "不明"
    assert doc["established_date"] == "不明"


def test_coverage_targets_mandatory_and_prohibited(client: TestClient) -> None:
    doc = _upload(client)
    cov = client.get(f"/api/documents/{doc['id']}/coverage").json()
    assert cov["mandatory_coverage"] == 100.0
    assert cov["prohibited_coverage"] == 100.0
    assert cov["target_rules"] > 0
    assert cov["coverage"] == round(cov["converted_rules"] / cov["target_rules"] * 100, 1)
    assert cov["ambiguous_rules"] >= 1  # 「適切な粒度」「必要に応じて」
    assert any("曖昧" in f for f in cov["findings"])


def test_review_result_can_be_recorded(client: TestClient) -> None:
    doc = _upload(client)
    checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    target = checks[0]

    updated = client.patch(
        f"/api/documents/{doc['id']}/checklist/{target['id']}",
        json={"result": "NG", "comment": "項目IDが未定義", "reviewer": "山田"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["result"] == "NG"
    assert body["reviewer"] == "山田"

    progress = client.get(f"/api/documents/{doc['id']}/progress").json()
    assert progress["ng"] == 1
    assert progress["pending"] == progress["total"] - 1


def test_reanalysis_preserves_review_state(client: TestClient) -> None:
    doc = _upload(client)
    checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    client.patch(
        f"/api/documents/{doc['id']}/checklist/{checks[0]['id']}",
        json={"result": "OK", "evidence": "設計書 3.2 節"},
    )

    assert client.post(f"/api/documents/{doc['id']}/analyze").status_code == 200

    after = client.get(f"/api/documents/{doc['id']}/checklist").json()
    same = next(c for c in after if c["check_id"] == checks[0]["check_id"])
    assert same["result"] == "OK"
    assert same["evidence"] == "設計書 3.2 節"


def test_traceability_rows_have_sources(client: TestClient) -> None:
    doc = _upload(client)
    rows = client.get(f"/api/documents/{doc['id']}/traceability").json()
    assert rows
    for row in rows:
        assert row["check_id"].startswith("CHK-UI-")
        assert row["standard_id"].startswith("STD-UI-")
        assert row["source_document"] == "画面設計標準"
        # ページ番号を取得できない形式では「不明」であり、推測値を入れない
        assert row["page"] == "不明"


def test_export_artifacts(client: TestClient) -> None:
    doc = _upload(client)
    base = f"/api/documents/{doc['id']}/export"

    checklist = client.get(f"{base}/design-review-checklist")
    assert checklist.status_code == 200
    text = checklist.content.decode("utf-8")
    assert text.startswith("﻿")  # Excel 用 BOM
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][:6] == ["No", "Check ID", "Category", "Sub Category", "Check Point", "Severity"]
    assert len(rows) - 1 == doc["check_count"]

    coverage_md = client.get(f"{base}/coverage-report").content.decode("utf-8")
    assert "# Coverage Report" in coverage_md
    assert "Coverage = Converted target rules / Total target rules * 100" in coverage_md

    bundle = client.get(base)
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        names = set(zf.namelist())
    assert {
        "standard-register.csv",
        "extracted-rules.csv",
        "design-review-checklist.csv",
        "traceability-matrix.csv",
        "unconverted-rules.csv",
        "coverage-report.md",
    } <= names


def test_unsupported_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("standard.doc", b"dummy", "application/msword")},
        data={"document_type": "screen"},
    )
    assert response.status_code == 400
    assert "未対応" in response.json()["detail"]


def test_document_can_be_deleted(client: TestClient) -> None:
    doc = _upload(client)
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404


def test_atomic_siblings_are_not_flagged_as_duplicates(client: TestClient) -> None:
    """同一規定の Atomic Check 兄弟は別々の確認事項なので重複候補にしない (STEP 11)。"""
    doc = _upload(client)
    checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    by_standard: dict[str, list[dict]] = {}
    for check in checks:
        by_standard.setdefault(check["standard_id"], []).append(check)

    siblings = [group for group in by_standard.values() if len(group) > 1]
    assert siblings, "分解された規定が1件も無い"
    for group in siblings:
        ids = {c["check_id"] for c in group}
        for check in group:
            flagged = {s.split(" ")[0] for s in check["similar_check_ids"]}
            assert not (flagged & ids), f"{check['check_id']} が兄弟を重複候補にしている"


def test_coverage_report_includes_rule_type_table_and_findings(client: TestClient) -> None:
    """Coverage レポートは規範レベル別の内訳と Findings を含む (STEP 13/14)。"""
    doc = _upload(client)
    md = client.get(
        f"/api/documents/{doc['id']}/export/coverage-report"
    ).content.decode("utf-8")
    assert "| Rule Type | Total | Converted | Unconverted | Coverage |" in md
    assert "| Mandatory |" in md
    assert "| Prohibited |" in md
    # Findings に地の文の指摘が入っている (曖昧表現の指摘など)
    assert "曖昧" in md


def test_document_ids_are_issued_in_order(client: TestClient) -> None:
    """標準書IDは登録順に払い出される。"""
    ids = [_upload(client)["document_id"] for _ in range(3)]
    assert ids == ["DOC-001", "DOC-002", "DOC-003"]


def test_document_id_is_not_reused_after_deletion(client: TestClient) -> None:
    """削除しても採番は巻き戻らない。

    巻き戻ると、既に出力済みの成果物が指すIDを別の標準書が名乗ることになり、
    トレーサビリティが崩れる。最新を消しても、途中を消しても前進すること。
    """
    first = _upload(client)
    second = _upload(client)
    third = _upload(client)
    issued = {first["document_id"], second["document_id"], third["document_id"]}

    # 最新を削除しても、その番号は二度と払い出さない
    assert client.delete(f"/api/documents/{third['id']}").status_code == 204
    fourth = _upload(client)
    assert fourth["document_id"] == "DOC-004"
    assert fourth["document_id"] not in issued

    # 全件削除しても同じ
    for doc_id in (first["id"], second["id"], fourth["id"]):
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert _upload(client)["document_id"] == "DOC-005"


def test_document_id_counter_starts_from_existing_documents(client: TestClient) -> None:
    """カウンタを持たない既存DBを引き継いだ場合は、現存する最大から続ける。

    この仕組みより前に作られたDBには id_sequences の行が無い。そのまま 1 から
    払い出すと既存の標準書と衝突するため、最大値から再開する必要がある。
    """
    from app.models import IdSequence

    _upload(client)
    _upload(client)

    # 移行前の状態を再現する (カウンタ行だけを消す)。
    # セッションはフィクスチャが差し替えた get_db から借りる。
    session = app.dependency_overrides[get_db]()
    db = next(session)
    try:
        row = db.get(IdSequence, "document_id")
        assert row is not None
        db.delete(row)
        db.commit()
    finally:
        session.close()

    assert _upload(client)["document_id"] == "DOC-003"


def test_upload_recovers_when_the_document_id_was_taken(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """採番が既存と衝突しても、番号を採り直して登録できる。

    同時にアップロードすると、両者が「既存の最大 + 1」を読んで同じ番号を採りうる。
    先に書いた側が通り、後から書いた側は一意制約に弾かれる状況を再現する。
    """
    from app.api import documents as documents_api

    first = _upload(client)

    real = documents_api.next_document_id
    calls: list[str] = []

    def collide_once(db: object) -> str:
        # 1回目だけ、既に使われている番号を返す
        value = first["document_id"] if not calls else real(db)
        calls.append(value)
        return value

    monkeypatch.setattr(documents_api, "next_document_id", collide_once)

    second = _upload(client)
    assert calls[0] == first["document_id"]  # 衝突させた
    assert len(calls) >= 2  # 採り直した
    assert second["document_id"] != first["document_id"]


def test_root_points_to_the_api_docs(client: TestClient) -> None:
    """バックエンドのポートをブラウザで開いたとき、行き先が分かること。

    ルートを定義しないと素の {"detail":"Not Found"} が返るだけになる。
    """
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"

    assert client.get("/docs").status_code == 200
