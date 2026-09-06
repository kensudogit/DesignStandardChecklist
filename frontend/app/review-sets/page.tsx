"use client";

/**
 * 統合レビュー表の一覧と作成フォーム。
 *
 * 作成対象に選べるのは解析済みの標準書だけ。未解析のものはチェック項目を
 * 持たないため、統合しても表に何も出てこない。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { ReviewSet, StandardDocument } from "@/lib/types";

export default function ReviewSetsPage() {
  const router = useRouter();
  const [sets, setSets] = useState<ReviewSet[]>([]);
  const [documents, setDocuments] = useState<StandardDocument[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // レビュー表一覧と、作成の選択肢になる標準書一覧をまとめて取る
  const load = useCallback(async () => {
    try {
      const [setList, docList] = await Promise.all([
        api.listReviewSets(),
        api.listDocuments(),
      ]);
      setSets(setList);
      // 未解析・解析失敗の標準書は統合しても中身が無いので選択肢から外す
      setDocuments(docList.filter((d) => d.status === "analyzed"));
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "一覧を取得できません");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 対象標準書の選択トグル。順序は選んだ順のまま保つ
  function toggle(id: number) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  /**
   * 統合レビュー表を作って、その詳細ページへ移動する。
   *
   * 作成 API 側で統合処理まで走るため、標準書の数が多いと待ち時間が出る。
   */
  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (selected.length === 0) {
      setError("標準書を1件以上選択してください。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // 名前が空ならそのまま送らず既定名を入れる。一覧で見分けが付かなくなるため
      const created = await api.createReviewSet({
        name: name.trim() || "統合レビュー表",
        document_ids: selected,
      });
      router.push(`/review-sets/${created.id}`);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "作成に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  // レビュー表だけを消す。元の標準書と、その個別チェックリストは残る
  async function remove(reviewSet: ReviewSet) {
    if (!confirm(`「${reviewSet.name}」を削除します。`)) return;
    try {
      await api.deleteReviewSet(reviewSet.id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "削除に失敗しました");
    }
  }

  return (
    <>
      <Link href="/" className="back-link">
        ← 標準書一覧へ戻る
      </Link>

      <section className="card" style={{ marginTop: 10 }}>
        <h2>統合レビュー表の作成</h2>
        <p className="hint">
          複数の標準書を横断した1枚のチェックリストを作ります。標準書をまたいで完全に重複する
          チェック項目は統合し、複数の標準書を出典として保持します。規定ID・チェックIDは
          各標準書のものをそのまま使います。
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        {documents.length === 0 ? (
          <div className="empty">
            解析済みの標準書がありません。先に標準書を登録してください。
          </div>
        ) : (
          <form onSubmit={create}>
            <div style={{ maxWidth: 420, marginBottom: 14 }}>
              <label htmlFor="rs-name">レビュー表の名前</label>
              <input
                id="rs-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例: 設計レビュー（画面+詳細）"
              />
            </div>

            <label>対象の標準書（複数選択）</label>
            <div
              className="grid"
              style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}
            >
              {documents.map((doc) => (
                <label
                  key={doc.id}
                  className="doc-card"
                  style={{
                    cursor: "pointer",
                    borderColor: selected.includes(doc.id) ? "var(--accent)" : undefined,
                    fontWeight: 400,
                    fontSize: 13,
                    color: "var(--text)",
                  }}
                >
                  <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                    <input
                      type="checkbox"
                      checked={selected.includes(doc.id)}
                      onChange={() => toggle(doc.id)}
                      style={{ width: "auto" }}
                    />
                    <div>
                      <div className="title">{doc.document_name}</div>
                      <div className="small muted">
                        <span className="mono">{doc.document_id}</span> ／{" "}
                        {doc.document_type_label} ／ プレフィックス {doc.id_prefix} ／ チェック{" "}
                        {doc.check_count} 件
                      </div>
                    </div>
                  </div>
                </label>
              ))}
            </div>

            <div className="row" style={{ marginTop: 14 }}>
              <button className="primary" type="submit" disabled={busy}>
                {busy ? "統合中…" : `統合レビュー表を作成（${selected.length}件選択中）`}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="card">
        <h2>作成済みの統合レビュー表</h2>
        {loading ? (
          <p className="muted small">読み込み中…</p>
        ) : sets.length === 0 ? (
          <div className="empty">統合レビュー表はまだありません。</div>
        ) : (
          <div
            className="grid"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))" }}
          >
            {sets.map((reviewSet) => (
              <div key={reviewSet.id} className="doc-card">
                <Link
                  href={`/review-sets/${reviewSet.id}`}
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div className="title">{reviewSet.name}</div>
                  <div className="small muted">
                    {reviewSet.documents.map((d) => d.document_name).join(" ＋ ")}
                  </div>
                  <div className="doc-meta">
                    <span>チェック {reviewSet.check_count} 件</span>
                    <span>統合 {reviewSet.merged_count} 件</span>
                    <span>標準書 {reviewSet.documents.length} 件</span>
                  </div>
                </Link>
                <div className="row" style={{ marginTop: 10 }}>
                  <span className="spacer" />
                  <button className="danger" onClick={() => remove(reviewSet)}>
                    削除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
