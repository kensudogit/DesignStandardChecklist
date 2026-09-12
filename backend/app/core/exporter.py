"""STEP 14: 最終出力。

skill/templates/*.csv の列構成をそのまま守る。
CSV は Excel で開けるよう UTF-8 BOM + CRLF で出力する。
出典が取得できなかった箇所は空欄ではなく「不明」を入れる (推測しない)。
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from app.core import taxonomy as tx
from app.core.coverage import CoverageResult
from app.models import AnalysisRun, ChecklistItem, Rule, StandardDocument

#: 出典等を取得できなかったときに入れる語。空欄との区別を付けるため文字列で持つ。
UNKNOWN = "不明"

#: 以降の *_COLUMNS は skill/templates/*.csv の列と順序をそのまま写したもの。
#: テンプレートと列がずれると既存のレビュー運用が壊れるため、並べ替え・改名はしない。
CHECKLIST_COLUMNS = [
    "No",
    "Check ID",
    "Category",
    "Sub Category",
    "Check Point",
    "Severity",
    "Requirement",
    "Standard ID",
    "Source Document",
    "Chapter",
    "Section",
    "Page",
    "Condition",
    "Exception",
    "Result",
    "Evidence",
    "Reviewer",
    "Review Date",
    "Comment",
]

EXTRACTED_RULES_COLUMNS = [
    "Standard ID",
    "Rule Type",
    "Category",
    "Original Rule",
    "Normalized Requirement",
    "Source Document",
    "Chapter",
    "Section",
    "Page",
    "Condition",
    "Exception",
    "Ambiguity",
    "Notes",
]

STANDARD_REGISTER_COLUMNS = [
    "Document ID",
    "Document Name",
    "Document Type",
    "Version",
    "Established Date",
    "Revised Date",
    "Target Phase",
    "Target Deliverable",
    "Notes",
]

TRACEABILITY_COLUMNS = [
    "Check ID",
    "Standard ID",
    "Source Document",
    "Chapter",
    "Section",
    "Page",
    "Trace Status",
    "Notes",
]

UNCONVERTED_COLUMNS = [
    "Standard ID",
    "Original Rule",
    "Reason Not Converted",
    "Required Action",
    "Owner",
    "Status",
]


def _csv(columns: list[str], rows: list[list[str]]) -> str:
    """CSV 文字列を組み立てる。

    先頭に付けている U+FEFF は UTF-8 BOM。付けないと Excel が Shift_JIS と
    誤認して日本語が文字化けする。改行を CRLF にしているのも Excel に合わせるため。
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return "﻿" + buf.getvalue()


def _blank(value: object) -> str:
    """空なら「不明」に置き換える。

    出典や版数など、取得できなかったことを明示したい項目に使う。空欄のままだと
    「取得できなかった」のか「そもそも記載が無い」のかを読み手が判別できない。
    """
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def _plain(value: object) -> str:
    """空を空のまま通す。備考など、無いことが自然な項目に使う。"""
    return "" if value is None else str(value)


def standard_register_csv(documents: list[StandardDocument]) -> str:
    """STEP 1 の成果物: 標準書一覧。登録済みの標準書をそのまま並べる。"""
    rows = [
        [
            d.document_id,
            d.document_name,
            tx.DOC_TYPE_LABEL.get(d.document_type, d.document_type),
            _blank(d.version),
            _blank(d.established_date),
            _blank(d.revised_date),
            _blank(d.target_phase),
            _blank(d.target_deliverable),
            _plain(d.notes),
        ]
        for d in documents
    ]
    return _csv(STANDARD_REGISTER_COLUMNS, rows)


def extracted_rules_csv(document: StandardDocument, rules: list[Rule]) -> str:
    """STEP 3-6 の成果物: 規定抽出一覧。チェックリストの手前にある中間成果物。

    原文と正規化後の要求事項を並べて出すので、変換が妥当かをここで確認できる。
    """
    rows = [
        [
            r.standard_id,
            r.rule_type,
            f"{r.category}/{r.heading_path.split(' > ')[-1]}" if r.heading_path else r.category,
            r.original_rule,
            r.normalized_requirement,
            document.document_name,
            _blank(r.chapter),
            _blank(r.section),
            _blank(r.page if r.page is not None else r.locator),
            _plain(r.condition),
            _plain(r.exception),
            _plain(r.ambiguity),
            _plain(r.notes),
        ]
        for r in rules
    ]
    return _csv(EXTRACTED_RULES_COLUMNS, rows)


def checklist_csv(document: StandardDocument, items: list[tuple[ChecklistItem, Rule]]) -> str:
    """STEP 14 の主成果物: レビューチェックリスト。

    レビュー記入欄 (Result/Evidence/Reviewer/Review Date/Comment) は、画面で
    記入済みならその値を、未記入なら空のまま出す。Excel 上で続きを記入できる。
    """
    rows = []
    for item, rule in items:
        standard_ids = ";".join([rule.standard_id, *item.extra_standard_ids])
        rows.append(
            [
                str(item.no),
                item.check_id,
                item.category,
                _plain(item.sub_category),
                item.check_point,
                item.severity,
                item.requirement,
                standard_ids,
                document.document_name,
                _blank(rule.chapter),
                _blank(rule.section),
                _blank(rule.page if rule.page is not None else rule.locator),
                _plain(item.condition),
                _plain(item.exception),
                item.result,
                _plain(item.evidence),
                _plain(item.reviewer),
                _plain(item.review_date),
                _plain(item.comment),
            ]
        )
    return _csv(CHECKLIST_COLUMNS, rows)


def traceability_csv(document: StandardDocument, items: list[tuple[ChecklistItem, Rule]]) -> str:
    """STEP 12 の成果物: トレーサビリティマトリクス。

    Check ID から出典までを1行で追えるようにする。出典が欠けている行は
    Trace Status で分かるようにし、ページ番号を推測して埋めることはしない。
    """
    rows = []
    for item, rule in items:
        has_source = bool(rule.chapter or rule.section or rule.page is not None or rule.locator)
        status = "Traced" if has_source else "Source Unknown"
        notes = []
        if item.extra_standard_ids:
            notes.append("複数標準由来: " + ";".join(item.extra_standard_ids))
        if item.merged_check_ids:
            notes.append("重複統合元: " + ";".join(item.merged_check_ids))
        if item.similar_check_ids:
            notes.append("類似候補: " + ";".join(item.similar_check_ids))
        if not has_source:
            notes.append("出典を特定できないため推測せず不明とした")
        rows.append(
            [
                item.check_id,
                ";".join([rule.standard_id, *item.extra_standard_ids]),
                document.document_name,
                _blank(rule.chapter),
                _blank(rule.section),
                _blank(rule.page if rule.page is not None else rule.locator),
                status,
                " / ".join(notes),
            ]
        )
    return _csv(TRACEABILITY_COLUMNS, rows)


def unconverted_rules_csv(rules: list[Rule]) -> str:
    """STEP 13 の成果物: 未変換規定一覧。

    チェック項目にできなかった規定を理由付きで残す。Coverage が 100% でない
    ときの内訳がここに出る。
    """
    rows = []
    for r in rules:
        if not r.unconverted_reason:
            continue
        action = (
            "標準書の判定基準を確認し、チェック項目化の可否を判断する"
            if r.ambiguity
            else "規定文を分割・具体化したうえで再解析する"
        )
        rows.append([r.standard_id, r.original_rule, r.unconverted_reason, action, "", "Open"])
    return _csv(UNCONVERTED_COLUMNS, rows)


def checklist_markdown(document: StandardDocument, items: list[tuple[ChecklistItem, Rule]]) -> str:
    """チェックリストの Markdown 版。CSV と同じ内容を、そのまま読める形で出す。"""
    header = (
        "| No | Check ID | Category | Sub Category | Check Point | Severity | Standard ID | "
        "Source Document | Chapter | Section | Page | Condition | Exception | Result | Evidence | "
        "Reviewer | Review Date | Comment |"
    )
    sep = "|---:|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|"
    lines = [f"# Design Review Checklist — {document.document_name}", "", header, sep]
    for item, rule in items:
        cells = [
            str(item.no),
            item.check_id,
            item.category,
            _plain(item.sub_category),
            item.check_point,
            item.severity,
            ";".join([rule.standard_id, *item.extra_standard_ids]),
            document.document_name,
            _blank(rule.chapter),
            _blank(rule.section),
            _blank(rule.page if rule.page is not None else rule.locator),
            _plain(item.condition),
            _plain(item.exception),
            item.result,
            _plain(item.evidence),
            _plain(item.reviewer),
            _plain(item.review_date),
            _plain(item.comment),
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"


def coverage_markdown(
    document: StandardDocument,
    run: AnalysisRun | None,
    result: CoverageResult | None = None,
) -> str:
    if result is None and run is None:
        return "# Coverage Report\n\n解析が未実行です。\n"

    if result is None and run is not None:
        result = CoverageResult(
            total_rules=run.total_rules,
            target_rules=run.target_rules,
            converted_rules=run.converted_rules,
            unconverted_rules=run.unconverted_rules,
            coverage=run.coverage,
            mandatory_total=run.mandatory_total,
            mandatory_converted=run.mandatory_converted,
            prohibited_total=run.prohibited_total,
            prohibited_converted=run.prohibited_converted,
            ambiguous_rules=run.ambiguous_rules,
            missing_source_rules=run.missing_source_rules,
            duplicate_candidates=run.duplicate_candidates,
            check_count=run.check_count,
        )
    assert result is not None

    generated = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Coverage Report",
        "",
        f"- Source document: {document.document_name}",
        f"- Document type: {tx.DOC_TYPE_LABEL.get(document.document_type, document.document_type)}",
        f"- Generated: {generated}",
        "",
        "## Summary",
        "",
        f"- Total extracted rules: {result.total_rules}",
        f"- Total target rules: {result.target_rules}",
        f"- Converted rules: {result.converted_rules}",
        f"- Unconverted rules: {result.unconverted_rules}",
        f"- Generated check items: {result.check_count}",
        f"- Mandatory rules: {result.mandatory_total}",
        f"- Mandatory converted: {result.mandatory_converted}",
        f"- Prohibited rules: {result.prohibited_total}",
        f"- Prohibited converted: {result.prohibited_converted}",
        "",
        "## Coverage Formula",
        "",
        "Coverage = Converted target rules / Total target rules * 100",
        "",
        f"**Coverage = {result.converted_rules} / {result.target_rules} * 100 = {result.coverage}%**",
        "",
        "## Mandatory Coverage",
        "",
        f"Target: 100% / Actual: {result.mandatory_coverage}%",
        "",
        "## Prohibited Coverage",
        "",
        f"Target: 100% / Actual: {result.prohibited_coverage}%",
        "",
        "## Coverage by Rule Type",
        "",
        "| Rule Type | Total | Converted | Unconverted | Coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    for rule_type, stats in result.by_rule_type.items():
        lines.append(
            f"| {rule_type} | {stats['total']} | {stats['converted']} | "
            f"{stats['unconverted']} | {stats['coverage']}% |"
        )
    lines += [
        "",
        "## Findings",
        "",
        f"- Unconverted: {result.unconverted_rules}",
        f"- Ambiguous: {result.ambiguous_rules}",
        f"- Missing source references: {result.missing_source_rules}",
        f"- Duplicate candidates: {result.duplicate_candidates}",
        "",
    ]
    lines += [f"- {f}" for f in result.findings]
    lines.append("")
    if not document.has_page_numbers:
        lines += [
            "## Note",
            "",
            "この文書形式ではページ番号を取得できないため、Page 列は「不明」としています。"
            "推測によるページ番号の付与は行いません。",
            "",
        ]
    return "\n".join(lines)


# --- AI推奨事項 (必須原則 8: 標準由来と分離した専用成果物) --------------------

AI_RECOMMENDATION_COLUMNS = [
    "Recommendation ID",
    "No",
    "Category",
    "Sub Category",
    "Check Point",
    "Severity",
    "Requirement",
    "Rationale",
    "Generator",
    "Origin",
    "Adoption",
    "Comment",
]

#: AI推奨事項の出力に必ず入れる由来表記。標準書由来と取り違えられないようにする。
AI_ORIGIN = "AI推奨（標準書由来ではない）"


def ai_recommendations_csv(document: StandardDocument, rows: list) -> str:
    """AI推奨事項の CSV。標準由来の成果物とは別ファイルにする。

    rows は Recommendation モデルのリスト。同じ ZIP に入れても取り違えられないよう、
    全行に由来表記を入れている。

    Standard ID / Chapter / Section / Page の列を意図的に持たない。
    標準書に無い提案に出典を書けば、それは出典の捏造になる (禁止事項)。
    """
    body = [
        [
            r.recommendation_id,
            str(r.no),
            r.category,
            _plain(r.sub_category),
            r.check_point,
            r.severity,
            r.requirement,
            _plain(r.rationale),
            f"{r.generator} / {r.generator_detail}" if r.generator_detail else r.generator,
            AI_ORIGIN,
            r.adoption,
            _plain(r.comment),
        ]
        for r in rows
    ]
    return _csv(AI_RECOMMENDATION_COLUMNS, body)


def ai_recommendations_markdown(document: StandardDocument, rows: list) -> str:
    lines = [
        f"# AI推奨事項 — {document.document_name}",
        "",
        "> **これらは標準書由来ではありません。**",
        "> 標準書に規定が無い観点として提案したものです。出典（章・節・ページ）は持たず、",
        "> レビューチェックリスト・トレーサビリティ表・Coverage には含まれません。",
        "> 採用するかどうかはプロジェクトで判断してください。",
        "",
    ]
    if not rows:
        lines.append("生成された推奨事項はありません。")
        return "\n".join(lines) + "\n"

    lines += [
        "| Recommendation ID | Category | Check Point | Severity | 提案理由 | 生成方式 | 採否 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cells = [
            r.recommendation_id,
            r.category,
            r.check_point,
            r.severity,
            _plain(r.rationale),
            r.generator,
            r.adoption,
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"


# --- 統合レビュー表 (複数標準書の横断) ---------------------------------------

CONSOLIDATED_COLUMNS = [
    "No",
    "Check ID",
    "Category",
    "Sub Category",
    "Check Point",
    "Severity",
    "Requirement",
    "Standard IDs",
    "Source Documents",
    "Chapters",
    "Sections",
    "Pages",
    "Condition",
    "Exception",
    "Merged Check IDs",
    "Result",
    "Evidence",
    "Reviewer",
    "Review Date",
    "Comment",
]

CROSS_TRACEABILITY_COLUMNS = [
    "Check ID",
    "Standard ID",
    "Source Document",
    "Chapter",
    "Section",
    "Page",
    "Consolidated No",
    "Role",
]


def consolidated_checklist_csv(rows: list[dict]) -> str:
    """統合レビュー表の CSV。1行が複数の標準書を出典に持ちうる。

    rows は ConsolidatedCheckOut を dict 化したもの。
    """
    body = []
    for row in rows:
        sources = row["sources"]
        body.append(
            [
                str(row["no"]),
                row["check_id"],
                row["category"],
                _plain(row["sub_category"]),
                row["check_point"],
                row["severity"],
                row["requirement"],
                ";".join(s["standard_id"] for s in sources),
                ";".join(dict.fromkeys(s["source_document"] for s in sources)),
                ";".join(s["chapter"] for s in sources),
                ";".join(s["section"] for s in sources),
                ";".join(s["page"] for s in sources),
                _plain(row["condition"]),
                _plain(row["exception"]),
                ";".join(row["merged_check_ids"]),
                row["result"],
                _plain(row["evidence"]),
                _plain(row["reviewer"]),
                _plain(row["review_date"]),
                _plain(row["comment"]),
            ]
        )
    return _csv(CONSOLIDATED_COLUMNS, body)


def cross_traceability_csv(rows: list[dict]) -> str:
    """統合レビュー表のトレーサビリティ。

    統合チェック1行につき、出典となった標準書ごとに1行を出す。どの標準書の
    どの規定から来たかを全て並べるため、行数はチェック件数より多くなる。
    """
    body = []
    for row in rows:
        for index, source in enumerate(row["sources"]):
            body.append(
                [
                    source["check_id"],
                    source["standard_id"],
                    source["source_document"],
                    source["chapter"],
                    source["section"],
                    source["page"],
                    str(row["no"]),
                    "Primary" if index == 0 else "Merged",
                ]
            )
    return _csv(CROSS_TRACEABILITY_COLUMNS, body)


def consolidated_markdown(name: str, rows: list[dict]) -> str:
    lines = [
        f"# 統合レビューチェックリスト — {name}",
        "",
        "| No | Check ID | Category | Check Point | Severity | Standard IDs | Source Documents | Merged | Result | Comment |",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        sources = row["sources"]
        cells = [
            str(row["no"]),
            row["check_id"],
            row["category"],
            row["check_point"],
            row["severity"],
            ";".join(s["standard_id"] for s in sources),
            ";".join(dict.fromkeys(s["source_document"] for s in sources)),
            ";".join(row["merged_check_ids"]) or "—",
            row["result"],
            _plain(row["comment"]),
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"


def review_set_coverage_markdown(name: str, coverage: dict) -> str:
    lines = [
        f"# 横断Coverageレポート — {name}",
        "",
        "## 標準書別 Coverage",
        "",
        "| 標準書 | 種別 | 対象規定 | 変換済み | 未変換 | Coverage | 必須 | 禁止 | チェック項目 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in coverage["by_document"]:
        lines.append(
            f"| {row['document_name']} | {row['document_type_label']} | {row['target_rules']} | "
            f"{row['converted_rules']} | {row['unconverted_rules']} | {row['coverage']}% | "
            f"{row['mandatory_coverage']}% | {row['prohibited_coverage']}% | {row['check_count']} |"
        )
    lines += [
        "",
        "## 全体",
        "",
        f"- 対象規定総数: {coverage['total_target_rules']}",
        f"- チェック項目化済み: {coverage['total_converted_rules']}",
        f"- 全体Coverage: {coverage['total_coverage']}%",
        "",
        "## 統合による重複削減",
        "",
        f"- 統合前のチェック項目総数: {coverage['total_checks_before_merge']}",
        f"- 統合後のチェック項目数: {coverage['consolidated_checks']}",
        f"- 統合された重複項目: {coverage['merged_checks']}",
        f"- 標準書をまたぐ類似候補（未統合）: {coverage['cross_document_similar']}",
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {f}" for f in coverage["findings"]]
    lines.append("")
    return "\n".join(lines)
