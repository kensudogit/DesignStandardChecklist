/**
 * バックエンド (FastAPI) を呼ぶための唯一の窓口。
 *
 * 画面側は `fetch` を直接使わず必ずこのモジュール経由にしている。認証ヘッダの付与、
 * エラーの正規化、401 時のトークン破棄といった横断的な処理を1か所に閉じ込めるため。
 *
 * エンドポイントの実体は `backend/app/api/` 配下にある。パスを変えるときは両方直すこと。
 */

import type {
  AdoptionValue,
  AuthStatus,
  AuthUser,
  ChecklistItem,
  ConsolidatedCheck,
  Coverage,
  Meta,
  LoginResponse,
  Recommendation,
  RecommendationStatus,
  ResultValue,
  ReviewProgress,
  ReviewSet,
  ReviewSetCoverage,
  Rule,
  StandardDocument,
  TraceabilityRow,
  UnconvertedRow,
} from "./types";

/** レビュー結果の記入内容。チェックリストと統合レビュー表で共通の形。 */
export interface ReviewUpdate {
  result: ResultValue;
  evidence: string;
  reviewer: string;
  review_date: string;
  comment: string;
}

/**
 * バックエンドの接続先。`NEXT_PUBLIC_API_BASE` で上書きできる。
 *
 * 末尾のスラッシュを削っているのは、各呼び出しがパスを `/api/...` と先頭スラッシュ付きで
 * 渡すため。付いたままだと `//api/...` になってしまう。
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

/** localStorage のキー。他アプリと衝突しないよう接頭辞を付けている。 */
const TOKEN_KEY = "dsc.token";

/** ログイントークン。認証が無効なら常に null で、ヘッダも付かない。 */
export const auth = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* プライベートモード等では保持できない。その場合はセッション内のみ有効。 */
    }
  },
  clear() {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* 同上 */
    }
  },
};

/**
 * API 呼び出しの失敗。`status` に HTTP ステータスを持つ。
 *
 * ネットワーク到達不能 (サーバ未起動など) の場合は status = 0 とする。
 * HTTP のステータスコードに 0 は無いので、通信できたかどうかの判別に使える。
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 全 API 呼び出しの共通処理。認証ヘッダの付与と失敗時の `ApiError` 化までを行う。
 *
 * 本文の読み方は呼び出し側に委ねる (JSON なら `request`、ダウンロードなら `download`)。
 */
async function send(path: string, init?: RequestInit): Promise<Response> {
  const token = auth.get();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      // 解析結果は随時変わるので、ブラウザキャッシュは使わない
      cache: "no-store",
      ...init,
      headers,
    });
  } catch {
    throw new ApiError(
      `バックエンド (${API_BASE}) へ接続できません。FastAPI を起動しているか確認してください。`,
      0,
    );
  }

  if (response.status === 401) {
    // 期限切れ・無効なトークンは持ち続けても意味がないので捨てる
    auth.clear();
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* JSON でない場合はステータスをそのまま使う */
    }
    throw new ApiError(detail, response.status);
  }

  return response;
}

/** JSON を返すエンドポイント用。失敗時は必ず `ApiError` を投げる。 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  // 204 No Content (DELETE 等) は本文が無く、json() を呼ぶと例外になる
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Content-Disposition からファイル名を取り出す。
 *
 * サーバは日本語を含むファイル名を `filename*=UTF-8''...` (RFC 5987) で送る
 * (`backend/app/api/exports.py` の `_content_disposition`)。素の `filename=` も
 * 一応見るが、これは将来サーバ側が変わった場合の保険。
 */
function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;

  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      /* パーセントエンコードが壊れている場合は素の filename= を試す */
    }
  }

  const plain = /filename="([^"]+)"|filename=([^;]+)/i.exec(header);
  const name = plain?.[1] ?? plain?.[2];
  return name ? name.trim() : fallback;
}

/**
 * 成果物をダウンロードする。
 *
 * `<a href download>` でサーバへ直接リンクしないのは、ブラウザ発のナビゲーションには
 * Authorization ヘッダが付かず、`DSC_AUTH_ENABLED=true` のとき 401 になるため。
 * ここでは他のAPIと同じ経路で取得し、Blob をオブジェクト URL 経由で保存させる。
 */
async function download(path: string, fallbackName: string): Promise<void> {
  const response = await send(path);
  const filename = filenameFromDisposition(
    response.headers.get("Content-Disposition"),
    fallbackName,
  );
  const blob = await response.blob();

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  // Firefox は文書に繋がっていない要素の click() を無視する
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // click() の保存処理は非同期に始まるので、即時 revoke すると取りこぼす。
  // 次のタスクまで待てば十分で、待った上で必ず解放する (放置するとリークする)。
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** 画面から使うエンドポイント群。パスはバックエンドのルータ構成に対応している。 */
export const api = {
  /** 選択肢マスタ。文書種別や重要度の一覧をサーバ側の定義に合わせるために使う。 */
  meta: () => request<Meta>("/api/meta"),

  // --- 認証 ---

  /** 認証が有効か、初期管理者の作成が必要かを問い合わせる。未ログインでも呼べる。 */
  authStatus: () => request<AuthStatus>("/api/auth/status"),

  login: (username: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),

  /**
   * 利用者を作成する。
   *
   * 初期管理者がまだ居ない場合 (needs_bootstrap) は未認証でも通る。
   * それ以降は管理者権限が必要。
   */
  createUser: (payload: {
    username: string;
    password: string;
    display_name?: string;
    is_admin?: boolean;
  }) =>
    request<AuthUser>("/api/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  listDocuments: () => request<StandardDocument[]>("/api/documents"),

  getDocument: (id: number) => request<StandardDocument>(`/api/documents/${id}`),

  /**
   * 標準書をアップロードする。
   *
   * multipart のため Content-Type は指定しない。指定すると boundary が欠けて
   * サーバ側でパースできなくなる。
   */
  uploadDocument: (form: FormData) =>
    request<StandardDocument>("/api/documents", { method: "POST", body: form }),

  updateDocument: (id: number, payload: Record<string, string>) =>
    request<StandardDocument>(`/api/documents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  /**
   * 解析をやり直す。規定・チェック項目は作り直され、IDも振り直される。
   *
   * ただし記入済みのレビュー結果 (Result/Evidence/Reviewer/日付/コメント) は
   * Check ID をキーに引き継がれる (`backend/app/core/pipeline.py` の
   * `_preserved_review_state`)。再解析後に同じ Check ID が生成されなかった項目の
   * 記入内容は失われる。
   */
  reanalyze: (id: number) =>
    request<StandardDocument>(`/api/documents/${id}/analyze`, { method: "POST" }),

  deleteDocument: (id: number) =>
    request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  listRules: (id: number) => request<Rule[]>(`/api/documents/${id}/rules`),

  /**
   * チェックリストを取得する。重要度や結果での絞り込みは params で渡す。
   *
   * 空文字の条件を落としているのは、`?severity=` のような空クエリを送らないため。
   * サーバ側で「空文字での絞り込み」と解釈されて0件になるのを避ける。
   */
  listChecklist: (id: number, params?: Record<string, string>) => {
    const query = new URLSearchParams(
      Object.entries(params ?? {}).filter(([, v]) => v),
    ).toString();
    return request<ChecklistItem[]>(
      `/api/documents/${id}/checklist${query ? `?${query}` : ""}`,
    );
  },

  updateChecklistItem: (
    documentId: number,
    itemId: number,
    payload: Partial<{
      result: ResultValue;
      evidence: string;
      reviewer: string;
      review_date: string;
      comment: string;
    }>,
  ) =>
    request<ChecklistItem>(`/api/documents/${documentId}/checklist/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  coverage: (id: number) => request<Coverage>(`/api/documents/${id}/coverage`),

  progress: (id: number) => request<ReviewProgress>(`/api/documents/${id}/progress`),

  traceability: (id: number) =>
    request<TraceabilityRow[]>(`/api/documents/${id}/traceability`),

  unconverted: (id: number) =>
    request<UnconvertedRow[]>(`/api/documents/${id}/unconverted`),

  /**
   * CSV / Markdown の成果物をダウンロードする。`artifact` を省略すると ZIP 一括。
   *
   * 出力エンドポイントも `current_user` を要求する (`backend/app/api/exports.py`) ため、
   * 他のAPIと同じく認証ヘッダ付きで取得する。ファイル名はサーバの
   * Content-Disposition に従う (CORS の expose_headers で公開済み)。
   */
  downloadExport: (id: number, artifact?: string) =>
    download(
      `/api/documents/${id}/export${artifact ? `/${artifact}` : ""}`,
      artifact ?? "checklist-artifacts.zip",
    ),

  // --- AI推奨事項 (標準由来とは別リソース) ---

  listRecommendations: (id: number) =>
    request<Recommendation[]>(`/api/documents/${id}/recommendations`),

  recommendationStatus: (id: number) =>
    request<RecommendationStatus>(`/api/documents/${id}/recommendations/status`),

  /**
   * AI推奨事項を生成する。`replace: true` なので既存の推奨事項は入れ替わる。
   *
   * 生成結果はチェックリストとは別リソースで、標準由来の成果物には混ざらない。
   */
  generateRecommendations: (id: number, generator: string) =>
    request<Recommendation[]>(`/api/documents/${id}/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ generator, replace: true }),
    }),

  updateRecommendation: (
    id: number,
    recommendationId: number,
    payload: Partial<{ adoption: AdoptionValue; comment: string }>,
  ) =>
    request<Recommendation>(
      `/api/documents/${id}/recommendations/${recommendationId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),

  clearRecommendations: (id: number) =>
    request<void>(`/api/documents/${id}/recommendations`, { method: "DELETE" }),

  // --- 統合レビュー表 (複数標準書の横断) ---

  listReviewSets: () => request<ReviewSet[]>("/api/review-sets"),

  getReviewSet: (id: number) => request<ReviewSet>(`/api/review-sets/${id}`),

  /** 統合レビュー表を作る。作成しただけでは統合処理は走らない (consolidate が別途必要)。 */
  createReviewSet: (payload: { name: string; document_ids: number[]; notes?: string }) =>
    request<ReviewSet>("/api/review-sets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  updateReviewSet: (
    id: number,
    payload: Partial<{ name: string; document_ids: number[]; notes: string }>,
  ) =>
    request<ReviewSet>(`/api/review-sets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  /** 統合処理を実行し直す。重複統合をやり直すため、記入済みのレビュー結果に影響する。 */
  rebuildReviewSet: (id: number) =>
    request<ReviewSet>(`/api/review-sets/${id}/consolidate`, { method: "POST" }),

  deleteReviewSet: (id: number) =>
    request<void>(`/api/review-sets/${id}`, { method: "DELETE" }),

  consolidatedChecklist: (id: number) =>
    request<ConsolidatedCheck[]>(`/api/review-sets/${id}/checklist`),

  updateConsolidatedItem: (id: number, rowId: number, payload: Partial<ReviewUpdate>) =>
    request<ConsolidatedCheck>(`/api/review-sets/${id}/checklist/${rowId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  reviewSetCoverage: (id: number) =>
    request<ReviewSetCoverage>(`/api/review-sets/${id}/coverage`),

  /** 統合レビュー表の成果物をダウンロードする。要領は `downloadExport` と同じ。 */
  downloadReviewSetExport: (id: number, artifact?: string) =>
    download(
      `/api/review-sets/${id}/export${artifact ? `/${artifact}` : ""}`,
      artifact ?? `review-set-${id}-artifacts.zip`,
    ),
};
