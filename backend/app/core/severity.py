"""STEP 10: 重要度設定。標準書に明示があればそれを最優先する。"""

from __future__ import annotations

from app.core import taxonomy as tx


def decide_severity(
    *,
    text: str,
    category: str,
    rule_type: str,
    explicit_severity: str | None = None,
) -> tuple[str, str]:
    """(severity, 判定根拠) を返す。"""
    if explicit_severity:
        return explicit_severity, "標準書に重要度の明示あり"

    haystack = f"{category} {text}"

    hit = next((k for k in tx.CRITICAL_KEYWORDS if k in haystack), None)
    if hit:
        return "Critical", f"Critical観点キーワード「{hit}」に該当"

    if rule_type == "Prohibited":
        return "High", "禁止規定"

    if rule_type in ("Mandatory", "Conditional Mandatory"):
        hit = next((k for k in tx.HIGH_KEYWORDS if k in haystack), None)
        if hit:
            return "High", f"必須規定かつHigh観点キーワード「{hit}」に該当"
        return "High", "必須規定"

    if rule_type == "Recommended":
        hit = next((k for k in tx.MEDIUM_KEYWORDS if k in haystack), None)
        if hit:
            return "Medium", f"推奨規定かつ品質観点キーワード「{hit}」に該当"
        return "Low", "推奨規定"

    if rule_type == "Optional":
        return "Low", "任意規定"

    return "Medium", "参考規定"
