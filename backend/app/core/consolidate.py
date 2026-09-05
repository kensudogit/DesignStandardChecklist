"""複数標準書の横断チェックリスト（SKILL.md 10. 実行例その2）。

1. 標準書別に規定を抽出   … 各文書の解析結果をそのまま使う
2. 規定IDは文書種別ごと   … STD-UI-xxx / STD-DD-xxx のまま変えない
3. 横断的に重複を分析     … 文書をまたいだ完全重複を統合、類似は候補として報告
4. 統合チェックリスト生成
5. 各チェック項目に複数出典を紐付ける
6. 標準書別Coverageも算出

チェックIDは各文書のものを維持する。統合表だけの新しいID体系を作ると、
文書別チェックリストとの対応が1段増えて追跡しにくくなるため。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.dedupe import find_duplicates
from app.models import ChecklistItem, StandardDocument

SEVERITY_ORDER = ("Critical", "High", "Medium", "Low")


@dataclass
class ConsolidatedRow:
    """統合チェックリストの1行（DB書き込み前の形）。"""

    primary: ChecklistItem
    merged: list[ChecklistItem] = field(default_factory=list)
    similar_check_ids: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        """統合した項目の中で最も重い重要度を採る（軽い方に引きずられない）。"""
        severities = [self.primary.severity, *(m.severity for m in self.merged)]
        return min(
            severities,
            key=lambda s: SEVERITY_ORDER.index(s) if s in SEVERITY_ORDER else len(SEVERITY_ORDER),
        )

    @property
    def all_items(self) -> list[ChecklistItem]:
        return [self.primary, *self.merged]


def consolidate(
    items_by_document: list[tuple[StandardDocument, list[ChecklistItem]]],
) -> list[ConsolidatedRow]:
    """文書順・No順に並べた統合行を返す。"""
    flat: list[ChecklistItem] = []
    for _, items in items_by_document:
        flat.extend(items)

    groups, merged_indexes = find_duplicates([item.check_point for item in flat])

    index_of_row: dict[int, int] = {}
    rows: list[ConsolidatedRow] = []
    for index, item in enumerate(flat):
        if index in merged_indexes:
            continue
        index_of_row[index] = len(rows)
        rows.append(ConsolidatedRow(primary=item))

    for group in groups:
        row_index = index_of_row.get(group.representative_index)
        if row_index is None:
            continue
        row = rows[row_index]
        for dup_index in group.exact_duplicates:
            row.merged.append(flat[dup_index])
        for similar_index, ratio in group.similar:
            similar = flat[similar_index]
            # 同一文書内の類似は文書別チェックリスト側で既に報告済み
            if similar.document_pk == row.primary.document_pk:
                continue
            row.similar_check_ids.append(f"{similar.check_id} ({ratio})")

    return rows


def sources_of(row: ConsolidatedRow, name_by_document_pk: dict[int, str]) -> list[dict[str, str]]:
    """STEP 12: 1チェック項目に紐づく出典（複数標準書に跨りうる）。"""
    out: list[dict[str, str]] = []
    for item in row.all_items:
        rule = item.rule
        page = rule.page if rule.page is not None else rule.locator
        out.append(
            {
                "check_id": item.check_id,
                "standard_id": rule.standard_id,
                "source_document": name_by_document_pk.get(item.document_pk, "不明"),
                "chapter": rule.chapter or "不明",
                "section": rule.section or "不明",
                "page": str(page) if page else "不明",
            }
        )
    return out
