"use client";

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

type TabKey =
  | "checklist"
  | "rules"
  | "coverage"
  | "traceability"
  | "unconverted"
  | "recommendations";

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void params.then((p) => setDocumentId(Number(p.id)));
  }, [params]);

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

  function handleItemChanged(updated: ChecklistItem) {
    setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
    if (documentId !== null) {
      void api.progress(documentId).then(setProgress).catch(() => undefined);
    }
  }

  if (loading) return <p className="muted">読み込み中…</p>;

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
          <a className="badge badge-neutral" href={api.exportUrl(documentId)} download>
            ⬇ 成果物一式 (ZIP)
          </a>
          {ARTIFACTS.map((a) => (
            <a
              key={a.artifact}
              className="badge badge-neutral"
              href={api.exportUrl(documentId, a.artifact)}
              download
            >
              ⬇ {a.label}
            </a>
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
