/**
 * バックエンド (`backend/app/schemas.py`) が返す JSON の型定義。
 *
 * サーバ側の Pydantic スキーマと1対1で対応させている。フィールド名・省略可否を
 * 変更するときは、必ず `schemas.py` と両方を直すこと。片方だけ直すと型は通るのに
 * 実行時に undefined が入る、という壊れ方をする。
 *
 * コメント中の STEP 番号は、標準書をチェックリストへ変換する13段階のパイプライン
 * (`backend/app/core/pipeline.py`) の工程番号を指す。
 */

/** レビュー結果。未レビューは `Pending` で、CSV 出力時もこの表記のまま出す。 */
export type ResultValue = "OK" | "NG" | "N/A" | "Pending";

/** チェック項目の重要度 (STEP 9)。標準書に明示があればそれを、無ければ推定して付ける。 */
export type Severity = "Critical" | "High" | "Medium" | "Low";

/**
 * アップロードされた標準書1件 (STEP 1: 標準書一覧)。
 *
 * `version` や `established_date` などのメタ情報は、文書から読み取れなかった場合
 * 空ではなく文字列 "不明" が入る。空文字と "不明" は意味が違うので、表示時に
 * 潰さないこと。
 */
export interface StandardDocument {
  id: number;
  document_id: string;
  document_name: string;
  document_type: string;
  document_type_label: string;
  id_prefix: string;
  version: string;
  established_date: string;
  revised_date: string;
  target_phase: string;
  target_deliverable: string;
  notes: string;
  original_filename: string;
  file_format: string;
  status: "uploaded" | "analyzed" | "failed";
  error_message: string | null;
  block_count: number;
  has_page_numbers: boolean;
  created_at: string;
  analyzed_at: string | null;
  rule_count: number;
  check_count: number;
  coverage: number | null;
}

/**
 * 標準書から抽出した規定1件 (STEP 3-6: 規定抽出一覧)。
 *
 * `original_rule` は標準書の原文そのままで、`normalized_requirement` はそれを
 * 要求事項の形に整えたもの。チェック項目の文言は必ずこのどちらかに由来する
 * (標準書に無い語を混ぜない、という必須原則のため)。
 */
export interface Rule {
  id: number;
  standard_id: string;
  rule_type: string;
  category: string;
  original_rule: string;
  normalized_requirement: string;
  chapter: string | null;
  section: string | null;
  page: number | null;
  heading_path: string;
  locator: string | null;
  condition: string | null;
  exception: string | null;
  ambiguity: string | null;
  explicit_severity: string | null;
  matched_markers: string[];
  unconverted_reason: string | null;
  check_ids: string[];
}

/**
 * レビューチェックリストの1行 (STEP 7-12)。
 *
 * 1件の規定 (`Rule`) が複数のチェック項目へ分解されるため、`standard_id` は
 * 複数の項目で重複しうる。一意なのは `check_id` の方。
 */
export interface ChecklistItem {
  id: number;
  check_id: string;
  no: number;
  category: string;
  sub_category: string;
  check_point: string;
  requirement: string;
  severity: Severity;
  severity_reason: string;
  condition: string | null;
  exception: string | null;
  origin: string;
  note: string | null;
  merged_check_ids: string[];
  similar_check_ids: string[];
  extra_standard_ids: string[];
  result: ResultValue;
  evidence: string;
  reviewer: string;
  review_date: string;
  comment: string;
  standard_id: string;
  source_document: string;
  chapter: string | null;
  section: string | null;
  page: number | null;
  locator: string | null;
  original_rule: string;
}

/** 規定種別 (必須/禁止/推奨など) ごとの変換率。 */
export interface CoverageByType {
  rule_type: string;
  total: number;
  converted: number;
  unconverted: number;
  coverage: number;
}

/**
 * Coverage レポート (STEP 13)。抽出した規定のうち何件をチェック項目化できたかを表す。
 *
 * 必須規定 (`mandatory_*`) と禁止規定 (`prohibited_*`) は、取りこぼすと
 * レビューが成立しないため全体の率とは別に集計している。
 */
export interface Coverage {
  total_rules: number;
  target_rules: number;
  converted_rules: number;
  unconverted_rules: number;
  coverage: number;
  mandatory_total: number;
  mandatory_converted: number;
  mandatory_coverage: number;
  prohibited_total: number;
  prohibited_converted: number;
  prohibited_coverage: number;
  ambiguous_rules: number;
  missing_source_rules: number;
  duplicate_candidates: number;
  check_count: number;
  by_rule_type: CoverageByType[];
  findings: string[];
  analyzed_at: string | null;
}

/** レビューの進捗集計。画面上部の進捗バーで使う。 */
export interface ReviewProgress {
  total: number;
  ok: number;
  ng: number;
  na: number;
  pending: number;
  by_severity: Record<string, number>;
}

/** トレーサビリティマトリクスの1行 (STEP 12)。チェック項目と出典の対応を示す。 */
export interface TraceabilityRow {
  check_id: string;
  standard_id: string;
  source_document: string;
  chapter: string | null;
  section: string | null;
  page: string;
  trace_status: string;
  notes: string;
}

/**
 * 未変換規定一覧の1行 (STEP 13)。
 *
 * チェック項目にできなかった規定を、理由付きで残すためのもの。ここが空でない
 * ことは異常ではない (曖昧な規定は意図的に変換しない)。
 */
export interface UnconvertedRow {
  standard_id: string;
  original_rule: string;
  reason_not_converted: string;
  required_action: string;
  owner: string;
  status: string;
}

/** アップロード画面の文書種別プルダウン1件。`prefix` は採番される ID の接頭辞。 */
export interface DocumentTypeOption {
  value: string;
  label: string;
  prefix: string;
}

/** 画面の選択肢をサーバ側の定義に合わせるためのマスタ。起動時に1回だけ取得する。 */
export interface Meta {
  document_types: DocumentTypeOption[];
  rule_types: string[];
  severities: Severity[];
  result_values: ResultValue[];
  categories: string[];
  supported_extensions: string[];
}

// --- AI推奨事項 (標準由来とは別リソース) ---

/** AI推奨事項の採否。既定は `Proposed` (未判断)。 */
export type AdoptionValue = "Proposed" | "Adopted" | "Rejected";

/**
 * AI推奨事項1件。
 *
 * 標準書に規定が無い観点の提案であり、`ChecklistItem` とは別リソースとして扱う。
 * 標準由来の成果物に混ぜてはいけない。
 */
export interface Recommendation {
  id: number;
  recommendation_id: string;
  no: number;
  category: string;
  sub_category: string;
  check_point: string;
  requirement: string;
  severity: Severity;
  rationale: string;
  generator: string;
  generator_detail: string;
  adoption: AdoptionValue;
  comment: string;
}

/** AI推奨事項の生成可否。`claude_available` が false なら API キー未設定。 */
export interface RecommendationStatus {
  count: number;
  generators_available: string[];
  claude_available: boolean;
  claude_model: string;
  note: string;
}

// --- 統合レビュー表 (複数標準書の横断) ---

/** 統合レビュー表に含まれる標準書1件の要約。 */
export interface ReviewSetMember {
  document_id: number;
  document_code: string;
  document_name: string;
  document_type_label: string;
  id_prefix: string;
  rule_count: number;
  check_count: number;
  coverage: number | null;
}

/**
 * 複数の標準書を横断する統合レビュー表。
 *
 * `consolidated_at` が null の間は、標準書を登録しただけで統合処理が未実行の状態。
 */
export interface ReviewSet {
  id: number;
  name: string;
  notes: string;
  created_at: string;
  consolidated_at: string | null;
  documents: ReviewSetMember[];
  check_count: number;
  merged_count: number;
}

/** 統合チェック項目の出典1件。統合により1項目が複数の標準書を根拠に持ちうる。 */
export interface ConsolidatedSource {
  /** 出典の標準書。画面から該当箇所へ辿るために使う (文書名は一意ではない)。 */
  document_id: number;
  check_id: string;
  standard_id: string;
  source_document: string;
  chapter: string;
  section: string;
  page: string;
}

/**
 * 統合レビュー表の1行。
 *
 * `ChecklistItem` と違い、出典が `sources` の配列になっている。同じ内容の規定が
 * 複数の標準書にある場合、1行にまとめて出典を並べるため。
 */
export interface ConsolidatedCheck {
  id: number;
  no: number;
  check_id: string;
  category: string;
  sub_category: string;
  check_point: string;
  requirement: string;
  severity: Severity;
  condition: string | null;
  exception: string | null;
  note: string | null;
  sources: ConsolidatedSource[];
  merged_check_ids: string[];
  similar_check_ids: string[];
  result: ResultValue;
  evidence: string;
  reviewer: string;
  review_date: string;
  comment: string;
}

/** 統合レビュー表の Coverage を標準書ごとに分解した1行。 */
export interface ReviewSetCoverageRow {
  document_id: number;
  document_name: string;
  document_type_label: string;
  coverage: number;
  mandatory_coverage: number;
  prohibited_coverage: number;
  target_rules: number;
  converted_rules: number;
  unconverted_rules: number;
  check_count: number;
}

/**
 * 統合レビュー表全体の Coverage。
 *
 * `total_checks_before_merge` と `consolidated_checks` の差が、重複統合により
 * 減った項目数にあたる。
 */
export interface ReviewSetCoverage {
  by_document: ReviewSetCoverageRow[];
  total_target_rules: number;
  total_converted_rules: number;
  total_coverage: number;
  total_checks_before_merge: number;
  consolidated_checks: number;
  merged_checks: number;
  cross_document_similar: number;
  findings: string[];
}

// --- 認証 (DSC_AUTH_ENABLED=true のときのみ使う) ---

/** ログイン中の利用者。レビュー結果の記入者と紐付けるために使う。 */
export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
}

/**
 * 認証の状態。
 *
 * `auth_enabled` が false なら認証機能そのものが無効 (誰でも使える)。
 * `needs_bootstrap` は、認証は有効だがまだ管理者が1人もいない初期状態を指す。
 */
export interface AuthStatus {
  auth_enabled: boolean;
  needs_bootstrap: boolean;
  user: AuthUser | null;
}

/** ログイン成功時の応答。`expires_in` は秒数。 */
export interface LoginResponse {
  token: string;
  expires_in: number;
  user: AuthUser;
}
