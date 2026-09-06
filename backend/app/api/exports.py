"""STEP 14: 成果物ダウンロード。README の推奨6成果物 + チェックリストMarkdown。"""

from __future__ import annotations

import io
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.analysis import _coverage_result, _items, _rules
from app.api.auth import current_user
from app.api.documents import get_document
from app.core import exporter
from app.db import get_db
from app.models import Recommendation, StandardDocument

router = APIRouter(prefix="/api/documents/{document_id}/export", tags=["export"], dependencies=[Depends(current_user)])

#: ZIP に常に含める成果物。すべて標準書由来。
ARTIFACTS = (
    "standard-register",
    "extracted-rules",
    "design-review-checklist",
    "traceability-matrix",
    "unconverted-rules",
    "coverage-report",
    "checklist-markdown",
)

#: AI推奨事項は「要求された場合のみ」の成果物なので、既定のZIPには含めない (STEP 14-7)。
OPTIONAL_ARTIFACTS = ("ai-recommendations", "ai-recommendations-markdown")


def _recommendations(db: Session, document_pk: int) -> list[Recommendation]:
    """その標準書の AI推奨事項を採番順で返す。ZIP に同梱するかの判定にも使う。"""
    return list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.document_pk == document_pk)
            .order_by(Recommendation.no)
        ).all()
    )


def _content_disposition(filename: str) -> str:
    """ダウンロード時のファイル名ヘッダ。

    RFC 5987 の filename*=UTF-8'' 形式のみを使う。素の filename= に日本語を
    そのまま置くと、ブラウザによって文字化けや欠落が起きる。

    なお、このヘッダをブラウザの JavaScript から読むには CORS の
    expose_headers に Content-Disposition を入れる必要がある (main.py)。
    """
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def build_artifact(db: Session, doc: StandardDocument, artifact: str) -> tuple[str, str, str]:
    """(filename, media_type, body) を返す。"""
    if artifact == "standard-register":
        docs = list(db.scalars(select(StandardDocument).order_by(StandardDocument.id)).all())
        return "standard-register.csv", "text/csv; charset=utf-8", exporter.standard_register_csv(docs)
    if artifact == "extracted-rules":
        return (
            "extracted-rules.csv",
            "text/csv; charset=utf-8",
            exporter.extracted_rules_csv(doc, _rules(db, doc.id)),
        )
    if artifact == "design-review-checklist":
        return (
            "design-review-checklist.csv",
            "text/csv; charset=utf-8",
            exporter.checklist_csv(doc, _items(db, doc.id)),
        )
    if artifact == "traceability-matrix":
        return (
            "traceability-matrix.csv",
            "text/csv; charset=utf-8",
            exporter.traceability_csv(doc, _items(db, doc.id)),
        )
    if artifact == "unconverted-rules":
        return (
            "unconverted-rules.csv",
            "text/csv; charset=utf-8",
            exporter.unconverted_rules_csv(_rules(db, doc.id)),
        )
    if artifact == "coverage-report":
        result, run = _coverage_result(db, doc)
        return (
            "coverage-report.md",
            "text/markdown; charset=utf-8",
            exporter.coverage_markdown(doc, run, result),
        )
    if artifact == "ai-recommendations":
        return (
            "ai-recommendations.csv",
            "text/csv; charset=utf-8",
            exporter.ai_recommendations_csv(doc, _recommendations(db, doc.id)),
        )
    if artifact == "ai-recommendations-markdown":
        return (
            "ai-recommendations.md",
            "text/markdown; charset=utf-8",
            exporter.ai_recommendations_markdown(doc, _recommendations(db, doc.id)),
        )
    if artifact == "checklist-markdown":
        return (
            "design-review-checklist.md",
            "text/markdown; charset=utf-8",
            exporter.checklist_markdown(doc, _items(db, doc.id)),
        )
    raise HTTPException(status_code=404, detail=f"未知の成果物です: {artifact}")


@router.get("/{artifact}")
def download_artifact(
    artifact: str,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> Response:
    """成果物を1つダウンロードする。"""
    filename, media_type, body = build_artifact(db, doc, artifact)
    return Response(
        content=body.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("")
def download_all(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> StreamingResponse:
    """成果物をまとめて ZIP で返す。

    AI推奨事項は生成済みのときだけ同梱する。標準由来の成果物とは別ファイルに
    分かれているので、ZIP を開いた時点で由来を取り違えることはない。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for artifact in ARTIFACTS:
            filename, _, body = build_artifact(db, doc, artifact)
            zf.writestr(filename, body.encode("utf-8"))
        # 生成済みの場合のみ、標準由来と分けたファイルとして同梱する
        if _recommendations(db, doc.id):
            for artifact in OPTIONAL_ARTIFACTS:
                filename, _, body = build_artifact(db, doc, artifact)
                zf.writestr(filename, body.encode("utf-8"))
    buf.seek(0)
    name = f"{doc.document_id}-checklist-artifacts.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(name)},
    )
