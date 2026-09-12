"use client";

/**
 * チェックリスト本体の表。絞り込みと、レビュー結果の記入を担当する。
 *
 * 記入方法は列によって2種類ある。
 *  - 結果 (OK/NG/N/A) のプルダウン: 選んだ時点で即保存する
 *  - Evidence / Reviewer / 日付 / コメントの自由入力: 入力中は `drafts` に溜め、
 *    フォーカスが外れた時点でまとめて保存する
 *
 * 自由入力を1文字ごとに保存しないのは、打鍵のたびに PATCH が飛ぶのを避けるため。
 */

import { useMemo, useState } from "react";

import { ResultBadge, SeverityBadge } from "@/components/Badges";
import { api, ApiError } from "@/lib/api";
import type { ChecklistItem, Meta, ResultValue } from "@/lib/types";

/** 表示順。重要度の高いものから並べる。`Severity` の宣言順とは独立に持つ。 */
const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"];

interface Props {
  documentId: number;
  items: ChecklistItem[];
  meta: Meta | null;
  hasPageNumbers: boolean;
  onChanged: (item: ChecklistItem) => void;
  /** 初期の検索語。統合レビュー表の出典から開いたときに該当項目へ絞る。 */
  initialQuery?: string;
}

export function ChecklistTable({
  documentId,
  items,
  meta,
  hasPageNumbers,
  onChanged,
  initialQuery = "",
}: Props) {
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [result, setResult] = useState("");
  const [query, setQuery] = useState(initialQuery);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  /**
   * 未保存の入力内容。キーはチェック項目の id。
   *
   * 保存に成功した項目はここから消し、以後はサーバから来た値を表示する。
   */
  const [drafts, setDrafts] = useState<Record<number, Partial<ChecklistItem>>>({});

  /**
   * 一覧が入れ替わったら未保存の入力は捨てる。古い draft を残すと、
   * 別の解析結果に対して前の入力値を表示してしまう。
   *
   * useEffect ではなく描画中に調整する。効果は描画の後に走るため、
   * items が入れ替わった直後の1フレームだけ「新しい items に古い draft を
   * 当てた状態」が描画されてしまい、防ごうとしている取り違えがそこで起きる。
   */
  const [renderedItems, setRenderedItems] = useState(items);
  if (items !== renderedItems) {
    setRenderedItems(items);
    setDrafts({});
  }

  // 分類の選択肢は取得済みの項目から作る。文書ごとに出現する分類が違うため
  const categories = useMemo(
    () => Array.from(new Set(items.map((i) => i.category))).sort(),
    [items],
  );

  /**
   * 絞り込みと並べ替えを適用した表示対象。
   *
   * 絞り込みはサーバにも同じ条件を渡せるが、件数が多くないため画面側で完結させ、
   * 操作のたびに通信しないようにしている。
   */
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items
      .filter((i) => !severity || i.severity === severity)
      .filter((i) => !category || i.category === category)
      .filter((i) => !result || i.result === result)
      .filter(
        (i) =>
          !needle ||
          i.check_point.toLowerCase().includes(needle) ||
          i.original_rule.toLowerCase().includes(needle) ||
          i.check_id.toLowerCase().includes(needle) ||
          i.standard_id.toLowerCase().includes(needle),
      )
      .sort(
        (a, b) =>
          SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
          a.no - b.no,
      );
  }, [items, severity, category, result, query]);

  /**
   * 1項目のレビュー結果を保存する。
   *
   * 成功したら親へ通知し、その項目の draft を破棄する (サーバの値が正になる)。
   */
  async function save(item: ChecklistItem, payload: Partial<ChecklistItem>) {
    setSavingId(item.id);
    setError(null);
    try {
      const updated = await api.updateChecklistItem(documentId, item.id, {
        result: payload.result as ResultValue | undefined,
        evidence: payload.evidence,
        reviewer: payload.reviewer,
        review_date: payload.review_date,
        comment: payload.comment,
      });
      onChanged(updated);
      setDrafts((d) => {
        const next = { ...d };
        delete next[item.id];
        return next;
      });
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "保存に失敗しました");
    } finally {
      setSavingId(null);
    }
  }

  /**
   * 入力欄に出す値。未編集ならサーバの値を出す。
   *
   * 末尾の `?? ""` は、null のフィールドで input が非制御コンポーネントに
   * 切り替わってしまうのを防ぐためのもの。
   */
  function draftValue(item: ChecklistItem, field: keyof ChecklistItem): string {
    const draft = drafts[item.id]?.[field];
    return (draft ?? item[field] ?? "") as string;
  }

  function setDraft(item: ChecklistItem, field: keyof ChecklistItem, value: string) {
    setDrafts((d) => ({ ...d, [item.id]: { ...d[item.id], [field]: value } }));
  }

  // 値が変わっていなければ保存しない。フォーカスを通過しただけで PATCH が飛ぶのを防ぐ
  function commit(item: ChecklistItem, field: keyof ChecklistItem) {
    const draft = drafts[item.id]?.[field];
    if (draft === undefined || draft === item[field]) return;
    void save(item, { [field]: draft } as Partial<ChecklistItem>);
  }

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}

      <div className="row" style={{ marginBottom: 12 }}>
        <div>
          <label htmlFor="f-severity">重要度</label>
          <select id="f-severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">すべて</option>
            {(meta?.severities ?? SEVERITY_ORDER).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-category">分類</label>
          <select id="f-category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">すべて</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-result">結果</label>
          <select id="f-result" value={result} onChange={(e) => setResult(e.target.value)}>
            <option value="">すべて</option>
            {(meta?.result_values ?? ["OK", "NG", "N/A", "Pending"]).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div style={{ minWidth: 260, flex: 1 }}>
          <label htmlFor="f-query">検索（チェック項目・規定原文・ID）</label>
          <input
            id="f-query"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="例: 項目ID / パスワード / CHK-UI-003"
          />
        </div>
        <div style={{ alignSelf: "flex-end" }}>
          <span className="small muted">
            {visible.length} / {items.length} 件
          </span>
        </div>
      </div>

      {!hasPageNumbers && (
        <div className="alert alert-info">
          この文書形式ではページ番号を取得できないため、Page 列は「不明」と表示します。
          推測によるページ番号は付与しません。
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">No</th>
              <th>Check ID</th>
              <th>分類</th>
              <th>チェック項目</th>
              <th>重要度</th>
              <th>根拠（Standard ID / 章・節・ページ）</th>
              <th>条件・例外</th>
              <th>結果</th>
              <th>Evidence</th>
              <th>Reviewer</th>
              <th>Review Date</th>
              <th>コメント</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={12} className="empty">
                  条件に一致するチェック項目はありません。
                </td>
              </tr>
            )}
            {visible.map((item) => (
              <tr key={item.id} className={item.result === "NG" ? "row-ng" : undefined}>
                <td className="num">{item.no}</td>
                <td className="mono">{item.check_id}</td>
                <td className="category-cell">
                  {item.category}
                  {item.sub_category && (
                    <div className="small muted">{item.sub_category}</div>
                  )}
                </td>
                <td className="check-point">
                  {item.check_point}
                  {item.note && <div className="note">{item.note}</div>}
                  <details style={{ marginTop: 4 }}>
                    <summary>標準書の原文</summary>
                    <div className="small muted">{item.original_rule}</div>
                  </details>
                </td>
                <td>
                  <SeverityBadge severity={item.severity} title={item.severity_reason} />
                </td>
                <td className="small source-cell">
                  <div className="mono">
                    {[item.standard_id, ...item.extra_standard_ids].join(" / ")}
                  </div>
                  <div className="muted">
                    章 {item.chapter ?? "不明"} ／ 節 {item.section ?? "不明"} ／ ページ{" "}
                    {item.page ?? item.locator ?? "不明"}
                  </div>
                  {item.similar_check_ids.length > 0 && (
                    <div className="note">類似候補: {item.similar_check_ids.join(", ")}</div>
                  )}
                  {item.merged_check_ids.length > 0 && (
                    <div className="small muted">
                      重複統合元: {item.merged_check_ids.join(", ")}
                    </div>
                  )}
                </td>
                <td className="small">
                  {item.condition && <div>条件: {item.condition}</div>}
                  {item.exception && <div>例外: {item.exception}</div>}
                  {!item.condition && !item.exception && <span className="muted">—</span>}
                </td>
                <td>
                  <select
                    value={item.result}
                    disabled={savingId === item.id}
                    /* 結果だけは draft を挟まず即保存する。選択操作は確定操作とみなせるため */
                    onChange={(e) => void save(item, { result: e.target.value as ResultValue })}
                    style={{ minWidth: 92 }}
                  >
                    {(meta?.result_values ?? ["OK", "NG", "N/A", "Pending"]).map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <div style={{ marginTop: 4 }}>
                    <ResultBadge result={item.result} />
                  </div>
                </td>
                <td>
                  <textarea
                    rows={2}
                    style={{ minWidth: 150 }}
                    value={draftValue(item, "evidence")}
                    onChange={(e) => setDraft(item, "evidence", e.target.value)}
                    onBlur={() => commit(item, "evidence")}
                    placeholder="設計書の該当箇所"
                  />
                </td>
                <td>
                  <input
                    type="text"
                    style={{ minWidth: 100 }}
                    value={draftValue(item, "reviewer")}
                    onChange={(e) => setDraft(item, "reviewer", e.target.value)}
                    onBlur={() => commit(item, "reviewer")}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    style={{ minWidth: 110 }}
                    placeholder="YYYY-MM-DD"
                    value={draftValue(item, "review_date")}
                    onChange={(e) => setDraft(item, "review_date", e.target.value)}
                    onBlur={() => commit(item, "review_date")}
                  />
                </td>
                <td>
                  <textarea
                    rows={2}
                    style={{ minWidth: 170 }}
                    value={draftValue(item, "comment")}
                    onChange={(e) => setDraft(item, "comment", e.target.value)}
                    onBlur={() => commit(item, "comment")}
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
