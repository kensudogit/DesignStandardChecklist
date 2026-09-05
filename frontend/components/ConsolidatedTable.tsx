"use client";

import { useEffect, useMemo, useState } from "react";

import { ResultBadge, SeverityBadge } from "@/components/Badges";
import { api, ApiError } from "@/lib/api";
import type { ConsolidatedCheck, ResultValue } from "@/lib/types";

const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"];
const RESULTS: ResultValue[] = ["OK", "NG", "N/A", "Pending"];

interface Props {
  reviewSetId: number;
  rows: ConsolidatedCheck[];
  onChanged: (row: ConsolidatedCheck) => void;
}

export function ConsolidatedTable({ reviewSetId, rows, onChanged }: Props) {
  const [severity, setSeverity] = useState("");
  const [documentName, setDocumentName] = useState("");
  const [onlyMerged, setOnlyMerged] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, Partial<ConsolidatedCheck>>>({});

  useEffect(() => {
    setDrafts({});
  }, [rows]);

  const documentNames = useMemo(
    () =>
      Array.from(
        new Set(rows.flatMap((r) => r.sources.map((s) => s.source_document))),
      ).sort(),
    [rows],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows
      .filter((r) => !severity || r.severity === severity)
      .filter(
        (r) => !documentName || r.sources.some((s) => s.source_document === documentName),
      )
      .filter((r) => !onlyMerged || r.merged_check_ids.length > 0)
      .filter(
        (r) =>
          !needle ||
          r.check_point.toLowerCase().includes(needle) ||
          r.check_id.toLowerCase().includes(needle) ||
          r.sources.some((s) => s.standard_id.toLowerCase().includes(needle)),
      )
      .sort(
        (a, b) =>
          SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
          a.no - b.no,
      );
  }, [rows, severity, documentName, onlyMerged, query]);

  async function save(row: ConsolidatedCheck, payload: Partial<ConsolidatedCheck>) {
    setError(null);
    try {
      const updated = await api.updateConsolidatedItem(reviewSetId, row.id, {
        result: payload.result as ResultValue | undefined,
        evidence: payload.evidence,
        reviewer: payload.reviewer,
        review_date: payload.review_date,
        comment: payload.comment,
      });
      onChanged(updated);
      setDrafts((d) => {
        const next = { ...d };
        delete next[row.id];
        return next;
      });
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "保存に失敗しました");
    }
  }

  function draftValue(row: ConsolidatedCheck, field: keyof ConsolidatedCheck): string {
    return (drafts[row.id]?.[field] ?? row[field] ?? "") as string;
  }

  function commit(row: ConsolidatedCheck, field: keyof ConsolidatedCheck) {
    const draft = drafts[row.id]?.[field];
    if (draft === undefined || draft === row[field]) return;
    void save(row, { [field]: draft } as Partial<ConsolidatedCheck>);
  }

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}

      <div className="alert alert-info">
        統合表で記入した結果は、統合元となったすべての標準書のチェック項目へ書き戻します。
        同じ内容のチェックが標準書ごとに違う判定になるのを防ぐためです。
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <div>
          <label htmlFor="c-severity">重要度</label>
          <select id="c-severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">すべて</option>
            {SEVERITY_ORDER.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="c-doc">出典の標準書</label>
          <select id="c-doc" value={documentName} onChange={(e) => setDocumentName(e.target.value)}>
            <option value="">すべて</option>
            {documentNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div style={{ minWidth: 240, flex: 1 }}>
          <label htmlFor="c-query">検索</label>
          <input
            id="c-query"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="チェック項目 / CHK-UI-003 / STD-DD-012"
          />
        </div>
        <div style={{ alignSelf: "flex-end" }}>
          <label htmlFor="c-merged" style={{ display: "inline" }}>
            <input
              id="c-merged"
              type="checkbox"
              checked={onlyMerged}
              onChange={(e) => setOnlyMerged(e.target.checked)}
              style={{ width: "auto", marginRight: 6 }}
            />
            統合された項目のみ
          </label>
        </div>
        <div style={{ alignSelf: "flex-end" }} className="small muted">
          {visible.length} / {rows.length} 件
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">No</th>
              <th>Check ID</th>
              <th>分類</th>
              <th>チェック項目</th>
              <th>重要度</th>
              <th>出典（複数標準書）</th>
              <th>結果</th>
              <th>Evidence</th>
              <th>Reviewer</th>
              <th>コメント</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={10} className="empty">
                  条件に一致するチェック項目はありません。
                </td>
              </tr>
            )}
            {visible.map((row) => (
              <tr key={row.id} className={row.result === "NG" ? "row-ng" : undefined}>
                <td className="num">{row.no}</td>
                <td className="mono">
                  {row.check_id}
                  {row.merged_check_ids.length > 0 && (
                    <div className="badge badge-medium" style={{ marginTop: 4 }}>
                      統合 {row.merged_check_ids.length + 1} 件
                    </div>
                  )}
                </td>
                <td className="category-cell">
                  {row.category}
                  {row.sub_category && <div className="small muted">{row.sub_category}</div>}
                </td>
                <td className="check-point">
                  {row.check_point}
                  {row.note && <div className="note">{row.note}</div>}
                  {row.condition && <div className="small muted">条件: {row.condition}</div>}
                  {row.exception && <div className="small muted">例外: {row.exception}</div>}
                </td>
                <td>
                  <SeverityBadge severity={row.severity} />
                </td>
                <td className="small source-cell">
                  {row.sources.map((source) => (
                    <div key={source.check_id} style={{ marginBottom: 3 }}>
                      <span className="mono">{source.standard_id}</span>{" "}
                      <span className="muted">
                        {source.source_document} 章 {source.chapter} ／ 節 {source.section} ／
                        ページ {source.page}
                      </span>
                    </div>
                  ))}
                  {row.similar_check_ids.length > 0 && (
                    <div className="note">
                      標準書をまたぐ類似候補: {row.similar_check_ids.join(", ")}
                    </div>
                  )}
                </td>
                <td>
                  <select
                    value={row.result}
                    onChange={(e) => void save(row, { result: e.target.value as ResultValue })}
                    style={{ minWidth: 92 }}
                  >
                    {RESULTS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <div style={{ marginTop: 4 }}>
                    <ResultBadge result={row.result} />
                  </div>
                </td>
                <td>
                  <textarea
                    rows={2}
                    style={{ minWidth: 150 }}
                    value={draftValue(row, "evidence")}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [row.id]: { ...d[row.id], evidence: e.target.value },
                      }))
                    }
                    onBlur={() => commit(row, "evidence")}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    style={{ minWidth: 100 }}
                    value={draftValue(row, "reviewer")}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [row.id]: { ...d[row.id], reviewer: e.target.value },
                      }))
                    }
                    onBlur={() => commit(row, "reviewer")}
                  />
                </td>
                <td>
                  <textarea
                    rows={2}
                    style={{ minWidth: 170 }}
                    value={draftValue(row, "comment")}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [row.id]: { ...d[row.id], comment: e.target.value },
                      }))
                    }
                    onBlur={() => commit(row, "comment")}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
