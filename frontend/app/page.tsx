"use client";

/**
 * トップページ。標準書の登録フォームと、登録済み標準書の一覧を出す。
 *
 * 一覧はサーバ側では描画せず、マウント後に取得する。localStorage のトークンが
 * ブラウザにしか無いため、サーバ側描画では認証付きの取得ができない。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { UploadForm } from "@/components/UploadForm";
import { api, ApiError } from "@/lib/api";
import type { StandardDocument } from "@/lib/types";

export default function HomePage() {
  const [documents, setDocuments] = useState<StandardDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * 標準書一覧を取り込む。アップロード後や削除後にも呼ぶので `useCallback` で固定する。
   *
   * 失敗しても `loading` は必ず落とす。落とさないと「読み込み中…」のまま止まる。
   */
  const load = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
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

  /**
   * 標準書を削除する。
   *
   * 解析結果と記入済みのレビュー結果も一緒に消える (サーバ側は cascade 削除)。
   * 取り消せないので確認を挟む。
   */
  async function handleDelete(doc: StandardDocument) {
    if (!confirm(`「${doc.document_name}」と、その解析結果・レビュー記入を削除します。`)) return;
    try {
      await api.deleteDocument(doc.id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "削除に失敗しました");
    }
  }

  return (
    <>
      <UploadForm onUploaded={load} />

      <section className="card">
        <h2>登録済み標準書</h2>
        <p className="hint">標準書一覧（standard-register）。クリックすると解析結果を開きます。</p>

        {error && <div className="alert alert-error">{error}</div>}

        {loading ? (
          <p className="muted small">読み込み中…</p>
        ) : documents.length === 0 ? (
          <div className="empty">
            登録済みの標準書はありません。上のフォームから標準書を登録してください。
          </div>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))" }}>
            {documents.map((doc) => (
              <div key={doc.id} className="doc-card">
                <Link href={`/documents/${doc.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                  <div className="title">{doc.document_name}</div>
                  <div className="small muted">
                    <span className="mono">{doc.document_id}</span> ／ {doc.document_type_label} ／
                    プレフィックス {doc.id_prefix}
                  </div>
                  <div className="doc-meta">
                    <span>規定 {doc.rule_count} 件</span>
                    <span>チェック {doc.check_count} 件</span>
                    <span>
                      Coverage {doc.coverage === null ? "—" : `${doc.coverage}%`}
                    </span>
                  </div>
                </Link>
                <div className="row" style={{ marginTop: 10 }}>
                  {/* 解析に失敗した標準書も一覧には残す。原因を error_message で示すため */}
                  {doc.status === "failed" ? (
                    <span className="badge badge-ng">解析失敗</span>
                  ) : (
                    <span className="badge badge-ok">解析済み</span>
                  )}
                  <span className="badge badge-neutral">{doc.file_format}</span>
                  {/* Markdown / テキストにはページの概念が無く、出典にページ番号を書けない */}
                  {!doc.has_page_numbers && (
                    <span className="badge badge-neutral" title="この形式ではページ番号を取得できません">
                      ページ番号なし
                    </span>
                  )}
                  <span className="spacer" />
                  <button className="danger" onClick={() => handleDelete(doc)}>
                    削除
                  </button>
                </div>
                {doc.error_message && (
                  <p className="note">{doc.error_message}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
