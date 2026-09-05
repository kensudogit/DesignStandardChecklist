"""AI推奨事項。

検証の主眼は必須原則 8「AI推奨事項を追加する場合は、標準由来と明確に分離する」。
生成しても、チェックリスト・トレーサビリティ・Coverage が一切変わらないことを確かめる。
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import recommender
from app.core.recommender import RecommendationError
from tests.test_api import _upload, client  # noqa: F401  (fixture)

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _generate(client: TestClient, document_id: int, generator: str = "catalog") -> list[dict]:
    response = client.post(
        f"/api/documents/{document_id}/recommendations",
        json={"generator": generator, "replace": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_no_recommendations_until_requested(client: TestClient) -> None:
    """STEP 14-7: AI推奨事項は「要求された場合のみ」生成する。"""
    doc = _upload(client)
    assert client.get(f"/api/documents/{doc['id']}/recommendations").json() == []

    status = client.get(f"/api/documents/{doc['id']}/recommendations/status").json()
    assert status["count"] == 0
    assert "catalog" in status["generators_available"]
    assert "標準書由来ではありません" in status["note"]


def test_catalog_generator_proposes_only_uncovered_viewpoints(client: TestClient) -> None:
    doc = _upload(client)
    rows = _generate(client, doc["id"])
    assert rows, "観点カタログから1件も提案されていない"

    checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    covered = " ".join(c["check_point"] + c["original_rule"] for c in checks)

    for row in rows:
        assert row["recommendation_id"].startswith("REC-UI-")
        assert row["generator"] == "catalog"
        assert row["adoption"] == "Proposed"
        assert row["check_point"].endswith("か？")
        assert row["rationale"]
        # 標準書が既に触れている観点は提案しない
        assert row["sub_category"] not in covered


def test_screen_standard_lacks_no_layout_viewpoint(client: TestClient) -> None:
    """標準書が規定している観点は提案されない（画面設計標準はレイアウトを規定済み）。"""
    doc = _upload(client)
    rows = _generate(client, doc["id"])
    proposed = {r["sub_category"] for r in rows}
    for covered in ("項目ID", "画面遷移", "入力チェック", "アクセシビリティ"):
        assert covered not in proposed


def test_recommendations_do_not_leak_into_standard_artifacts(client: TestClient) -> None:
    """必須原則 8 の核心。生成前後でチェックリスト・Coverage・トレーサビリティが変わらない。"""
    doc = _upload(client)
    before_checks = client.get(f"/api/documents/{doc['id']}/checklist").json()
    before_coverage = client.get(f"/api/documents/{doc['id']}/coverage").json()
    before_trace = client.get(f"/api/documents/{doc['id']}/traceability").json()
    before_progress = client.get(f"/api/documents/{doc['id']}/progress").json()

    rows = _generate(client, doc["id"])
    assert rows

    assert client.get(f"/api/documents/{doc['id']}/checklist").json() == before_checks
    assert client.get(f"/api/documents/{doc['id']}/coverage").json() == before_coverage
    assert client.get(f"/api/documents/{doc['id']}/traceability").json() == before_trace
    assert client.get(f"/api/documents/{doc['id']}/progress").json() == before_progress

    # チェックリストCSVにも入らない
    csv_text = client.get(
        f"/api/documents/{doc['id']}/export/design-review-checklist"
    ).content.decode("utf-8")
    assert "REC-UI-" not in csv_text


def test_recommendations_have_no_fabricated_sources(client: TestClient) -> None:
    """禁止事項: 出典の捏造。標準書に無い提案に章・節・ページを与えない。"""
    doc = _upload(client)
    _generate(client, doc["id"])

    text = client.get(f"/api/documents/{doc['id']}/export/ai-recommendations").content.decode(
        "utf-8"
    )
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header = rows[0]
    for column in ("Standard ID", "Chapter", "Section", "Page", "Source Document"):
        assert column not in header, f"AI推奨事項に出典列 {column} があってはならない"
    assert "Origin" in header
    origin_index = header.index("Origin")
    assert all(row[origin_index] == "AI推奨（標準書由来ではない）" for row in rows[1:])


def test_recommendations_markdown_states_the_separation(client: TestClient) -> None:
    doc = _upload(client)
    _generate(client, doc["id"])
    md = client.get(
        f"/api/documents/{doc['id']}/export/ai-recommendations-markdown"
    ).content.decode("utf-8")
    assert "標準書由来ではありません" in md
    assert "Coverage には含まれません" in md


def test_bundle_includes_recommendations_only_after_generation(client: TestClient) -> None:
    doc = _upload(client)

    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/documents/{doc['id']}/export").content)) as zf:
        assert "ai-recommendations.csv" not in zf.namelist()

    _generate(client, doc["id"])

    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/documents/{doc['id']}/export").content)) as zf:
        names = zf.namelist()
    assert "ai-recommendations.csv" in names
    assert "ai-recommendations.md" in names
    assert "design-review-checklist.csv" in names


def test_adoption_can_be_recorded(client: TestClient) -> None:
    doc = _upload(client)
    rows = _generate(client, doc["id"])

    updated = client.patch(
        f"/api/documents/{doc['id']}/recommendations/{rows[0]['id']}",
        json={"adoption": "Adopted", "comment": "次回改訂で標準へ反映する"},
    )
    assert updated.status_code == 200
    assert updated.json()["adoption"] == "Adopted"
    assert updated.json()["comment"] == "次回改訂で標準へ反映する"


def test_regenerate_replaces_and_clear_removes(client: TestClient) -> None:
    doc = _upload(client)
    first = _generate(client, doc["id"])
    second = _generate(client, doc["id"])
    assert len(second) == len(first)
    assert second[0]["recommendation_id"] == "REC-UI-001"

    assert client.delete(f"/api/documents/{doc['id']}/recommendations").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}/recommendations").json() == []


def test_claude_generator_requires_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    doc = _upload(client)
    response = client.post(
        f"/api/documents/{doc['id']}/recommendations",
        json={"generator": "claude", "replace": True},
    )
    assert response.status_code == 422
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_claude_response_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude の応答は疑問文へ正規化し、重要度は既知の値に丸める。"""
    payload = {
        "recommendations": [
            {
                "category": "性能",
                "sub_category": "タイムアウト",
                "check_point": "タイムアウト値が定義されている",  # 疑問文でない
                "requirement": "タイムアウト値が定義されている",
                "severity": "とても高い",  # 未知の重要度
                "rationale": "標準書に記載が無いため",
            },
            {
                "category": "ログ",
                "sub_category": "ログ",
                "check_point": "",  # 空は捨てる
                "requirement": "x",
                "severity": "High",
                "rationale": "y",
            },
        ]
    }
    out = recommender._to_recommendations(payload, rule_texts=["画面IDを付与すること"])
    assert len(out) == 1
    assert out[0].check_point == "タイムアウト値が定義されているか？"
    assert out[0].severity == "Medium"
    assert out[0].generator == "claude"
    assert recommender.CLAUDE_MODEL in out[0].generator_detail


def test_claude_suggestions_duplicating_the_standard_are_dropped() -> None:
    payload = {
        "recommendations": [
            {
                "category": "UI",
                "sub_category": "項目ID",
                "check_point": "画面項目には項目IDを付与しているか？",
                "requirement": "x",
                "severity": "High",
                "rationale": "y",
            }
        ]
    }
    out = recommender._to_recommendations(
        payload, rule_texts=["画面項目には項目IDを付与している"]
    )
    assert out == []


def test_claude_refusal_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs["model"] == recommender.CLAUDE_MODEL
            return SimpleNamespace(stop_reason="refusal", content=[])

    class FakeClient:
        messages = FakeMessages()

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: FakeClient())

    with pytest.raises(RecommendationError, match="拒否"):
        recommender.claude_recommendations(
            document_name="画面設計標準", document_type="screen", rule_texts=["a"]
        )


def test_unknown_generator_is_rejected(client: TestClient) -> None:
    doc = _upload(client)
    response = client.post(
        f"/api/documents/{doc['id']}/recommendations",
        json={"generator": "gpt", "replace": True},
    )
    assert response.status_code == 422
