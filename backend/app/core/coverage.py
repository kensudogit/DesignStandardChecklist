"""STEP 13: Coverage 検証。

Coverage = チェック項目化済み対象規定数 / チェック対象規定総数 * 100
必須・禁止・条件付き必須は 100% を目標とする。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core import taxonomy as tx


@dataclass
class CoverageResult:
    """Coverage の算出結果。findings は画面と Markdown 出力の両方で使う。"""
    total_rules: int = 0
    target_rules: int = 0
    converted_rules: int = 0
    unconverted_rules: int = 0
    coverage: float = 0.0
    by_rule_type: dict[str, dict[str, int | float]] = field(default_factory=dict)
    mandatory_total: int = 0
    mandatory_converted: int = 0
    prohibited_total: int = 0
    prohibited_converted: int = 0
    ambiguous_rules: int = 0
    missing_source_rules: int = 0
    duplicate_candidates: int = 0
    check_count: int = 0
    findings: list[str] = field(default_factory=list)

    @property
    def mandatory_coverage(self) -> float:
        return _pct(self.mandatory_converted, self.mandatory_total)

    @property
    def prohibited_coverage(self) -> float:
        return _pct(self.prohibited_converted, self.prohibited_total)


def _pct(num: int, den: int) -> float:
    """百分率。分母が 0 なら 100% とする。

    「対象となる規定が1件も無い」のは未達ではないため。0% にすると、
    禁止規定を含まない標準書が常に警告を出してしまう。
    """
    if den == 0:
        return 100.0
    return round(num / den * 100, 1)


def compute_coverage(
    rules: list,
    check_count: int,
    duplicate_candidates: int = 0,
) -> CoverageResult:
    """rules は Rule モデル (または同じ属性を持つオブジェクト) のリスト。"""
    res = CoverageResult(check_count=check_count, duplicate_candidates=duplicate_candidates)
    res.total_rules = len(rules)

    per_type: dict[str, list] = {}
    for rule in rules:
        per_type.setdefault(rule.rule_type, []).append(rule)

    for rule_type, items in sorted(per_type.items()):
        converted = sum(1 for r in items if not r.unconverted_reason)
        res.by_rule_type[rule_type] = {
            "total": len(items),
            "converted": converted,
            "unconverted": len(items) - converted,
            "coverage": _pct(converted, len(items)),
        }

    # Coverage の分母は「チェック対象の規範レベル」に限る。参考記述まで含めると率が薄まる
    target = [r for r in rules if r.rule_type in tx.TARGET_RULE_TYPES]
    res.target_rules = len(target)
    res.converted_rules = sum(1 for r in target if not r.unconverted_reason)
    res.unconverted_rules = res.target_rules - res.converted_rules
    res.coverage = _pct(res.converted_rules, res.target_rules)

    mandatory = [r for r in rules if r.rule_type in ("Mandatory", "Conditional Mandatory")]
    res.mandatory_total = len(mandatory)
    res.mandatory_converted = sum(1 for r in mandatory if not r.unconverted_reason)

    prohibited = [r for r in rules if r.rule_type == "Prohibited"]
    res.prohibited_total = len(prohibited)
    res.prohibited_converted = sum(1 for r in prohibited if not r.unconverted_reason)

    res.ambiguous_rules = sum(1 for r in rules if r.ambiguity)
    res.missing_source_rules = sum(
        1 for r in rules if not r.chapter and not r.section and r.page is None and not r.locator
    )

    if res.mandatory_coverage < 100:
        res.findings.append(
            f"必須規定のCoverageが{res.mandatory_coverage}%です。目標100%に対し未達です。"
        )
    if res.prohibited_coverage < 100:
        res.findings.append(
            f"禁止規定のCoverageが{res.prohibited_coverage}%です。目標100%に対し未達です。"
        )
    if res.ambiguous_rules:
        res.findings.append(
            f"曖昧表現を含む規定が{res.ambiguous_rules}件あります。判定基準の明確化が必要です。"
        )
    if res.missing_source_rules:
        res.findings.append(
            f"出典 (章・節・ページ) を特定できない規定が{res.missing_source_rules}件あります。"
            "ページ番号は推測せず「不明」として扱っています。"
        )
    if res.duplicate_candidates:
        res.findings.append(
            f"類似チェック項目の候補が{res.duplicate_candidates}件あります。統合可否を確認してください。"
        )
    # 指摘が1つも無いときも、確認済みであることが分かるよう1行残す
    if not res.findings:
        res.findings.append("必須・禁止規定のCoverageは100%です。未変換・曖昧・出典欠落もありません。")
    return res
