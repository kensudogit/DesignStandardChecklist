import type {
  AdoptionValue,
  ChecklistItem,
  ConsolidatedCheck,
  Coverage,
  Meta,
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

export interface ReviewUpdate {
  result: ResultValue;
  evidence: string;
  reviewer: string;
  review_date: string;
  comment: string;
}

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
    });
  } catch {
    throw new ApiError(
      `バックエンド (${API_BASE}) へ接続できません。FastAPI を起動しているか確認してください。`,
      0,
    );
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

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<Meta>("/api/meta"),

  listDocuments: () => request<StandardDocument[]>("/api/documents"),

  getDocument: (id: number) => request<StandardDocument>(`/api/documents/${id}`),

  uploadDocument: (form: FormData) =>
    request<StandardDocument>("/api/documents", { method: "POST", body: form }),

  updateDocument: (id: number, payload: Record<string, string>) =>
    request<StandardDocument>(`/api/documents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  reanalyze: (id: number) =>
    request<StandardDocument>(`/api/documents/${id}/analyze`, { method: "POST" }),

  deleteDocument: (id: number) =>
    request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  listRules: (id: number) => request<Rule[]>(`/api/documents/${id}/rules`),

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

  exportUrl: (id: number, artifact?: string) =>
    `${API_BASE}/api/documents/${id}/export${artifact ? `/${artifact}` : ""}`,

  // --- AI推奨事項 (標準由来とは別リソース) ---

  listRecommendations: (id: number) =>
    request<Recommendation[]>(`/api/documents/${id}/recommendations`),

  recommendationStatus: (id: number) =>
    request<RecommendationStatus>(`/api/documents/${id}/recommendations/status`),

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

  reviewSetExportUrl: (id: number, artifact?: string) =>
    `${API_BASE}/api/review-sets/${id}/export${artifact ? `/${artifact}` : ""}`,
};
