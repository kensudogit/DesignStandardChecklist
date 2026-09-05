import type { ResultValue, Severity } from "@/lib/types";

const SEVERITY_CLASS: Record<Severity, string> = {
  Critical: "badge badge-critical",
  High: "badge badge-high",
  Medium: "badge badge-medium",
  Low: "badge badge-low",
};

const RESULT_CLASS: Record<ResultValue, string> = {
  OK: "badge badge-ok",
  NG: "badge badge-ng",
  "N/A": "badge badge-na",
  Pending: "badge badge-pending",
};

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
