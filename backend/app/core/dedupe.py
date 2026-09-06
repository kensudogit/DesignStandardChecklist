"""STEP 11: 重複整理。

完全重複のみ自動統合し、類似は「候補」として報告するに留める
(勝手に削って規定を落とさないため)。統合時は出典を複数保持する。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

#: 類似と見なす下限。これを超えても自動統合はせず「候補」として報告するだけ。
#: 下げすぎると無関係な規定が候補に並び、確認の手間がかえって増える。
SIMILAR_THRESHOLD = 0.88


def normalize_for_compare(text: str) -> str:
    """比較用に表記を揃える。

    全角/半角、空白、句読点や括弧の違いだけで別物と判定されるのを防ぐ。
    ここで落とすのは表記の揺れだけで、語そのものは変えない。
    """
    s = unicodedata.normalize("NFKC", text)
    s = re.sub(r"[\s　]+", "", s)
    s = re.sub(r"[。、,.・「」『』()（）\"']", "", s)
    return s.lower()


@dataclass
class DuplicateGroup:
    """1つの代表チェックと、そこへ統合された/類似すると判定された仲間。"""

    representative_index: int
    exact_duplicates: list[int] = field(default_factory=list)
    similar: list[tuple[int, float]] = field(default_factory=list)


def find_duplicates(check_points: list[str]) -> tuple[list[DuplicateGroup], set[int]]:
    """(グループ一覧, 完全重複として除外すべきindex集合) を返す。"""
    groups: list[DuplicateGroup] = []
    merged: set[int] = set()
    by_norm: dict[str, int] = {}

    for i, cp in enumerate(check_points):
        norm = normalize_for_compare(cp)
        if norm in by_norm:
            rep = by_norm[norm]
            group = next(g for g in groups if g.representative_index == rep)
            group.exact_duplicates.append(i)
            merged.add(i)
            continue
        by_norm[norm] = i
        groups.append(DuplicateGroup(representative_index=i))

    # 類似判定は残った代表同士のみ (O(n^2) を抑える)
    reps = [g.representative_index for g in groups]
    norms = {i: normalize_for_compare(check_points[i]) for i in reps}
    for a_pos, a in enumerate(reps):
        for b in reps[a_pos + 1 :]:
            na, nb = norms[a], norms[b]
            # 長さが大きく違う組は類似になりえない。重い比較の前に落とす
            if abs(len(na) - len(nb)) > max(len(na), len(nb)) * 0.4:
                continue
            ratio = SequenceMatcher(None, na, nb).ratio()
            if ratio >= SIMILAR_THRESHOLD:
                group = next(g for g in groups if g.representative_index == a)
                group.similar.append((b, round(ratio, 3)))
    return groups, merged
