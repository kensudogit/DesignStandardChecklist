"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Meta } from "@/lib/types";

export function UploadForm({ onUploaded }: { onUploaded?: () => void }) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .meta()
      .then(setMeta)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "メタ情報を取得できません"),
      );
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setError("標準書ファイルを選択してください。");
      return;
    }
    setBusy(true);
    try {
      const doc = await api.uploadDocument(form);
      formRef.current?.reset();
      onUploaded?.();
      router.push(`/documents/${doc.id}`);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "アップロードに失敗しました");
    } finally {
      setBusy(false);
    }
  }

  const accept = meta?.supported_extensions.join(",") ?? ".pdf,.docx,.xlsx,.md,.txt";

  return (
    <section className="card">
      <h2>標準書の登録</h2>
      <p className="hint">
        画面設計標準・詳細設計標準・DB設計標準・API設計標準などを登録すると、規定を抽出して
        チェックリストを生成します。不明な項目は空欄のままで構いません（「不明」として記録されます）。
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <form ref={formRef} onSubmit={handleSubmit}>
        <div className="grid">
          <div>
            <label htmlFor="file">標準書ファイル *</label>
            <input id="file" name="file" type="file" accept={accept} required />
            <p className="small muted" style={{ margin: "4px 0 0" }}>
              対応: {meta?.supported_extensions.join(" / ") ?? "読み込み中…"}
            </p>
          </div>
          <div>
            <label htmlFor="document_name">文書名</label>
            <input
              id="document_name"
              name="document_name"
              type="text"
              placeholder="未入力ならファイル名を使用"
            />
          </div>
          <div>
            <label htmlFor="document_type">文書種別</label>
            <select id="document_type" name="document_type" defaultValue="screen">
              {meta?.document_types.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}（{t.prefix}）
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="version">版数</label>
            <input id="version" name="version" type="text" placeholder="不明" />
          </div>
          <div>
            <label htmlFor="established_date">制定日</label>
            <input id="established_date" name="established_date" type="text" placeholder="不明" />
          </div>
          <div>
            <label htmlFor="revised_date">改訂日</label>
            <input id="revised_date" name="revised_date" type="text" placeholder="不明" />
          </div>
          <div>
            <label htmlFor="target_phase">対象工程</label>
            <input id="target_phase" name="target_phase" type="text" placeholder="不明" />
          </div>
          <div>
            <label htmlFor="target_deliverable">対象成果物</label>
            <input
              id="target_deliverable"
              name="target_deliverable"
              type="text"
              placeholder="不明"
            />
          </div>
        </div>

        <div className="row" style={{ marginTop: 14 }}>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "解析中…" : "登録して解析する"}
          </button>
          <span className="small muted">
            アップロード後、規定抽出からCoverage算出までを自動実行します。
          </span>
        </div>
      </form>
    </section>
  );
}
