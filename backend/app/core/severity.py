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
    # 標準書に書いてあるものが最優先。推定は書かれていないときの代替手段にすぎない
    if explicit_severity:
        return explicit_severity, "標準書に重要度の明示あり"

    # 分類名にも観点語が現れる (例: 分類「セキュリティ」)。本文と併せて見る
    haystack = f"{category} {text}"

    hit = next((k for k in tx.CRITICAL_KEYWORDS if k in haystack), None)
    if hit:
        return "Critical", f"Critical観点キーワード「{hit}」に該当"

    # 禁止規定は違反時の影響が大きいので、キーワードが無くても High 以上に置く
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

    # 規範レベルを判定できなかった規定。落とさず中位に置いて人の目に触れさせる
    return "Medium", "参考規定"
