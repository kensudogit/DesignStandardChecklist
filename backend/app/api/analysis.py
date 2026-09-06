"""規定一覧 / チェックリスト / トレーサビリティ / 未変換規定 / Coverage の参照と更新。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.api.documents import get_document
from app.core import taxonomy as tx
from app.core.coverage import CoverageResult, compute_coverage
from app.db import get_db
from app.models import AnalysisRun, ChecklistItem, Rule, StandardDocument, User
from app.schemas import (
    ChecklistItemOut,
    ChecklistItemUpdate,
    CoverageByType,
    CoverageOut,
    ReviewProgress,
    RuleOut,
    TraceabilityRow,
    UnconvertedRow,
)

router = APIRouter(prefix="/api/documents/{document_id}", tags=["analysis"], dependencies=[Depends(current_user)])

UNKNOWN = "不明"


def apply_reviewer(data: dict, item, user: User | None) -> dict:
    """判定を記録したのが誰かを残す。

    認証が有効なら、Reviewer 未入力のときにログイン利用者で補う。
    明示的に入力された値は上書きしない（代理入力を妨げないため）。
    """
    if user is None or "result" not in data:
        return data
    if not data.get("reviewer") and not item.reviewer:
        data["reviewer"] = user.display_name or user.username
    return data


def _rules(db: Session, document_pk: int) -> list[Rule]:
    """その標準書の規定を、抽出順 (id 順) で全件返す。"""
    return list(
        db.scalars(
            select(Rule).where(Rule.document_pk == document_pk).order_by(Rule.id)
        ).all()
    )


def _items(db: Session, document_pk: int) -> list[tuple[ChecklistItem, Rule]]:
    """チェック項目を、由来する規定と組にして返す。

    出典 (章・節・ページ) は規定側にしか無いため、常に join して取り出す。
    """
    rows = db.execute(
        select(ChecklistItem, Rule)
        .join(Rule, ChecklistItem.rule_pk == Rule.id)
        .where(ChecklistItem.document_pk == document_pk)
        .order_by(ChecklistItem.no)
    ).all()
    return [(item, rule) for item, rule in rows]


def _item_out(item: ChecklistItem, rule: Rule, document: StandardDocument) -> ChecklistItemOut:
    """チェック項目と規定を1つの応答へまとめる (STEP 12: トレーサビリティ)。

    出典は規定側の値をそのまま写す。ここで補完や推測はしない。
    """
    out = ChecklistItemOut.model_validate(item)
    out.standard_id = rule.standard_id
    out.source_document = document.document_name
    out.chapter = rule.chapter
    out.section = rule.section
    out.page = rule.page
    out.locator = rule.locator
    out.original_rule = rule.original_rule
    return out


@router.get("/rules", response_model=list[RuleOut])
def list_rules(
    rule_type: str | None = Query(None),
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> list[RuleOut]:
    """規定抽出一覧 (STEP 3-6)。規範レベルで絞り込める。"""
    rules = _rules(db, doc.id)
    if rule_type:
        rules = [r for r in rules if r.rule_type == rule_type]
    out: list[RuleOut] = []
    for rule in rules:
        model = RuleOut.model_validate(rule)
        model.check_ids = [c.check_id for c in rule.checks]
        out.append(model)
    return out


@router.get("/checklist", response_model=list[ChecklistItemOut])
def list_checklist(
    severity: str | None = Query(None),
    category: str | None = Query(None),
    result: str | None = Query(None),
    q: str | None = Query(None),
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
) -> list[ChecklistItemOut]:
    """レビューチェックリスト (STEP 7-12)。

    絞り込みは DB ではなく Python 側で行う。1標準書あたりの件数が多くなく、
    全文検索が規定の原文にもまたがるため、まとめて取ってから絞る方が単純になる。
    """
    rows = _items(db, doc.id)
    if severity:
        rows = [(i, r) for i, r in rows if i.severity == severity]
    if category:
        rows = [(i, r) for i, r in rows if i.category == category]
    if result:
        rows = [(i, r) for i, r in rows if i.result == result]
    if q:
        needle = q.strip().lower()
        rows = [
            (i, r)
            for i, r in rows
            if needle in i.check_point.lower()
            or needle in r.original_rule.lower()
            or needle in i.check_id.lower()
            or needle in r.standard_id.lower()
        ]
    return [_item_out(i, r, doc) for i, r in rows]


@router.patch("/checklist/{item_id}", response_model=ChecklistItemOut)
def update_checklist_item(
    item_id: int,
    payload: ChecklistItemUpdate,
    doc: StandardDocument = Depends(get_document),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
) -> ChecklistItemOut:
    """レビュー結果を1件更新する。

    未指定の項目は変更しない (exclude_none)。画面側が1欄ずつ保存してくるため。
    """
    item = db.get(ChecklistItem, item_id)
    if item is None or item.document_pk != doc.id:
        raise HTTPException(status_code=404, detail="チェック項目が見つかりません")
    data = apply_reviewer(payload.model_dump(exclude_none=True), item, user)
    for key, value in data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    rule = db.get(Rule, item.rule_pk)
    assert rule is not None
    return _item_out(item, rule, doc)


@router.get("/progress", response_model=ReviewProgress)
def review_progress(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> ReviewProgress:
    """レビューの進捗集計。重要度別の件数は未判定も含めた総数。"""
    rows = _items(db, doc.id)
    by_severity = {s: 0 for s in tx.SEVERITIES}
    for item, _ in rows:
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
    return ReviewProgress(
        total=len(rows),
        ok=sum(1 for i, _ in rows if i.result == "OK"),
        ng=sum(1 for i, _ in rows if i.result == "NG"),
        na=sum(1 for i, _ in rows if i.result == "N/A"),
        pending=sum(1 for i, _ in rows if i.result == "Pending"),
        by_severity=by_severity,
    )


def _coverage_result(db: Session, doc: StandardDocument) -> tuple[CoverageResult, AnalysisRun | None]:
    """Coverage を算出する。重複候補の件数だけは解析時のスナップショットを使う。

    重複判定は解析パイプラインの中でしか行わないため、ここでは数え直せない。
    """
    rules = _rules(db, doc.id)
    run = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.document_pk == doc.id)
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    ).first()
    duplicates = run.duplicate_candidates if run else 0
    check_count = len(_items(db, doc.id))
    return compute_coverage(rules, check_count=check_count, duplicate_candidates=duplicates), run


@router.get("/coverage", response_model=CoverageOut)
def coverage(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> CoverageOut:
    """Coverage レポート (STEP 13)。"""
    result, run = _coverage_result(db, doc)
    return CoverageOut(
        total_rules=result.total_rules,
        target_rules=result.target_rules,
        converted_rules=result.converted_rules,
        unconverted_rules=result.unconverted_rules,
        coverage=result.coverage,
        mandatory_total=result.mandatory_total,
        mandatory_converted=result.mandatory_converted,
        mandatory_coverage=result.mandatory_coverage,
        prohibited_total=result.prohibited_total,
        prohibited_converted=result.prohibited_converted,
        prohibited_coverage=result.prohibited_coverage,
        ambiguous_rules=result.ambiguous_rules,
        missing_source_rules=result.missing_source_rules,
        duplicate_candidates=result.duplicate_candidates,
        check_count=result.check_count,
        by_rule_type=[
            CoverageByType(
                rule_type=k,
                total=int(v["total"]),
                converted=int(v["converted"]),
                unconverted=int(v["unconverted"]),
                coverage=float(v["coverage"]),
            )
            for k, v in result.by_rule_type.items()
        ],
        findings=result.findings,
        analyzed_at=run.created_at if run else None,
    )


@router.get("/traceability", response_model=list[TraceabilityRow])
def traceability(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> list[TraceabilityRow]:
    """トレーサビリティ表 (STEP 12)。

    出典が1つも取れない規定は Trace Status を Source Unknown にする。
    ページ番号を推測して埋めることはしない (必須原則)。
    """
    out: list[TraceabilityRow] = []
    for item, rule in _items(db, doc.id):
        has_source = bool(rule.chapter or rule.section or rule.page is not None or rule.locator)
        notes: list[str] = []
        if item.extra_standard_ids:
            notes.append("複数標準由来: " + ";".join(item.extra_standard_ids))
        if item.merged_check_ids:
            notes.append("重複統合元: " + ";".join(item.merged_check_ids))
        if item.similar_check_ids:
            notes.append("類似候補: " + ";".join(item.similar_check_ids))
        if not has_source:
            notes.append("出典を特定できないため推測せず不明とした")
        page = rule.page if rule.page is not None else rule.locator
        out.append(
            TraceabilityRow(
                check_id=item.check_id,
                standard_id=";".join([rule.standard_id, *item.extra_standard_ids]),
                source_document=doc.document_name,
                chapter=rule.chapter,
                section=rule.section,
                page=str(page) if page else UNKNOWN,
                trace_status="Traced" if has_source else "Source Unknown",
                notes=" / ".join(notes),
            )
        )
    return out


@router.get("/unconverted", response_model=list[UnconvertedRow])
def unconverted(
    doc: StandardDocument = Depends(get_document), db: Session = Depends(get_db)
) -> list[UnconvertedRow]:
    """未変換規定一覧 (STEP 13)。

    必要な対応は、曖昧さが原因かどうかで文面を変える。曖昧な規定は標準書側の
    判断が要るので、再解析しても解決しない。
    """
    return [
        UnconvertedRow(
            standard_id=r.standard_id,
            original_rule=r.original_rule,
            reason_not_converted=r.unconverted_reason or "",
            required_action=(
                "標準書の判定基準を確認し、チェック項目化の可否を判断する"
                if r.ambiguity
                else "規定文を分割・具体化したうえで再解析する"
            ),
        )
        for r in _rules(db, doc.id)
        if r.unconverted_reason
    ]
