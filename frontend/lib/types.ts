export type ResultValue = "OK" | "NG" | "N/A" | "Pending";

export type Severity = "Critical" | "High" | "Medium" | "Low";

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

export interface CoverageByType {
  rule_type: string;
  total: number;
  converted: number;
  unconverted: number;
  coverage: number;
}

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

export interface ReviewProgress {
  total: number;
  ok: number;
  ng: number;
  na: number;
  pending: number;
  by_severity: Record<string, number>;
}

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

export interface UnconvertedRow {
  standard_id: string;
  original_rule: string;
  reason_not_converted: string;
  required_action: string;
  owner: string;
  status: string;
}

export interface DocumentTypeOption {
  value: string;
  label: string;
  prefix: string;
}

export interface Meta {
  document_types: DocumentTypeOption[];
  rule_types: string[];
  severities: Severity[];
  result_values: ResultValue[];
  categories: string[];
  supported_extensions: string[];
}

// --- AI推奨事項 (標準由来とは別リソース) ---

export type AdoptionValue = "Proposed" | "Adopted" | "Rejected";

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

export interface RecommendationStatus {
  count: number;
  generators_available: string[];
  claude_available: boolean;
  claude_model: string;
  note: string;
}

// --- 統合レビュー表 (複数標準書の横断) ---

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

export interface ConsolidatedSource {
  check_id: string;
  standard_id: string;
  source_document: string;
  chapter: string;
  section: string;
  page: string;
}

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
