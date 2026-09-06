/**
 * 一覧表で使う色付きラベル。表示だけを担当し、状態は持たない。
 *
 * 実際の色は `app/globals.css` のクラス定義側にある。
 */

import type { ResultValue, Severity } from "@/lib/types";

/** 重要度 → CSS クラス。4段階以外は来ない想定。 */
const SEVERITY_CLASS: Record<Severity, string> = {
  Critical: "badge badge-critical",
  High: "badge badge-high",
  Medium: "badge badge-medium",
  Low: "badge badge-low",
};

/** レビュー結果 → CSS クラス。 */
const RESULT_CLASS: Record<ResultValue, string> = {
  OK: "badge badge-ok",
  NG: "badge badge-ng",
  "N/A": "badge badge-na",
  Pending: "badge badge-pending",
};

/**
 * 重要度ラベル。`title` には重要度の判定理由を渡してツールチップに出す。
 *
 * 型の上では `SEVERITY_CLASS[severity]` は必ず値を持つが、サーバが未知の値を
 * 返した場合に無地のラベルへ落とすため `??` を残している。
 */
export function SeverityBadge({
  severity,
  title,
}: {
  severity: Severity;
  title?: string;
}) {
  return (
    <span className={SEVERITY_CLASS[severity] ?? "badge badge-neutral"} title={title}>
      {severity}
    </span>
  );
}

export function ResultBadge({ result }: { result: ResultValue }) {
  return <span className={RESULT_CLASS[result] ?? "badge badge-neutral"}>{result}</span>;
}

/**
 * 規定種別ラベル。
 *
 * 禁止規定を最も強い色にしているのは、見落とすとレビューが成立しないため。
 * 必須・条件付き必須はその次に強い色で揃えている。
 */
export function RuleTypeBadge({ ruleType }: { ruleType: string }) {
  const className =
    ruleType === "Prohibited"
      ? "badge badge-critical"
      : ruleType === "Mandatory" || ruleType === "Conditional Mandatory"
        ? "badge badge-high"
        : ruleType === "Recommended"
          ? "badge badge-medium"
          : "badge badge-neutral";
  return <span className={className}>{ruleType}</span>;
}
