"use client";

/**
 * 標準書1件の詳細ページ。解析結果をタブで切り替えて見せる。
 *
 * データはページ表示時に一括で取得し、以降はタブを切り替えても取り直さない
 * (AI推奨事項だけは別リソースなので、そのタブの中で自前に取得する)。
 * 通信を1回にまとめる代わりに、初回の表示までは少し待たされる。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ChecklistTable } from "@/components/ChecklistTable";
import { RecommendationsPanel } from "@/components/RecommendationsPanel";
import {
  CoveragePanel,
  RulesTable,
  TraceabilityTable,
  UnconvertedTable,
} from "@/components/Panels";
import { api, ApiError } from "@/lib/api";
import type {
  ChecklistItem,
  Coverage,
  Meta,
  ReviewProgress,
  Rule,
  StandardDocument,
  TraceabilityRow,
  UnconvertedRow,
} from "@/lib/types";

/** タブの識別子。文字列そのままだと綴り違いに気付けないので型で縛る。 */
type TabKey =
  | "checklist"
  | "rules"
  | "coverage"
  | "traceability"
  | "unconverted"
  | "recommendations";

/** ZIP 一括ダウンロードを表す擬似 artifact 名 (個別の成果物名と衝突しない)。 */
const BUNDLE = "__bundle__";

/**
 * 個別にダウンロードできる成果物。
 *
 * `artifact` はサーバ側の出力名 (`backend/app/core/exporter.py`) とそのまま
 * 対応する。ここを変えるだけでは増えないので、増やすときは両方直すこと。
 */
const ARTIFACTS: { artifact: string; label: string }[] = [
  { artifact: "design-review-checklist", label: "チェックリスト (CSV)" },
  { artifact: "checklist-markdown", label: "チェックリスト (MD)" },
  { artifact: "extracted-rules", label: "規定抽出一覧 (CSV)" },
  { artifact: "traceability-matrix", label: "トレーサビリティ (CSV)" },
  { artifact: "unconverted-rules", label: "未変換規定 (CSV)" },
  { artifact: "coverage-report", label: "Coverageレポート (MD)" },
  { artifact: "standard-register", label: "標準書一覧 (CSV)" },
];

export default function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [tab, setTab] = useState<TabKey>("checklist");

  const [doc, setDoc] = useState<StandardDocument | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [progress, setProgress] = useState<ReviewProgress | null>(null);
  const [trace, setTrace] = useState<TraceabilityRow[]>([]);
  const [unconverted, setUnconverted] = useState<UnconvertedRow[]>([]);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // ダウンロード中の成果物。ZIP 一括は BUNDLE で表す。
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Next.js の params は Promise。id が決まるまで取得は始められない
  useEffect(() => {
    void params.then((p) => setDocumentId(Number(p.id)));
  }, [params]);

  /**
   * このページで使うデータを一括で取得する。
   *
   * タブごとに遅延読み込みしないのは、Coverage やトレーサビリティが
   * チェックリストと同じ解析結果から作られており、別々に取ると
   * 再解析を挟んだときに画面内で新旧が混ざるため。
   */
  const load = useCallback(async (id: number) => {
    setLoading(true);
    try {
      const [document, metaData, ruleRows, checkRows, cov, prog, traceRows, unconvertedRows] =
        await Promise.all([
          api.getDocument(id),
          api.meta(),
          api.listRules(id),
          api.listChecklist(id),
          api.coverage(id),
          api.progress(id),
          api.traceability(id),
          api.unconverted(id),
        ]);
      setDoc(document);
      setMeta(metaData);
      setRules(ruleRows);
      setItems(checkRows);
      setCoverage(cov);
      setProgress(prog);
      setTrace(traceRows);
      setUnconverted(unconvertedRows);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "解析結果を取得できません");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (documentId !== null) void load(documentId);
  }, [documentId, load]);

  /**
   * 再解析する。
   *
   * 記入済みのレビュー結果は Check ID を手がかりにサーバ側で引き継がれるが、
   * 再解析後に同じ Check ID が出てこなかった項目の記入内容は失われる。
   */
  async function handleReanalyze() {
    if (documentId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.reanalyze(documentId);
      await load(documentId);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "再解析に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload(artifact?: string) {
    if (documentId === null) return;
    setDownloading(artifact ?? BUNDLE);
    setError(null);
    try {
      await api.downloadExport(documentId, artifact);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "ダウンロードに失敗しました");
    } finally {
      setDownloading(null);
    }
  }

  /**
   * チェック項目1件の更新を画面へ反映する。
   *
   * 一覧全体は取り直さず、更新のあった1件だけ差し替える。入力のたびに
   * 全件取得すると、他の欄の未保存入力が消えてしまうため。
   * 進捗だけはサーバから取り直す (件数の集計は画面側では持っていない)。
   */
  function handleItemChanged(updated: ChecklistItem) {
    setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
    if (documentId !== null) {
      // 進捗の取得失敗は記入操作を妨げないので、握りつぶして表示だけ据え置く
      void api.progress(documentId).then(setProgress).catch(() => undefined);
    }
  }

  if (loading) return <p className="muted">読み込み中…</p>;

  // 文書そのものを取得できなかった場合だけ、全面をエラー表示に差し替える
  if (error && !doc) {
    return (
      <>
        <div className="alert alert-error">{error}</div>
        <Link href="/" className="back-link">
          ← 標準書一覧へ戻る
        </Link>
      </>
    );
  }

  if (!doc || documentId === null) return null;

  const tabs: { key: TabKey; label: string; count?: number }[] = [
    { key: "checklist", label: "レビューチェックリスト", count: items.length },
    { key: "rules", label: "規定抽出一覧", count: rules.length },
    { key: "coverage", label: "Coverage" },
    { key: "traceability", label: "トレーサビリティ", count: trace.length },
    { key: "unconverted", label: "未変換規定", count: unconverted.length },
    { key: "recommendations", label: "AI推奨事項（標準書由来ではない）" },
  ];

  return (
    <>
      <Link href="/" className="back-link">
        ← 標準書一覧へ戻る
      </Link>

      <section className="card" style={{ marginTop: 10 }}>
        <div className="row">
          <div>
            <h2 style={{ marginBottom: 2 }}>{doc.document_name}</h2>
            <div className="small muted">
              <span className="mono">{doc.document_id}</span> ／ {doc.document_type_label} ／
              ID プレフィックス <span className="mono">{doc.id_prefix}</span> ／ 版数 {doc.version}
              ／ 制定 {doc.established_date} ／ 改訂 {doc.revised_date}
            </div>
            <div className="small muted">
              対象工程 {doc.target_phase} ／ 対象成果物 {doc.target_deliverable} ／ 原本{" "}
              {doc.original_filename}（{doc.file_format}, {doc.block_count} ブロック）
            </div>
          </div>
          <span className="spacer" />
          <button onClick={handleReanalyze} disabled={busy}>
            {busy ? "再解析中…" : "再解析"}
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
          再解析すると規定ID・チェックIDは振り直されますが、記入済みの結果・Evidence・
          Reviewer・コメントは Check ID を手がかりに引き継ぎます。
        </p>
      </section>

      <div className="tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`tab${tab === t.key ? " active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {t.count !== undefined && <span className="count">{t.count}</span>}
          </button>
        ))}
      </div>

      {tab === "checklist" && (
        <ChecklistTable
          documentId={documentId}
          items={items}
          meta={meta}
          hasPageNumbers={doc.has_page_numbers}
          onChanged={handleItemChanged}
        />
      )}
      {tab === "rules" && <RulesTable rules={rules} />}
      {tab === "coverage" && coverage && (
        <CoveragePanel coverage={coverage} progress={progress} />
      )}
      {tab === "traceability" && <TraceabilityTable rows={trace} />}
      {tab === "unconverted" && <UnconvertedTable rows={unconverted} />}
      {tab === "recommendations" && <RecommendationsPanel documentId={documentId} />}
    </>
  );
}
