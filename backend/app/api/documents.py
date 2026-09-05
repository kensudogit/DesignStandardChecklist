"""標準書の登録・解析・参照 (STEP 1, 14-1)。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import taxonomy as tx
from app.core.parsers import SUPPORTED_EXTENSIONS, ParseError
from app.core.pipeline import analyze_document, next_document_id, suggest_document_type
from app.db import get_db
from app.models import AnalysisRun, ChecklistItem, Rule, StandardDocument
from app.schemas import DocumentMetaUpdate, DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
UNKNOWN = "不明"


def _to_out(db: Session, doc: StandardDocument) -> DocumentOut:
    rule_count = db.scalar(
        select(func.count()).select_from(Rule).where(Rule.document_pk == doc.id)
    ) or 0
    check_count = db.scalar(
        select(func.count()).select_from(ChecklistItem).where(ChecklistItem.document_pk == doc.id)
    ) or 0
    run = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.document_pk == doc.id)
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    ).first()
    out = DocumentOut.model_validate(doc)
    out.document_type_label = tx.DOC_TYPE_LABEL.get(doc.document_type, doc.document_type)
    out.rule_count = rule_count
    out.check_count = check_count
    out.coverage = run.coverage if run else None
    return out


def get_document(document_id: int, db: Session = Depends(get_db)) -> StandardDocument:
    doc = db.get(StandardDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="標準書が見つかりません")
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    docs = db.scalars(select(StandardDocument).order_by(StandardDocument.id.desc())).all()
    return [_to_out(db, d) for d in docs]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_name: str | None = Form(None),
    document_type: str | None = Form(None),
    version: str | None = Form(None),
    established_date: str | None = Form(None),
    revised_date: str | None = Form(None),
    target_phase: str | None = Form(None),
    target_deliverable: str | None = Form(None),
    notes: str | None = Form(None),
    analyze: bool = Form(True),
    db: Session = Depends(get_db),
) -> DocumentOut:
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"未対応の形式です ({ext or '拡張子なし'})。対応: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="ファイルが空です")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ファイルサイズが上限 (30MB) を超えています")

    settings = get_settings()
    stored = settings.storage_path / f"{uuid.uuid4().hex}{ext}"
    stored.write_bytes(data)

    doc_type = document_type or suggest_document_type(filename)
    if doc_type not in tx.DOC_TYPE_PREFIX:
        raise HTTPException(status_code=400, detail=f"未知の文書種別です: {doc_type}")

    doc = StandardDocument(
        document_id=next_document_id(db),
        document_name=(document_name or Path(filename).stem).strip(),
        document_type=doc_type,
        id_prefix=tx.DOC_TYPE_PREFIX[doc_type],
        version=(version or UNKNOWN).strip() or UNKNOWN,
        established_date=(established_date or UNKNOWN).strip() or UNKNOWN,
        revised_date=(revised_date or UNKNOWN).strip() or UNKNOWN,
        target_phase=(target_phase or UNKNOWN).strip() or UNKNOWN,
        target_deliverable=(target_deliverable or UNKNOWN).strip() or UNKNOWN,
        notes=(notes or "").strip(),
        original_filename=filename,
        stored_path=str(stored),
        file_format=ext.lstrip("."),
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if analyze:
        _run_analysis(db, doc)
    return _to_out(db, doc)


def _run_analysis(db: Session, doc: StandardDocument) -> None:
    try:
        analyze_document(db, doc)
    except ParseError as exc:
        db.rollback()
        doc.status = "failed"
        doc.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 想定外
        db.rollback()
        doc.status = "failed"
        doc.error_message = f"解析に失敗しました: {exc}"
        db.commit()
        raise HTTPException(status_code=500, detail=doc.error_message) from exc


@router.get("/{document_id}", response_model=DocumentOut)
def read_document(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> DocumentOut:
    return _to_out(db, doc)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document_meta(
    payload: DocumentMetaUpdate,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> DocumentOut:
    data = payload.model_dump(exclude_none=True)
    if "document_type" in data:
        if data["document_type"] not in tx.DOC_TYPE_PREFIX:
            raise HTTPException(status_code=400, detail="未知の文書種別です")
        doc.id_prefix = tx.DOC_TYPE_PREFIX[data["document_type"]]
    for key, value in data.items():
        setattr(doc, key, value)
    db.commit()
    db.refresh(doc)
    return _to_out(db, doc)


@router.post("/{document_id}/analyze", response_model=DocumentOut)
def reanalyze(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> DocumentOut:
    """再解析。規定ID/チェックIDは振り直すが、レビュー記入内容は Check ID で引き継ぐ。"""
    _run_analysis(db, doc)
    db.refresh(doc)
    return _to_out(db, doc)


@router.delete("/{document_id}", status_code=204, response_class=Response)
def delete_document(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> Response:
    stored = Path(doc.stored_path)
    db.delete(doc)
    db.commit()
    stored.unlink(missing_ok=True)
    return Response(status_code=204)
