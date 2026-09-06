"use client";

/**
 * AI推奨事項のタブ。
 *
 * ここで扱うのは「標準書に規定が無い観点」の提案であり、標準書由来の成果物とは
 * 完全に別のリソース。チェックリスト・トレーサビリティ・Coverage には混ざらない。
 * 画面上でも警告帯と「AI推奨」タグで由来が分かるようにしている。
 *
 * コメント欄は入力中 `drafts` に溜め、フォーカスが外れた時点で保存する
 * (`ChecklistTable` と同じ方式)。採否のプルダウンは選択時に即保存する。
 */

import { useCallback, useEffect, useState } from "react";

import { SeverityBadge } from "@/components/Badges";
import { api, ApiError } from "@/lib/api";
import type { AdoptionValue, Recommendation, RecommendationStatus } from "@/lib/types";

/** 採否の選択肢。既定は `Proposed` (未判断)。 */
const ADOPTIONS: AdoptionValue[] = ["Proposed", "Adopted", "Rejected"];

/** 採否 → CSS クラス。Rejected は N/A と同じ色にして、対応不要であることを示す。 */
const ADOPTION_CLASS: Record<AdoptionValue, string> = {
  Proposed: "badge badge-pending",
  Adopted: "badge badge-ok",
  Rejected: "badge badge-na",
};

export function RecommendationsPanel({ documentId }: { documentId: number }) {
  const [rows, setRows] = useState<Recommendation[]>([]);
  const [status, setStatus] = useState<RecommendationStatus | null>(null);
  const [generator, setGenerator] = useState("catalog");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** コメント欄の未保存入力。キーは推奨事項の id。 */
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  // 一覧と生成可否は常に組で使うので同時に取りに行く
  const load = useCallback(async () => {
    try {
      const [list, statusData] = await Promise.all([
        api.listRecommendations(documentId),
        api.recommendationStatus(documentId),
      ]);
      setRows(list);
      setStatus(statusData);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "AI推奨事項を取得できません");
    }
  }, [documentId]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * 推奨事項を生成する。
   *
   * サーバ側は `replace: true` で呼ぶため、既存の推奨事項は入れ替わる。
   * 採否やコメントの記入内容も一緒に消える。
   */
  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setRows(await api.generateRecommendations(documentId, generator));
      setStatus(await api.recommendationStatus(documentId));
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "生成に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  // 取り消せないので確認を挟む
  async function clear() {
    if (!confirm("生成済みのAI推奨事項をすべて削除します。")) return;
    setBusy(true);
    try {
      await api.clearRecommendations(documentId);
      await load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "削除に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function save(row: Recommendation, payload: Partial<Recommendation>) {
    try {
      const updated = await api.updateRecommendation(documentId, row.id, {
        adoption: payload.adoption,
        comment: payload.comment,
      });
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      setDrafts((d) => {
        const next = { ...d };
        delete next[row.id];
        return next;
      });
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "保存に失敗しました");
    }
  }

  // APIキー未設定なら Claude を選べないようにする。選ばせてから失敗させない
  const claudeDisabled = !status?.claude_available;

  return (
    <>
      {/* 由来を取り違えると成果物の意味が変わるので、常に先頭で明示する */}
      <div className="alert alert-warn">
        <strong>AI推奨事項は標準書由来ではありません。</strong>{" "}
        標準書に規定が無い観点として提案したものです。出典（章・節・ページ）は持たず、
        レビューチェックリスト・トレーサビリティ表・Coverage には一切含まれません。
        採用するかどうかはプロジェクトで判断してください。
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="card">
        <h2>推奨事項の生成</h2>
        <p className="hint">
          SKILL.md の成果物では「要求された場合のみ」生成する項目です。生成しない限り、
          成果物は標準書由来のみで構成されます。
        </p>
        <div className="row">
          <div>
            <label htmlFor="generator">生成方式</label>
            <select
              id="generator"
              value={generator}
              onChange={(e) => setGenerator(e.target.value)}
              style={{ minWidth: 260 }}
            >
              <option value="catalog">観点カタログ（APIキー不要・決定的）</option>
              <option value="claude" disabled={claudeDisabled}>
                Claude API {claudeDisabled ? "（ANTHROPIC_API_KEY 未設定）" : `（${status?.claude_model}）`}
              </option>
            </select>
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button className="primary" onClick={generate} disabled={busy}>
              {busy ? "生成中…" : rows.length ? "再生成する" : "生成する"}
            </button>
          </div>
          {rows.length > 0 && (
            <div style={{ alignSelf: "flex-end" }}>
              <button className="danger" onClick={clear} disabled={busy}>
                すべて削除
              </button>
            </div>
          )}
          <span className="spacer" />
          <span className="small muted" style={{ alignSelf: "flex-end" }}>
            {rows.length} 件
          </span>
        </div>
        <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
          観点カタログは SKILL.md 5章・6章の重点観点をもとに、標準書が触れていない観点だけを
          提案します。Claude API を使う場合は、抽出済みの規定一覧を渡して不足観点を提案させます。
        </p>
      </section>

      {rows.length === 0 ? (
        <div className="empty">
          AI推奨事項はまだ生成されていません。上のボタンから生成してください。
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="num">No</th>
                <th>Recommendation ID</th>
                <th>分類</th>
                <th>推奨チェック項目</th>
                <th>重要度</th>
                <th>提案理由</th>
                <th>生成方式</th>
                <th>採否</th>
                <th>コメント</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="num">{row.no}</td>
                  <td className="mono">{row.recommendation_id}</td>
                  <td className="category-cell">
                    {row.category}
                    {row.sub_category && <div className="small muted">{row.sub_category}</div>}
                  </td>
                  <td className="check-point">
                    {row.check_point}
                    <span className="origin-tag">AI推奨</span>
                  </td>
                  <td>
                    <SeverityBadge severity={row.severity} />
                  </td>
                  <td className="small muted" style={{ maxWidth: 320 }}>
                    {row.rationale}
                  </td>
                  <td className="small muted">
                    {row.generator}
                    {row.generator_detail && <div>{row.generator_detail}</div>}
                  </td>
                  <td>
                    <select
                      value={row.adoption}
                      onChange={(e) =>
                        void save(row, { adoption: e.target.value as AdoptionValue })
                      }
                      style={{ minWidth: 106 }}
                    >
                      {ADOPTIONS.map((a) => (
                        <option key={a} value={a}>
                          {a}
                        </option>
                      ))}
                    </select>
                    <div style={{ marginTop: 4 }}>
                      <span className={ADOPTION_CLASS[row.adoption]}>{row.adoption}</span>
                    </div>
                  </td>
                  <td>
                    <textarea
                      rows={2}
                      style={{ minWidth: 170 }}
                      value={drafts[row.id] ?? row.comment}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [row.id]: e.target.value }))
                      }
                      onBlur={() => {
                        const draft = drafts[row.id];
                        if (draft !== undefined && draft !== row.comment) {
                          void save(row, { comment: draft });
                        }
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
