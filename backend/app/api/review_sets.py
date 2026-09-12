"""統合レビュー表（複数標準書の横断チェックリスト）。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.analysis import _coverage_result, _items, apply_reviewer
from app.api.auth import current_user
from app.core import taxonomy as tx
from app.core.consolidate import ConsolidatedRow, consolidate, sources_of
from app.db import get_db
from app.models import (
    ChecklistItem,
    ConsolidatedCheck,
    ReviewSet,
    ReviewSetDocument,
    StandardDocument,
    User,
)
from app.schemas import (
    ChecklistItemUpdate,
    ConsolidatedCheckOut,
    ConsolidatedSource,
    ReviewSetCoverageOut,
    ReviewSetCoverageRow,
    ReviewSetCreate,
    ReviewSetMember,
    ReviewSetOut,
    ReviewSetUpdate,
)

router = APIRouter(prefix="/api/review-sets", tags=["review-sets"], dependencies=[Depends(current_user)])


def get_review_set(review_set_id: int, db: Session = Depends(get_db)) -> ReviewSet:
    """パス中の id から統合レビュー表を引く依存関数。無ければ 404。"""
    review_set = db.get(ReviewSet, review_set_id)
    if review_set is None:
        raise HTTPException(status_code=404, detail="統合レビュー表が見つかりません")
    return review_set


def _documents(db: Session, review_set: ReviewSet) -> list[StandardDocument]:
    """この統合レビュー表に含まれる標準書を、登録した順で返す。"""
    return [member.document for member in review_set.members]


def _set_documents(db: Session, review_set: ReviewSet, document_ids: list[int]) -> None:
    """対象の標準書を入れ替える。

    重複した指定は先勝ちで畳む。並び順は指定された順のまま保つ (position)。
    既存の割り当てを消してから入れ直すため、呼び出し後は再統合が必要になる。
    """
    seen: list[int] = []
    for document_id in document_ids:
        # 同じ標準書を二重に指定されても1件として扱う
        if document_id in seen:
            continue
        if db.get(StandardDocument, document_id) is None:
            raise HTTPException(status_code=400, detail=f"標準書が見つかりません: id={document_id}")
        seen.append(document_id)
    if len(seen) < 1:
        raise HTTPException(status_code=400, detail="標準書を1件以上指定してください")

    for member in list(review_set.members):
        db.delete(member)
    db.flush()
    for position, document_id in enumerate(seen):
        db.add(
            ReviewSetDocument(
                review_set_pk=review_set.id, document_pk=document_id, position=position
            )
        )
    db.flush()


def _build(db: Session, review_set: ReviewSet) -> list[ConsolidatedRow]:
    """統合行を作り直して保存する。"""
    per_document: list[tuple[StandardDocument, list[ChecklistItem]]] = []
    for document in _documents(db, review_set):
        per_document.append((document, [item for item, _ in _items(db, document.id)]))

    rows = consolidate(per_document)

    # 統合結果は毎回作り直す。差分更新にすると、統合の組み替えを追いきれない
    for old in db.scalars(
        select(ConsolidatedCheck).where(ConsolidatedCheck.review_set_pk == review_set.id)
    ).all():
        db.delete(old)
    db.flush()

    for no, row in enumerate(rows, start=1):
        db.add(
            ConsolidatedCheck(
                review_set_pk=review_set.id,
                no=no,
                primary_item_pk=row.primary.id,
                merged_item_pks=[item.id for item in row.merged],
                similar_check_ids=row.similar_check_ids,
                severity=row.severity,
            )
        )
    review_set.consolidated_at = datetime.now(UTC)
    db.commit()
    return rows


def _stored_rows(db: Session, review_set: ReviewSet) -> list[ConsolidatedCheck]:
    """保存済みの統合行を採番順で返す。"""
    return list(
        db.scalars(
            select(ConsolidatedCheck)
            .where(ConsolidatedCheck.review_set_pk == review_set.id)
            .order_by(ConsolidatedCheck.no)
        ).all()
    )


def _to_out(db: Session, review_set: ReviewSet) -> ReviewSetOut:
    """統合レビュー表を応答へ変換する。

    含まれる標準書ごとの Coverage はここで都度算出する。標準書側を再解析
    すると値が変わるため、統合時点の値を保存して見せると古くなる。
    """
    members: list[ReviewSetMember] = []
    for document in _documents(db, review_set):
        result, _ = _coverage_result(db, document)
        members.append(
            ReviewSetMember(
                document_id=document.id,
                document_code=document.document_id,
                document_name=document.document_name,
                document_type_label=tx.DOC_TYPE_LABEL.get(
                    document.document_type, document.document_type
                ),
                id_prefix=document.id_prefix,
                rule_count=result.total_rules,
                check_count=result.check_count,
                coverage=result.coverage,
            )
        )
    stored = _stored_rows(db, review_set)
    return ReviewSetOut(
        id=review_set.id,
        name=review_set.name,
        notes=review_set.notes,
        created_at=review_set.created_at,
        consolidated_at=review_set.consolidated_at,
        documents=members,
        check_count=len(stored),
        merged_count=sum(len(row.merged_item_pks) for row in stored),
    )


@router.get("", response_model=list[ReviewSetOut])
def list_review_sets(db: Session = Depends(get_db)) -> list[ReviewSetOut]:
    """統合レビュー表の一覧。新しいものを先頭に出す。"""
    sets = db.scalars(select(ReviewSet).order_by(ReviewSet.id.desc())).all()
    return [_to_out(db, s) for s in sets]


@router.post("", response_model=ReviewSetOut, status_code=201)
def create_review_set(payload: ReviewSetCreate, db: Session = Depends(get_db)) -> ReviewSetOut:
    """作成して、そのまま統合まで実行する。"""
    review_set = ReviewSet(name=payload.name.strip(), notes=payload.notes.strip())
    db.add(review_set)
    db.flush()
    _set_documents(db, review_set, payload.document_ids)
    db.commit()
    db.refresh(review_set)
    _build(db, review_set)
    db.refresh(review_set)
    return _to_out(db, review_set)


@router.get("/{review_set_id}", response_model=ReviewSetOut)
def read_review_set(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> ReviewSetOut:
    """統合レビュー表1件。"""
    return _to_out(db, review_set)


@router.patch("/{review_set_id}", response_model=ReviewSetOut)
def update_review_set(
    payload: ReviewSetUpdate,
    review_set: ReviewSet = Depends(get_review_set),
    db: Session = Depends(get_db),
) -> ReviewSetOut:
    """名前・備考・対象標準書を更新する。

    対象標準書を入れ替えた場合は統合結果が食い違うので、続けて統合し直す。
    """
    data = payload.model_dump(exclude_none=True)
    if "name" in data:
        review_set.name = data["name"].strip()
    if "notes" in data:
        review_set.notes = data["notes"].strip()
    if "document_ids" in data:
        _set_documents(db, review_set, data["document_ids"])
    db.commit()
    db.refresh(review_set)
    _build(db, review_set)
    db.refresh(review_set)
    return _to_out(db, review_set)


@router.post("/{review_set_id}/consolidate", response_model=ReviewSetOut)
def rebuild(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> ReviewSetOut:
    """各標準書の最新の解析結果から統合表を作り直す。"""
    _build(db, review_set)
    db.refresh(review_set)
    return _to_out(db, review_set)


@router.delete("/{review_set_id}", status_code=204, response_class=Response)
def delete_review_set(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> Response:
    """統合レビュー表を削除する。

    消えるのは統合表と統合行だけで、元の標準書と個別のチェックリストは残る。
    """
    db.delete(review_set)
    db.commit()
    return Response(status_code=204)


def _name_map(db: Session, review_set: ReviewSet) -> dict[int, str]:
    """標準書 id → 文書名。出典の表示に使う。"""
    return {d.id: d.document_name for d in _documents(db, review_set)}


def _row_out(
    db: Session, stored: ConsolidatedCheck, names: dict[int, str]
) -> ConsolidatedCheckOut:
    """保存済みの統合行を応答へ組み立てる。

    表示内容は代表のチェック項目 (primary) から取る。レビュー結果も代表の値を
    返すが、更新時は統合元すべてへ書き戻すので、どれを見ても同じ値になる。

    代表が見つからない場合は 409。標準書を再解析して Check ID が変わると、
    統合表が古い項目を指したままになるため、再統合を促す。
    """
    primary = db.get(ChecklistItem, stored.primary_item_pk)
    if primary is None:
        raise HTTPException(
            status_code=409,
            detail="統合表が最新ではありません。再統合してください。",
        )
    merged = [db.get(ChecklistItem, pk) for pk in stored.merged_item_pks]
    merged_items = [m for m in merged if m is not None]
    row = ConsolidatedRow(primary=primary, merged=merged_items)
    return ConsolidatedCheckOut(
        id=stored.id,
        no=stored.no,
        check_id=primary.check_id,
        category=primary.category,
        sub_category=primary.sub_category,
        check_point=primary.check_point,
        requirement=primary.requirement,
        severity=stored.severity,
        condition=primary.condition,
        exception=primary.exception,
        note=primary.note,
        sources=[ConsolidatedSource(**s) for s in sources_of(row, names)],
        merged_check_ids=[m.check_id for m in merged_items],
        similar_check_ids=stored.similar_check_ids,
        result=primary.result,
        evidence=primary.evidence,
        reviewer=primary.reviewer,
        review_date=primary.review_date,
        comment=primary.comment,
    )


@router.get("/{review_set_id}/checklist", response_model=list[ConsolidatedCheckOut])
def consolidated_checklist(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> list[ConsolidatedCheckOut]:
    """統合チェックリスト。1行が複数の標準書を出典に持ちうる。"""
    names = _name_map(db, review_set)
    return [_row_out(db, stored, names) for stored in _stored_rows(db, review_set)]


@router.patch("/{review_set_id}/checklist/{row_id}", response_model=ConsolidatedCheckOut)
def update_consolidated_item(
    row_id: int,
    payload: ChecklistItemUpdate,
    review_set: ReviewSet = Depends(get_review_set),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
) -> ConsolidatedCheckOut:
    """記入内容は統合元のチェック項目すべてへ書き戻す。

    同一内容のチェックを別々に判定してしまうと、文書別チェックリストと
    統合表で結果が食い違うため。
    """
    stored = db.get(ConsolidatedCheck, row_id)
    if stored is None or stored.review_set_pk != review_set.id:
        raise HTTPException(status_code=404, detail="チェック項目が見つかりません")

    raw = payload.model_dump(exclude_none=True)
    targets = [db.get(ChecklistItem, stored.primary_item_pk)]
    targets += [db.get(ChecklistItem, pk) for pk in stored.merged_item_pks]
    for item in targets:
        if item is None:
            continue
        for key, value in apply_reviewer(dict(raw), item, user).items():
            setattr(item, key, value)
    db.commit()
    return _row_out(db, stored, _name_map(db, review_set))


@router.get("/{review_set_id}/coverage", response_model=ReviewSetCoverageOut)
def review_set_coverage(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> ReviewSetCoverageOut:
    """標準書別Coverageと、統合による重複削減の内訳。"""
    by_document: list[ReviewSetCoverageRow] = []
    total_target = 0
    total_converted = 0
    total_checks = 0

    for document in _documents(db, review_set):
        result, _ = _coverage_result(db, document)
        total_target += result.target_rules
        total_converted += result.converted_rules
        total_checks += result.check_count
        by_document.append(
            ReviewSetCoverageRow(
                document_id=document.id,
                document_name=document.document_name,
                document_type_label=tx.DOC_TYPE_LABEL.get(
                    document.document_type, document.document_type
                ),
                coverage=result.coverage,
                mandatory_coverage=result.mandatory_coverage,
                prohibited_coverage=result.prohibited_coverage,
                target_rules=result.target_rules,
                converted_rules=result.converted_rules,
                unconverted_rules=result.unconverted_rules,
                check_count=result.check_count,
            )
        )

    stored = _stored_rows(db, review_set)
    merged = sum(len(row.merged_item_pks) for row in stored)
    similar = sum(len(row.similar_check_ids) for row in stored)

    findings: list[str] = []
    below = [r for r in by_document if r.mandatory_coverage < 100 or r.prohibited_coverage < 100]
    if below:
        findings.append(
            "必須・禁止規定のCoverageが100%未満の標準書があります: "
            + "、".join(r.document_name for r in below)
        )
    if merged:
        findings.append(
            f"標準書をまたいで完全に重複するチェック項目を{merged}件統合しました。"
            "統合された項目は複数の標準書を出典として保持しています。"
        )
    if similar:
        findings.append(
            f"標準書をまたぐ類似チェック項目が{similar}件あります。"
            "自動統合はしていないため、統合可否を確認してください。"
        )
    if not findings:
        findings.append("標準書間で重複するチェック項目はありませんでした。")

    return ReviewSetCoverageOut(
        by_document=by_document,
        total_target_rules=total_target,
        total_converted_rules=total_converted,
        total_coverage=(
            round(total_converted / total_target * 100, 1) if total_target else 100.0
        ),
        total_checks_before_merge=total_checks,
        consolidated_checks=len(stored),
        merged_checks=merged,
        cross_document_similar=similar,
        findings=findings,
    )


# --- 成果物のダウンロード -----------------------------------------------------

REVIEW_SET_ARTIFACTS = (
    "consolidated-checklist",
    "consolidated-checklist-markdown",
    "cross-traceability-matrix",
    "cross-coverage-report",
)


def _artifact(db: Session, review_set: ReviewSet, artifact: str) -> tuple[str, str, str]:
    """成果物を1つ組み立てて (filename, media_type, body) を返す。

    exporter を関数内で import しているのは、循環 import を避けるため。
    """
    from app.core import exporter

    if artifact in ("consolidated-checklist", "consolidated-checklist-markdown", "cross-traceability-matrix"):
        rows = [row.model_dump() for row in consolidated_checklist(review_set, db)]
        if artifact == "consolidated-checklist":
            return (
                "consolidated-checklist.csv",
                "text/csv; charset=utf-8",
                exporter.consolidated_checklist_csv(rows),
            )
        if artifact == "consolidated-checklist-markdown":
            return (
                "consolidated-checklist.md",
                "text/markdown; charset=utf-8",
                exporter.consolidated_markdown(review_set.name, rows),
            )
        return (
            "cross-traceability-matrix.csv",
            "text/csv; charset=utf-8",
            exporter.cross_traceability_csv(rows),
        )
    if artifact == "cross-coverage-report":
        coverage = review_set_coverage(review_set, db).model_dump()
        return (
            "cross-coverage-report.md",
            "text/markdown; charset=utf-8",
            exporter.review_set_coverage_markdown(review_set.name, coverage),
        )
    raise HTTPException(status_code=404, detail=f"未知の成果物です: {artifact}")


def _disposition(filename: str) -> str:
    """ダウンロード時のファイル名ヘッダ。日本語を含むので RFC 5987 形式で送る。"""
    from urllib.parse import quote

    return f"attachment; filename*=UTF-8''{quote(filename)}"


@router.get("/{review_set_id}/export/{artifact}")
def download_review_set_artifact(
    artifact: str,
    review_set: ReviewSet = Depends(get_review_set),
    db: Session = Depends(get_db),
) -> Response:
    """統合レビュー表の成果物を1つダウンロードする。"""
    filename, media_type, body = _artifact(db, review_set, artifact)
    return Response(
        content=body.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": _disposition(filename)},
    )


@router.get("/{review_set_id}/export")
def download_review_set_bundle(
    review_set: ReviewSet = Depends(get_review_set), db: Session = Depends(get_db)
) -> Response:
    """統合レビュー表の成果物をまとめて ZIP で返す。

    標準書ごとの成果物は含まない。個別のものは各標準書の画面から取得する。
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for artifact in REVIEW_SET_ARTIFACTS:
            filename, _, body = _artifact(db, review_set, artifact)
            zf.writestr(filename, body.encode("utf-8"))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": _disposition(f"review-set-{review_set.id}-artifacts.zip")},
    )
