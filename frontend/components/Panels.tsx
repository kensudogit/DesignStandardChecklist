"use client";

/**
 * 標準書ページのタブごとの中身をまとめたもの。
 *
 * ここにある表はいずれも読み取り専用で、レビュー結果の記入は
 * `ChecklistTable` 側が受け持つ。表示に徹しているため状態はほぼ持たない。
 */

import { useMemo, useState } from "react";

import { RuleTypeBadge } from "@/components/Badges";
import type {
  Coverage,
  ReviewProgress,
  Rule,
  TraceabilityRow,
  UnconvertedRow,
} from "@/lib/types";

/**
 * 抽出した規定の一覧 (STEP 3-6)。チェックリストの手前の中間成果物にあたる。
 *
 * チェック項目がどの原文から来たのかを確かめる用途で使う。
 */
export function RulesTable({ rules }: { rules: Rule[] }) {
  const [ruleType, setRuleType] = useState("");
  const types = useMemo(
    () => Array.from(new Set(rules.map((r) => r.rule_type))).sort(),
    [rules],
  );
  // 件数が多くないので useMemo は使わない。絞り込みは描画のたびに計算する
  const visible = rules.filter((r) => !ruleType || r.rule_type === ruleType);

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <div>
          <label htmlFor="f-ruletype">規範レベル</label>
          <select id="f-ruletype" value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
            <option value="">すべて</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div style={{ alignSelf: "flex-end" }} className="small muted">
          {visible.length} / {rules.length} 件
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Standard ID</th>
              <th>規範レベル</th>
              <th>分類</th>
              <th>標準書の原文</th>
              <th>要求事項</th>
              <th>出典</th>
              <th>条件 / 例外 / 曖昧</th>
              <th>チェックID</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((rule) => (
              <tr key={rule.id}>
                <td className="mono">{rule.standard_id}</td>
                <td>
                  <RuleTypeBadge ruleType={rule.rule_type} />
                </td>
                <td>{rule.category}</td>
                <td style={{ maxWidth: 420 }}>{rule.original_rule}</td>
                <td style={{ maxWidth: 340 }} className="small">
                  {rule.normalized_requirement}
                </td>
                <td className="small muted">
                  章 {rule.chapter ?? "不明"} ／ 節 {rule.section ?? "不明"} ／ ページ{" "}
                  {rule.page ?? rule.locator ?? "不明"}
                  {rule.heading_path && <div>{rule.heading_path}</div>}
                </td>
                <td className="small">
                  {rule.condition && <div>条件: {rule.condition}</div>}
                  {rule.exception && <div>例外: {rule.exception}</div>}
                  {rule.ambiguity && <div className="note">{rule.ambiguity}</div>}
                  {!rule.condition && !rule.exception && !rule.ambiguity && (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="mono small">
                  {/* 未変換の規定にはチェックIDが無い。空欄だと「表示漏れ」と区別が
                                        付かないので、未変換であることを明示する */}
                  {rule.unconverted_reason ? (
                    <span className="badge badge-ng">未変換</span>
                  ) : (
                    rule.check_ids.join(", ")
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/**
 * トレーサビリティ表 (STEP 12)。チェック項目 → 出典の追跡可否を一覧にする。
 *
 * 追跡できない項目があること自体は異常ではない。ページ番号を持てない文書形式
 * (Markdown 等) では出典が「不明」になるため。
 */
export function TraceabilityTable({ rows }: { rows: TraceabilityRow[] }) {
  const untraced = rows.filter((r) => r.trace_status !== "Traced").length;
  return (
    <>
      {untraced > 0 ? (
        <div className="alert alert-warn">
          出典を特定できないチェック項目が {untraced} 件あります。ページ番号や章節は推測せず
          「不明」として扱っています。
        </div>
      ) : (
        <div className="alert alert-info">
          すべてのチェック項目が Standard ID → 出典まで追跡可能です。
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Check ID</th>
              <th>Standard ID</th>
              <th>Source Document</th>
              <th>Chapter</th>
              <th>Section</th>
              <th>Page</th>
              <th>Trace Status</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.check_id}>
                <td className="mono">{row.check_id}</td>
                <td className="mono">{row.standard_id}</td>
                <td>{row.source_document}</td>
                <td>{row.chapter ?? "不明"}</td>
                <td>{row.section ?? "不明"}</td>
                <td>{row.page}</td>
                <td>
                  <span
                    className={row.trace_status === "Traced" ? "badge badge-ok" : "badge badge-pending"}
                  >
                    {row.trace_status}
                  </span>
                </td>
                <td className="small muted">{row.notes || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/**
 * 未変換規定の一覧 (STEP 13)。
 *
 * 曖昧な規定を無理にチェック項目化しない方針のため、ここが空でないのが通常。
 * 0件のときだけ表ではなく説明を出す。
 */
export function UnconvertedTable({ rows }: { rows: UnconvertedRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="alert alert-info">
        未変換の規定はありません。抽出した規定はすべてチェック項目化されています。
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Standard ID</th>
            <th>標準書の原文</th>
            <th>変換できない理由</th>
            <th>必要な対応</th>
            <th>Owner</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.standard_id}>
              <td className="mono">{row.standard_id}</td>
              <td style={{ maxWidth: 420 }}>{row.original_rule}</td>
              <td className="small">{row.reason_not_converted}</td>
              <td className="small">{row.required_action}</td>
              <td className="muted">{row.owner || "—"}</td>
              <td>
                <span className="badge badge-pending">{row.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * 数値1つを見せるタイル。`percent` を渡すとバーも出す。
 *
 * バーの色は 100% で緑、80% 未満で赤。必須・禁止規定は 100% が目標なので、
 * 達していないことがひと目で分かるようにしている。
 */
function Stat({
  label,
  value,
  sub,
  tone,
  percent,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "warn" | "bad";
  percent?: number;
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value${tone ? ` ${tone}` : ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
      {percent !== undefined && (
        <div className={`meter${percent >= 100 ? " good" : percent < 80 ? " bad" : ""}`}>
          {/* 丸め誤差で 100 をわずかに超えてもバーがはみ出さないよう挟み込む */}
          <span style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
        </div>
      )}
    </div>
  );
}

/**
 * Coverage とレビュー進捗のまとめ (STEP 13)。
 *
 * 全体の Coverage とは別に必須・禁止規定を独立したタイルにしているのは、
 * 全体が高くても必須が欠けていればレビューが成立しないため。
 */
export function CoveragePanel({
  coverage,
  progress,
}: {
  coverage: Coverage;
  progress: ReviewProgress | null;
}) {
  // 必須・禁止は 100% 未満なら無条件で赤。「おおむね達成」を許さない
  const mandatoryTone = coverage.mandatory_coverage >= 100 ? "good" : "bad";
  const prohibitedTone = coverage.prohibited_coverage >= 100 ? "good" : "bad";

  return (
    <>
      <section className="card">
        <h2>Coverage</h2>
        <p className="hint">
          Coverage = チェック項目化済み対象規定数 / チェック対象規定総数 × 100。
          必須・禁止規定は 100% を目標とします。
        </p>
        <div className="stat-grid">
          <Stat
            label="Coverage"
            value={`${coverage.coverage}%`}
            sub={`${coverage.converted_rules} / ${coverage.target_rules} 対象規定`}
            percent={coverage.coverage}
          />
          <Stat
            label="必須規定 Coverage（目標100%）"
            value={`${coverage.mandatory_coverage}%`}
            sub={`${coverage.mandatory_converted} / ${coverage.mandatory_total} 件`}
            tone={mandatoryTone}
            percent={coverage.mandatory_coverage}
          />
          <Stat
            label="禁止規定 Coverage（目標100%）"
            value={`${coverage.prohibited_coverage}%`}
            sub={`${coverage.prohibited_converted} / ${coverage.prohibited_total} 件`}
            tone={prohibitedTone}
            percent={coverage.prohibited_coverage}
          />
          <Stat label="抽出規定" value={String(coverage.total_rules)} sub="規定候補の総数" />
          <Stat label="チェック項目" value={String(coverage.check_count)} sub="Atomic Check 後" />
          <Stat
            label="未変換規定"
            value={String(coverage.unconverted_rules)}
            tone={coverage.unconverted_rules > 0 ? "warn" : "good"}
          />
          <Stat
            label="曖昧規定"
            value={String(coverage.ambiguous_rules)}
            sub="判定基準の明確化が必要"
            tone={coverage.ambiguous_rules > 0 ? "warn" : "good"}
          />
          <Stat
            label="出典欠落"
            value={String(coverage.missing_source_rules)}
            sub="章・節・ページ不明"
            tone={coverage.missing_source_rules > 0 ? "warn" : "good"}
          />
          <Stat
            label="重複候補"
            value={String(coverage.duplicate_candidates)}
            sub="統合可否の確認対象"
            tone={coverage.duplicate_candidates > 0 ? "warn" : "good"}
          />
        </div>
      </section>

      <section className="card">
        <h2>規範レベル別 Coverage</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>規範レベル</th>
                <th className="num">規定数</th>
                <th className="num">変換済み</th>
                <th className="num">未変換</th>
                <th className="num">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {coverage.by_rule_type.map((row) => (
                <tr key={row.rule_type}>
                  <td>
                    <RuleTypeBadge ruleType={row.rule_type} />
                  </td>
                  <td className="num">{row.total}</td>
                  <td className="num">{row.converted}</td>
                  <td className="num">{row.unconverted}</td>
                  <td className="num">{row.coverage}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {progress && (
        <section className="card">
          <h2>レビュー進捗</h2>
          <div className="stat-grid">
            <Stat label="OK" value={String(progress.ok)} tone="good" />
            <Stat label="NG" value={String(progress.ng)} tone={progress.ng ? "bad" : undefined} />
            <Stat label="N/A" value={String(progress.na)} />
            <Stat
              label="未判定"
              value={String(progress.pending)}
              tone={progress.pending ? "warn" : "good"}
              sub={`全 ${progress.total} 件`}
              /* 0件のときは 0 とする。除算をそのまま書くと NaN がバーの幅に入る */
              percent={
                progress.total ? ((progress.total - progress.pending) / progress.total) * 100 : 0
              }
            />
          </div>
          <div className="row small muted" style={{ marginTop: 12 }}>
            重要度別:
            {Object.entries(progress.by_severity).map(([severity, count]) => (
              <span key={severity}>
                {severity} {count} 件
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <h2>Findings</h2>
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          {coverage.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
