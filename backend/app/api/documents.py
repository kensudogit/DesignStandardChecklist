"""標準書の登録・解析・参照 (STEP 1, 14-1)。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.config import get_settings
from app.core import taxonomy as tx
from app.core.parsers import SUPPORTED_EXTENSIONS, ParseError
from app.core.pipeline import analyze_document, next_document_id, suggest_document_type
from app.db import get_db
from app.models import AnalysisRun, ChecklistItem, Rule, StandardDocument
from app.schemas import DocumentMetaUpdate, DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(current_user)])

#: アップロード上限。解析が同期実行のため、応答が返らなくなる大きさを避ける狙いもある。
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
UNKNOWN = "不明"


def _to_out(db: Session, doc: StandardDocument) -> DocumentOut:
    """DB のモデルを API 応答へ変換する。

    規定数・チェック数・Coverage は別テーブルにあるので、ここで数えて詰め直す。
    Coverage は最新の解析実行 (AnalysisRun) の値を使う。未解析なら None。
    """
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
    """パス中の document_id から標準書を引く FastAPI の依存関数。

    見つからなければ 404。各エンドポイントで存在チェックを書かずに済ませるため。
    """
    doc = db.get(StandardDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="標準書が見つかりません")
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    """標準書一覧。新しく登録したものを先頭に出す。"""
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
    """標準書をアップロードし、既定ではそのまま解析まで走らせる。

    解析は同期実行なので、大きな標準書ではこの応答が遅くなる。バックグラウンド化
    しないのは、失敗した理由をその場で返したいため。
    """
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

    doc = _create_document(
        db,
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

    # 既定は登録と同時に解析する。analyze=False は取り込みだけしたいとき用
    if analyze:
        _run_analysis(db, doc)
    return _to_out(db, doc)


#: 採番が衝突したときに番号を採り直す回数。実運用で数回を超えることはない。
MAX_DOCUMENT_ID_ATTEMPTS = 5


def _create_document(db: Session, **fields: object) -> StandardDocument:
    """標準書を作る。採番が衝突したら番号を採り直す。

    next_document_id は「既存の最大 + 1」を読んでから書くため、同時に2件
    アップロードされると両方が同じ番号を採りうる。document_id には一意制約が
    あるので、後から書いた側は IntegrityError になる。

    衝突しても失う情報は無く、番号を採り直して入れ直せば済む。ここで捕まえて
    やり直し、利用者にはエラーを見せない。
    """
    for _ in range(MAX_DOCUMENT_ID_ATTEMPTS):
        doc = StandardDocument(document_id=next_document_id(db), **fields)
        db.add(doc)
        try:
            db.commit()
        except IntegrityError:
            # StandardDocument の一意制約は document_id だけなので、衝突の原因は採番。
            db.rollback()
            continue
        db.refresh(doc)
        return doc

    raise HTTPException(
        status_code=503,
        detail="標準書IDの採番が繰り返し衝突しました。時間をおいて再度登録してください。",
    )


def _run_analysis(db: Session, doc: StandardDocument) -> None:
    """解析を実行し、失敗したら標準書を failed 状態にして残す。

    レコードごと消さないのは、何が原因で失敗したかを画面で確認できるようにするため。
    ParseError は利用者側で直せる問題 (422)、それ以外は想定外 (500) として分ける。
    """
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
    """標準書1件の詳細。"""
    return _to_out(db, doc)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document_meta(
    payload: DocumentMetaUpdate,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """版数・制定日などのメタ情報を後から直す。

    文書種別を変えると ID プレフィックスも連動して変わる。既に採番済みの
    規定ID・チェックIDは再解析するまで古いプレフィックスのまま残る。
    """
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
    """標準書を削除する。規定・チェック項目・レビュー記入も cascade で消える。

    アップロードした原本ファイルは DB のコミット後に消す。順序を逆にすると、
    DB 側が失敗したときにファイルだけ失われる。
    """
    stored = Path(doc.stored_path)
    db.delete(doc)
    db.commit()
    # コミット後に消す。逆順だと DB 側が失敗したときに原本だけ失われる
    stored.unlink(missing_ok=True)
    return Response(status_code=204)
