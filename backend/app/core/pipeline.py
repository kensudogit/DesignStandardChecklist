"""SKILL.md STEP 1-14 を通しで実行する。

入口は analyze_document(): パース済み文書 → DB上の Rule / ChecklistItem / AnalysisRun。
再解析時は既存の解析結果を作り直すが、レビュー記入欄 (Result/Evidence/Reviewer/Comment) は
Check ID をキーに引き継ぐ。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import taxonomy as tx
from app.core import llm_classify
from app.core import llm_split
from app.core.atomizer import AtomicCheck, atomize, base_sentence
from app.core.coverage import CoverageResult, compute_coverage
from app.core.dedupe import find_duplicates
from app.core.extractor import ExtractedRule, extract_rules
from app.core.parsers import parse_document
from app.core.severity import decide_severity
from app.core.structure import assign_structure
from app.models import AnalysisRun, ChecklistItem, IdSequence, Rule, StandardDocument

#: 短すぎる / 述語が無い等でチェック化できない場合の理由
REASON_TOO_SHORT = "確認可能な粒度に変換できない (規定文が短く述部を特定できない)"
REASON_AMBIGUOUS_ONLY = "曖昧表現のみで構成され、判定基準が標準書内に定義されていない"

#: これより短い確認事項は「〜か？」を付けても判定できないので採用しない
MIN_CHECK_POINT_LEN = 8


def checks_for_rule(
    item: ExtractedRule, assist: llm_split.SplitAssist | None = None
) -> tuple[list[AtomicCheck], str | None]:
    """STEP 7: 1規定 → Atomic Check 群。変換できない場合は (空, 理由)。

    DB を触らないので eval/ の評価スクリプトからも同じ判定を呼べる。
    ここを分岐の唯一の置き場にして、評価が実装のコピーを測ってしまうのを防ぐ。

    assist を渡すと、ルールベースが1件にしか分解できなかった規定だけ Claude に
    区切りを尋ねる。提案が原文と一致しなければ黙って捨て、ルールベースの結果を使う。
    """
    checks = [c for c in atomize(item) if len(c.check_point) >= MIN_CHECK_POINT_LEN]
    if not checks:
        return [], REASON_TOO_SHORT
    if item.ambiguity and item.rule_type == "Reference":
        return [], REASON_AMBIGUOUS_ONLY

    if assist is not None and len(checks) == 1:
        assisted = llm_split.assisted_checks(item, assist, base_sentence(item))
        if assisted:
            kept = [c for c in assisted if len(c.check_point) >= MIN_CHECK_POINT_LEN]
            if len(kept) > len(checks):
                return kept, None
    return checks, None


def suggest_document_type(filename: str, sample_text: str = "") -> str:
    haystack = f"{filename} {sample_text[:2000]}"
    for doc_type, hints in tx.DOC_TYPE_HINTS:
        if any(h in haystack for h in hints):
            return doc_type
    return "other"


#: 標準書IDの接頭辞。出力・トレーサビリティ表にそのまま現れる。
DOCUMENT_ID_PREFIX = "DOC-"

#: 標準書IDの採番系列名 (IdSequence.name)。
DOCUMENT_SEQUENCE = "document_id"


def _highest_document_number(db: Session) -> int:
    """現存する document_id のうち最大の番号。1件も無ければ 0。

    カウンタをまだ持たない既存DBを引き継ぐときの初期値に使う。
    """
    highest = 0
    for value in db.scalars(select(StandardDocument.document_id)).all():
        if not value or not value.startswith(DOCUMENT_ID_PREFIX):
            continue
        suffix = value[len(DOCUMENT_ID_PREFIX) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


def next_document_id(db: Session) -> str:
    """次の標準書ID。採番カウンタ (IdSequence) から払い出す。

    現存レコードの最大値ではなくカウンタから採るのは、削除で番号が巻き戻らない
    ようにするため。巻き戻ると、既に出力済みの成果物が指すIDを別の標準書が
    名乗ることになり、トレーサビリティが崩れる。

    カウンタが無いDB (この仕組みより前に作られたもの) では、現存する
    document_id の最大から始める。その時点で全件削除されていた場合に限り、
    過去に使った番号を一度だけ再利用しうる。

    払い出しはカウンタの読み書きなので、同時に登録すると両者が同じ番号を採る
    余地が残る。衝突は document_id の一意制約が弾き、採り直しは
    api/documents.py の _create_document が行う。カウンタの更新も採番した
    標準書と同じトランザクションに入るため、やり直せば整合する。
    """
    sequence = db.get(IdSequence, DOCUMENT_SEQUENCE)
    if sequence is None:
        sequence = IdSequence(name=DOCUMENT_SEQUENCE, value=_highest_document_number(db))
        db.add(sequence)
        db.flush()

    sequence.value += 1
    return f"{DOCUMENT_ID_PREFIX}{sequence.value:03d}"


def _preserved_review_state(db: Session, document_pk: int) -> dict[str, dict[str, str]]:
    """再解析でレビュー結果を消さないため、Check ID をキーに退避する。"""
    rows = db.scalars(select(ChecklistItem).where(ChecklistItem.document_pk == document_pk)).all()
    return {
        r.check_id: {
            "result": r.result,
            "evidence": r.evidence,
            "reviewer": r.reviewer,
            "review_date": r.review_date,
            "comment": r.comment,
        }
        for r in rows
        if r.result != "Pending" or r.evidence or r.reviewer or r.comment
    }


def analyze_document(db: Session, document: StandardDocument) -> CoverageResult:
    """STEP 2-14 を実行し、結果を DB に書き込む。"""
    data = Path(document.stored_path).read_bytes()
    parsed = parse_document(document.original_filename, data)

    # --- STEP 2: 文書構造解析 ---
    located = assign_structure(parsed.blocks)
    document.block_count = len(located)
    document.has_page_numbers = any(item.page is not None for item in located)

    # --- STEP 3-6: 規定候補抽出 / 分類 / 要求事項化 ---
    settings = get_settings()
    classify = llm_classify.build_assist(
        settings.llm_classify_enabled, settings.llm_classify_cache_path
    )
    extracted = extract_rules(located, classify)

    preserved = _preserved_review_state(db, document.id)

    # 既存の解析結果は作り直す
    for old_rule in db.scalars(select(Rule).where(Rule.document_pk == document.id)).all():
        db.delete(old_rule)
    for old_run in db.scalars(
        select(AnalysisRun).where(AnalysisRun.document_pk == document.id)
    ).all():
        db.delete(old_run)
    db.flush()

    prefix = document.id_prefix

    # --- STEP 4: 規定ID付与 ---
    rule_rows: list[Rule] = []
    for seq, item in enumerate(extracted, start=1):
        rule = Rule(
            document_pk=document.id,
            standard_id=f"STD-{prefix}-{seq:03d}",
            rule_type=item.rule_type,
            category=item.category,
            original_rule=item.original_rule,
            normalized_requirement=item.normalized_requirement,
            chapter=item.chapter,
            section=item.section,
            page=item.page,
            heading_path=item.heading_path,
            locator=item.locator,
            condition=item.condition,
            exception=item.exception,
            ambiguity=item.ambiguity,
            notes=item.notes or "",
            explicit_severity=item.explicit_severity,
            matched_markers=item.matched_markers,
            order_index=item.order,
        )
        db.add(rule)
        rule_rows.append(rule)
    db.flush()

    # --- STEP 7: Atomic Check 分解 ---
    # 設定と資格情報が揃っているときだけ AI補助を使う。無ければルールベースのまま。
    settings = get_settings()
    assist = llm_split.build_assist(settings.llm_split_enabled, settings.llm_split_cache_path)

    pending: list[tuple[Rule, AtomicCheck]] = []
    for rule, item in zip(rule_rows, extracted, strict=True):
        checks, reason = checks_for_rule(item, assist=assist)
        if reason is not None:
            rule.unconverted_reason = reason
            continue
        for check in checks:
            pending.append((rule, check))

    # --- STEP 11: 重複整理 (完全重複のみ統合、類似は候補として報告) ---
    groups, merged_indexes = find_duplicates([c.check_point for _, c in pending])

    # --- STEP 8: チェックID付与 ---
    index_to_check_id: dict[int, str] = {}
    kept: list[tuple[int, Rule, AtomicCheck]] = []
    seq = 0
    for idx, (rule, check) in enumerate(pending):
        if idx in merged_indexes:
            continue
        seq += 1
        index_to_check_id[idx] = f"CHK-{prefix}-{seq:03d}"
        kept.append((idx, rule, check))

    duplicate_candidates = 0
    for idx, rule, check in kept:
        group = next((g for g in groups if g.representative_index == idx), None)
        merged_ids: list[str] = []
        extra_standard_ids: list[str] = []
        similar_ids: list[str] = []
        if group is not None:
            for dup_idx in group.exact_duplicates:
                dup_rule = pending[dup_idx][0]
                merged_ids.append(dup_rule.standard_id)
                if dup_rule.standard_id != rule.standard_id:
                    extra_standard_ids.append(dup_rule.standard_id)
                # 統合された側の規定も変換済みとして扱う (出典は複数保持: STEP 11)
                dup_rule.unconverted_reason = None
            for sim_idx, ratio in group.similar:
                # 同一規定を Atomic 分解した兄弟同士は定義上別の確認事項なので重複候補にしない
                if pending[sim_idx][0].id == rule.id:
                    continue
                sim_id = index_to_check_id.get(sim_idx)
                if sim_id:
                    similar_ids.append(f"{sim_id} ({ratio})")
                    duplicate_candidates += 1

        # --- STEP 10: 重要度設定 ---
        severity, reason = decide_severity(
            text=f"{rule.original_rule} {check.check_point}",
            category=rule.category,
            rule_type=rule.rule_type,
            explicit_severity=rule.explicit_severity,
        )

        # --- STEP 9: 属性付与 ---
        check_id = index_to_check_id[idx]
        state = preserved.get(check_id, {})
        db.add(
            ChecklistItem(
                document_pk=document.id,
                rule_pk=rule.id,
                check_id=check_id,
                no=seq_of(check_id),
                category=rule.category,
                sub_category=check.sub_category,
                check_point=check.check_point,
                requirement=check.requirement,
                severity=severity,
                severity_reason=reason,
                condition=check.condition,
                exception=check.exception,
                note=check.note,
                merged_check_ids=merged_ids,
                similar_check_ids=similar_ids,
                extra_standard_ids=extra_standard_ids,
                result=state.get("result", "Pending"),
                evidence=state.get("evidence", ""),
                reviewer=state.get("reviewer", ""),
                review_date=state.get("review_date", ""),
                comment=state.get("comment", ""),
            )
        )
    db.flush()

    # --- STEP 13: Coverage 検証 ---
    result = compute_coverage(
        rule_rows, check_count=len(kept), duplicate_candidates=duplicate_candidates
    )

    db.add(
        AnalysisRun(
            document_pk=document.id,
            total_rules=result.total_rules,
            target_rules=result.target_rules,
            converted_rules=result.converted_rules,
            unconverted_rules=result.unconverted_rules,
            coverage=result.coverage,
            mandatory_total=result.mandatory_total,
            mandatory_converted=result.mandatory_converted,
            prohibited_total=result.prohibited_total,
            prohibited_converted=result.prohibited_converted,
            ambiguous_rules=result.ambiguous_rules,
            missing_source_rules=result.missing_source_rules,
            duplicate_candidates=result.duplicate_candidates,
            check_count=result.check_count,
        )
    )
    document.status = "analyzed"
    document.error_message = None
    document.analyzed_at = datetime.now(timezone.utc)
    document.file_format = parsed.meta.get("format", document.file_format)
    db.commit()
    return result


def seq_of(check_id: str) -> int:
    return int(check_id.rsplit("-", 1)[1])
