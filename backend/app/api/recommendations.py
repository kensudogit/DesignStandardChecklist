"""STEP 14-7: AI推奨事項（要求された場合のみ生成）。

必須原則 8 に従い、標準由来のチェックリストとは別のリソースとして扱う。
生成しない限り1件も存在しないので、既定の成果物は標準由来のみで構成される。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.analysis import _items, _rules
from app.api.auth import current_user
from app.api.documents import get_document
from app.core import recommender
from app.core.recommender import RecommendationError
from app.db import get_db
from app.models import Recommendation, StandardDocument
from app.schemas import (
    RecommendationOut,
    RecommendationRequest,
    RecommendationStatus,
    RecommendationUpdate,
)

router = APIRouter(prefix="/api/documents/{document_id}/recommendations", tags=["recommendations"], dependencies=[Depends(current_user)])

#: 由来の説明。画面の警告帯に出して、標準由来と取り違えないようにする。
SEPARATION_NOTE = (
    "AI推奨事項は標準書由来ではありません。チェックリスト・トレーサビリティ・"
    "Coverage には含まれず、出典（章・節・ページ）も持ちません。"
)


def _rows(db: Session, document_pk: int) -> list[Recommendation]:
    """その標準書の AI推奨事項を採番順で返す。"""
    return list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.document_pk == document_pk)
            .order_by(Recommendation.no)
        ).all()
    )


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> list[Recommendation]:
    """生成済みの AI推奨事項の一覧。未生成なら空。"""
    return _rows(db, doc.id)


@router.get("/status", response_model=RecommendationStatus)
def status(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> RecommendationStatus:
    """生成可否の問い合わせ。

    画面はこの結果で生成方式のプルダウンを組み立てる。APIキーが無いときに
    Claude を選ばせて失敗させないため、選択肢の側で先に落としている。
    """
    claude_ok = recommender.claude_available()
    return RecommendationStatus(
        count=len(_rows(db, doc.id)),
        generators_available=["catalog"] + (["claude"] if claude_ok else []),
        claude_available=claude_ok,
        claude_model=recommender.CLAUDE_MODEL,
        note=SEPARATION_NOTE,
    )


@router.post("", response_model=list[RecommendationOut], status_code=201)
def generate_recommendations(
    payload: RecommendationRequest,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> list[Recommendation]:
    """AI推奨事項を生成する。

    解析前の標準書に対しては 409 で断る。標準書がどこまで規定しているかを
    知らないまま提案しても、既に規定済みの観点を重ねて出すだけになるため。

    replace=True なら総入れ替え、False なら既存に無いものだけ追記する。
    """
    rules = _rules(db, doc.id)
    if not rules:
        raise HTTPException(
            status_code=409,
            detail="解析済みの規定がありません。先に標準書を解析してください。",
        )

    try:
        generated = recommender.generate(
            generator=payload.generator,
            document_name=doc.document_name,
            document_type=doc.document_type,
            rule_texts=[r.original_rule for r in rules],
            check_points=[item.check_point for item, _ in _items(db, doc.id)],
        )
    except RecommendationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 総入れ替え。採否やコメントの記入内容も一緒に消える
    if payload.replace:
        for old in _rows(db, doc.id):
            db.delete(old)
        db.flush()
        start = 0
    else:
        existing = _rows(db, doc.id)
        start = max((r.no for r in existing), default=0)
        known = {r.check_point for r in existing}
        # 追記時は同じ内容の提案を重ねない。生成方式を変えると重複しやすい
        generated = [g for g in generated if g.check_point not in known]

    prefix = doc.id_prefix
    created: list[Recommendation] = []
    for offset, item in enumerate(generated, start=1):
        no = start + offset
        row = Recommendation(
            document_pk=doc.id,
            recommendation_id=f"REC-{prefix}-{no:03d}",
            no=no,
            category=item.category,
            sub_category=item.sub_category,
            check_point=item.check_point,
            requirement=item.requirement,
            severity=item.severity,
            rationale=item.rationale,
            generator=item.generator,
            generator_detail=item.generator_detail,
        )
        db.add(row)
        created.append(row)
    db.commit()
    return _rows(db, doc.id)


@router.patch("/{recommendation_pk}", response_model=RecommendationOut)
def update_recommendation(
    recommendation_pk: int,
    payload: RecommendationUpdate,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> Recommendation:
    """採否とコメントを記録する。推奨内容そのものは書き換えない。"""
    row = db.get(Recommendation, recommendation_pk)
    if row is None or row.document_pk != doc.id:
        raise HTTPException(status_code=404, detail="AI推奨事項が見つかりません")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("", status_code=204, response_class=Response)
def clear_recommendations(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> Response:
    """生成済みの AI推奨事項をすべて消す。標準由来の成果物には影響しない。"""
    for row in _rows(db, doc.id):
        db.delete(row)
    db.commit()
    return Response(status_code=204)
