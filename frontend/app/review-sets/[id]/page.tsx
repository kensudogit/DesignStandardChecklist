"use client";

/**
 * 統合レビュー表1件の詳細ページ。
 *
 * 構成は標準書の詳細ページとほぼ同じで、対象が複数標準書を横断した
 * チェックリストになっている点だけが違う。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ConsolidatedTable } from "@/components/ConsolidatedTable";
import { api, ApiError } from "@/lib/api";
import type { ConsolidatedCheck, ReviewSet, ReviewSetCoverage } from "@/lib/types";

/** ZIP 一括ダウンロードを表す擬似 artifact 名 (個別の成果物名と衝突しない)。 */
const BUNDLE = "__bundle__";

/** 個別にダウンロードできる成果物。`artifact` はサーバ側の出力名と対応する。 */
const ARTIFACTS = [
  { artifact: "consolidated-checklist", label: "統合チェックリスト (CSV)" },
  { artifact: "consolidated-checklist-markdown", label: "統合チェックリスト (MD)" },
  { artifact: "cross-traceability-matrix", label: "横断トレーサビリティ (CSV)" },
  { artifact: "cross-coverage-report", label: "横断Coverageレポート (MD)" },
];

export default function ReviewSetPage({ params }: { params: Promise<{ id: string }> }) {
  const [reviewSetId, setReviewSetId] = useState<number | null>(null);
  const [tab, setTab] = useState<"checklist" | "coverage">("checklist");

  const [reviewSet, setReviewSet] = useState<ReviewSet | null>(null);
  const [rows, setRows] = useState<ConsolidatedCheck[]>([]);
  const [coverage, setCoverage] = useState<ReviewSetCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // ダウンロード中の成果物。ZIP 一括は BUNDLE で表す。
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Next.js の params は Promise。id が決まるまで取得は始められない
  useEffect(() => {
    void params.then((p) => setReviewSetId(Number(p.id)));
  }, [params]);

  // レビュー表・統合チェックリスト・Coverage は同じ統合結果から作られるので一括で取る
  const load = useCallback(async (id: number) => {
    setLoading(true);
    try {
      const [set, checklist, cov] = await Promise.all([
        api.getReviewSet(id),
        api.consolidatedChecklist(id),
        api.reviewSetCoverage(id),
      ]);
      setReviewSet(set);
      setRows(checklist);
      setCoverage(cov);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "統合レビュー表を取得できません");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (reviewSetId !== null) void load(reviewSetId);
  }, [reviewSetId, load]);

  /**
   * 統合をやり直す。
   *
   * 各標準書を再解析したあとは、統合結果が古いままなのでこれを実行する。
   * 重複の統合先が変わりうるため、記入済みの結果の紐付きも変わる。
   */
  async function rebuild() {
    if (reviewSetId === null) return;
    setBusy(true);
    try {
      await api.rebuildReviewSet(reviewSetId);
      await load(reviewSetId);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "再統合に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload(artifact?: string) {
    if (reviewSetId === null) return;
    setDownloading(artifact ?? BUNDLE);
    setError(null);
    try {
      await api.downloadReviewSetExport(reviewSetId, artifact);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "ダウンロードに失敗しました");
    } finally {
      setDownloading(null);
    }
  }

  // 更新のあった1行だけ差し替える。全件取り直すと他の欄の未保存入力が消える
  function handleChanged(updated: ConsolidatedCheck) {
    setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  if (loading) return <p className="muted">読み込み中…</p>;

  if (error && !reviewSet) {
    return (
      <>
        <div className="alert alert-error">{error}</div>
        <Link href="/review-sets" className="back-link">
          ← 統合レビュー表一覧へ戻る
        </Link>
      </>
    );
  }

  if (!reviewSet || reviewSetId === null) return null;

  return (
    <>
      <Link href="/review-sets" className="back-link">
        ← 統合レビュー表一覧へ戻る
      </Link>

      <section className="card" style={{ marginTop: 10 }}>
        <div className="row">
          <div>
            <h2 style={{ marginBottom: 2 }}>{reviewSet.name}</h2>
            <div className="small muted">
              {reviewSet.documents.map((d) => (
                <span key={d.document_id} style={{ marginRight: 14 }}>
                  <span className="mono">{d.document_code}</span> {d.document_name}（
                  {d.document_type_label} / {d.id_prefix} / チェック {d.check_count} 件 / Coverage{" "}
                  {d.coverage ?? "—"}%）
                </span>
              ))}
            </div>
            <div className="small muted" style={{ marginTop: 4 }}>
              統合後 {reviewSet.check_count} 件（うち標準書をまたいで統合した重複{" "}
              {reviewSet.merged_count} 件）
            </div>
          </div>
          <span className="spacer" />
          <button onClick={rebuild} disabled={busy}>
            {busy ? "再統合中…" : "再統合"}
          </button>
        </div>

        {error && (
          <div className="alert alert-error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <button
            className="badge badge-neutral"
            onClick={() => void handleDownload()}
            disabled={downloading !== null}
          >
            {downloading === BUNDLE ? "取得中…" : "⬇ 成果物一式 (ZIP)"}
          </button>
          {ARTIFACTS.map((a) => (
            <button
              key={a.artifact}
              className="badge badge-neutral"
              onClick={() => void handleDownload(a.artifact)}
              disabled={downloading !== null}
            >
              {downloading === a.artifact ? "取得中…" : `⬇ ${a.label}`}
            </button>
          ))}
        </div>
        <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
          各標準書を再解析したあとは「再統合」で最新の解析結果から作り直してください。
        </p>
      </section>

      <div className="tabs">
        <button
          className={`tab${tab === "checklist" ? " active" : ""}`}
          onClick={() => setTab("checklist")}
        >
          統合チェックリスト<span className="count">{rows.length}</span>
        </button>
        <button
          className={`tab${tab === "coverage" ? " active" : ""}`}
          onClick={() => setTab("coverage")}
        >
          標準書別Coverage
        </button>
      </div>

      {tab === "checklist" && (
        <ConsolidatedTable
          reviewSetId={reviewSetId}
          rows={rows}
          onChanged={handleChanged}
        />
      )}

      {tab === "coverage" && coverage && (
        <>
          <section className="card">
            <h2>標準書別 Coverage</h2>
            <p className="hint">
              統合しても Coverage は標準書ごとに算出します。必須・禁止規定は各標準書で
              100% が目標です。
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>標準書</th>
                    <th>種別</th>
                    <th className="num">対象規定</th>
                    <th className="num">変換済み</th>
                    <th className="num">未変換</th>
                    <th className="num">Coverage</th>
                    <th className="num">必須</th>
                    <th className="num">禁止</th>
                    <th className="num">チェック項目</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.by_document.map((row) => (
                    <tr key={row.document_id}>
                      <td>
                        <Link href={`/documents/${row.document_id}`}>{row.document_name}</Link>
                      </td>
                      <td className="small muted">{row.document_type_label}</td>
                      <td className="num">{row.target_rules}</td>
                      <td className="num">{row.converted_rules}</td>
                      <td className="num">{row.unconverted_rules}</td>
                      <td className="num">{row.coverage}%</td>
                      <td className="num">
                        <span
                          /* 必須規定は 100% 未満なら無条件で赤。統合しても Coverage は標準書ごとに見る */
                          className={
                            row.mandatory_coverage >= 100 ? "badge badge-ok" : "badge badge-ng"
                          }
                        >
                          {row.mandatory_coverage}%
                        </span>
                      </td>
                      <td className="num">
                        <span
                          className={
                            row.prohibited_coverage >= 100 ? "badge badge-ok" : "badge badge-ng"
                          }
                        >
                          {row.prohibited_coverage}%
                        </span>
                      </td>
                      <td className="num">{row.check_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <h2>統合による重複削減</h2>
            <div className="stat-grid">
              <div className="stat">
                <div className="label">統合前のチェック項目</div>
                <div className="value">{coverage.total_checks_before_merge}</div>
                <div className="sub">標準書ごとの合計</div>
              </div>
              <div className="stat">
                <div className="label">統合後のチェック項目</div>
                <div className="value good">{coverage.consolidated_checks}</div>
              </div>
              <div className="stat">
                <div className="label">統合された重複</div>
                <div className="value">{coverage.merged_checks}</div>
                <div className="sub">複数標準書を出典として保持</div>
              </div>
              <div className="stat">
                <div className="label">類似候補（未統合）</div>
                <div className={`value${coverage.cross_document_similar ? " warn" : ""}`}>
                  {coverage.cross_document_similar}
                </div>
                <div className="sub">統合可否は人が判断</div>
              </div>
              <div className="stat">
                <div className="label">全体 Coverage</div>
                <div className="value">{coverage.total_coverage}%</div>
                <div className="sub">
                  {coverage.total_converted_rules} / {coverage.total_target_rules} 対象規定
                </div>
              </div>
            </div>
          </section>

          <section className="card">
            <h2>Findings</h2>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {coverage.findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
