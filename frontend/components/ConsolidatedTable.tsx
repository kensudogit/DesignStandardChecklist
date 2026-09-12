"use client";

/**
 * 統合レビュー表。複数の標準書を横断した1枚のチェックリスト。
 *
 * `ChecklistTable` との違いは2つ。
 *  - 出典が配列 (`sources`)。同じ内容の規定が複数の標準書にある場合、1行にまとめる
 *  - ここで記入した結果は、統合元となった各標準書のチェック項目へ書き戻される
 *    (書き戻しはサーバ側の処理。`backend/app/api/review_sets.py`)
 *
 * 入力の保存方式 (即保存とフォーカス外し保存の使い分け) は `ChecklistTable` と同じ。
 */

import Link from "next/link";
import { useMemo, useState } from "react";

import { ResultBadge, SeverityBadge } from "@/components/Badges";
import { api, ApiError } from "@/lib/api";
import type { ConsolidatedCheck, ResultValue } from "@/lib/types";

/** 表示順。重要度の高いものから並べる。 */
const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"];
/**
 * 結果の選択肢。
 *
 * `ChecklistTable` は meta から取るが、こちらは固定にしている。統合表は
 * 複数文書にまたがるため、特定文書の meta に引きずられないようにするため。
 */
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
  /** 未保存の入力内容。キーは統合チェック項目の id。 */
  const [drafts, setDrafts] = useState<Record<number, Partial<ConsolidatedCheck>>>({});

  /**
   * 一覧が入れ替わったら未保存の入力は捨てる (古い draft の混入を防ぐ)。
   *
   * useEffect ではなく描画中に調整する。効果は描画の後に走るため、rows が
   * 入れ替わった直後の1フレームだけ古い draft が新しい行に当たってしまう。
   */
  const [renderedRows, setRenderedRows] = useState(rows);
  if (rows !== renderedRows) {
    setRenderedRows(rows);
    setDrafts({});
  }

  // 出典の標準書名を重複なく集める。1行が複数出典を持つため flatMap で潰す
  const documentNames = useMemo(
    () =>
      Array.from(
        new Set(rows.flatMap((r) => r.sources.map((s) => s.source_document))),
      ).sort(),
    [rows],
  );

  /**
   * 絞り込みと並べ替えを適用した表示対象。
   *
   * 出典と検索は「どれか1つでも一致すれば表示」とする (`some`)。統合された行は
   * 複数の標準書に属するので、片方の標準書で絞り込んでも消えては困るため。
   */
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

  // 未編集ならサーバの値。末尾の `?? ""` は input が非制御に切り替わるのを防ぐため
  function draftValue(row: ConsolidatedCheck, field: keyof ConsolidatedCheck): string {
    return (drafts[row.id]?.[field] ?? row[field] ?? "") as string;
  }

  // 値が変わっていなければ保存しない
  function commit(row: ConsolidatedCheck, field: keyof ConsolidatedCheck) {
    const draft = drafts[row.id]?.[field];
    if (draft === undefined || draft === row[field]) return;
    void save(row, { [field]: draft } as Partial<ConsolidatedCheck>);
  }

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}

      {/* 書き戻しの挙動は画面から見えないので、記入前に明示しておく */}
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
                  {/* +1 は統合先である自分自身の分。merged_check_ids には統合元だけが入る */}
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
                  {row.sources.map((source, index) => (
                    // check_id は出典間で一意にならない。標準書ごとに同じ採番
                    // (CHK-UI-001 等) を持つため、位置を含めて識別する
                    // 出典から、その標準書のチェックリストの該当項目へ移動できる
                    // ようにする。check クエリで検索欄を埋め、その行だけを出す
                    <div key={`${source.check_id}-${index}`} style={{ marginBottom: 3 }}>
                      <Link
                        href={`/documents/${source.document_id}?check=${source.check_id}`}
                        title={`${source.source_document} の ${source.check_id} を開く`}
                      >
                        <span className="mono">{source.standard_id}</span>{" "}
                        {source.source_document}
                      </Link>
                      <span className="muted">
                        {" "}章 {source.chapter} ／ 節 {source.section} ／ ページ {source.page}
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
