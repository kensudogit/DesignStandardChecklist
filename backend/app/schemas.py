from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResultValue = Literal["OK", "NG", "N/A", "Pending"]


class DocumentMetaUpdate(BaseModel):
    """STEP 1: 文書識別。取得できない項目は「不明」のまま残す。"""

    document_name: str | None = None
    document_type: str | None = None
    version: str | None = None
    established_date: str | None = None
    revised_date: str | None = None
    target_phase: str | None = None
    target_deliverable: str | None = None
    notes: str | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    document_name: str
    document_type: str
    document_type_label: str = ""
    id_prefix: str
    version: str
    established_date: str
    revised_date: str
    target_phase: str
    target_deliverable: str
    notes: str
    original_filename: str
    file_format: str
    status: str
    error_message: str | None
    block_count: int
    has_page_numbers: bool
    created_at: datetime
    analyzed_at: datetime | None
    rule_count: int = 0
    check_count: int = 0
    coverage: float | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    standard_id: str
    rule_type: str
    category: str
    original_rule: str
    normalized_requirement: str
    chapter: str | None
    section: str | None
    page: int | None
    heading_path: str
    locator: str | None
    condition: str | None
    exception: str | None
    ambiguity: str | None
    explicit_severity: str | None
    matched_markers: list[str]
    unconverted_reason: str | None
    check_ids: list[str] = Field(default_factory=list)


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: str
    no: int
    category: str
    sub_category: str
    check_point: str
    requirement: str
    severity: str
    severity_reason: str
    condition: str | None
    exception: str | None
    note: str | None
    merged_check_ids: list[str]
    similar_check_ids: list[str]
    extra_standard_ids: list[str]
    result: str
    evidence: str
    reviewer: str
    review_date: str
    comment: str
    # トレーサビリティ (STEP 12)
    standard_id: str = ""
    source_document: str = ""
    chapter: str | None = None
    section: str | None = None
    page: int | None = None
    locator: str | None = None
    original_rule: str = ""


class ChecklistItemUpdate(BaseModel):
    result: ResultValue | None = None
    evidence: str | None = None
    reviewer: str | None = None
    review_date: str | None = None
    comment: str | None = None


class CoverageByType(BaseModel):
    rule_type: str
    total: int
    converted: int
    unconverted: int
    coverage: float


class CoverageOut(BaseModel):
    total_rules: int
    target_rules: int
    converted_rules: int
    unconverted_rules: int
    coverage: float
    mandatory_total: int
    mandatory_converted: int
    mandatory_coverage: float
    prohibited_total: int
    prohibited_converted: int
    prohibited_coverage: float
    ambiguous_rules: int
    missing_source_rules: int
    duplicate_candidates: int
    check_count: int
    by_rule_type: list[CoverageByType]
    findings: list[str]
    analyzed_at: datetime | None = None


class ReviewProgress(BaseModel):
    total: int
    ok: int
    ng: int
    na: int
    pending: int
    by_severity: dict[str, int]


class TraceabilityRow(BaseModel):
    check_id: str
    standard_id: str
    source_document: str
    chapter: str | None
    section: str | None
    page: str
    trace_status: str
    notes: str


class UnconvertedRow(BaseModel):
    standard_id: str
    original_rule: str
    reason_not_converted: str
    required_action: str
    owner: str = ""
    status: str = "Open"


class DocumentTypeOption(BaseModel):
    value: str
    label: str
    prefix: str


class MetaOut(BaseModel):
    document_types: list[DocumentTypeOption]
    rule_types: list[str]
    severities: list[str]
    result_values: list[str]
    categories: list[str]
    supported_extensions: list[str]


# --- AI推奨事項 (必須原則 8: 標準由来と分離) ---------------------------------

AdoptionValue = Literal["Proposed", "Adopted", "Rejected"]


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recommendation_id: str
    no: int
    category: str
    sub_category: str
    check_point: str
    requirement: str
    severity: str
    rationale: str
    generator: str
    generator_detail: str
    adoption: str
    comment: str


class RecommendationRequest(BaseModel):
    #: catalog = 観点カタログ (APIキー不要) / claude = Claude API
    generator: Literal["catalog", "claude"] = "catalog"
    #: 既存の提案を置き換えるか
    replace: bool = True


class RecommendationUpdate(BaseModel):
    adoption: AdoptionValue | None = None
    comment: str | None = None


class RecommendationStatus(BaseModel):
    count: int
    generators_available: list[str]
    claude_available: bool
    claude_model: str
    note: str


# --- 統合レビュー表 (複数標準書の横断) ---------------------------------------


class ReviewSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    document_ids: list[int] = Field(min_length=1)
    notes: str = ""


class ReviewSetUpdate(BaseModel):
    name: str | None = None
    document_ids: list[int] | None = None
    notes: str | None = None


class ReviewSetMember(BaseModel):
    document_id: int
    document_code: str
    document_name: str
    document_type_label: str
    id_prefix: str
    rule_count: int
    check_count: int
    coverage: float | None


class ReviewSetOut(BaseModel):
    id: int
    name: str
    notes: str
    created_at: datetime
    consolidated_at: datetime | None
    documents: list[ReviewSetMember]
    check_count: int
    merged_count: int


class ConsolidatedSource(BaseModel):
    check_id: str
    standard_id: str
    source_document: str
    chapter: str
    section: str
    page: str


class ConsolidatedCheckOut(BaseModel):
    id: int
    no: int
    check_id: str
    category: str
    sub_category: str
    check_point: str
    requirement: str
    severity: str
    condition: str | None
    exception: str | None
    note: str | None
    #: 複数標準書に跨る出典 (STEP 11/12)
    sources: list[ConsolidatedSource]
    #: 統合された他文書のチェックID
    merged_check_ids: list[str]
    similar_check_ids: list[str]
    #: 記入内容は代表チェック項目のもの
    result: str
    evidence: str
    reviewer: str
    review_date: str
    comment: str


class ReviewSetCoverageRow(BaseModel):
    document_id: int
    document_name: str
    document_type_label: str
    coverage: float
    mandatory_coverage: float
    prohibited_coverage: float
    target_rules: int
    converted_rules: int
    unconverted_rules: int
    check_count: int


class ReviewSetCoverageOut(BaseModel):
    by_document: list[ReviewSetCoverageRow]
    total_target_rules: int
    total_converted_rules: int
    total_coverage: float
    total_checks_before_merge: int
    consolidated_checks: int
    merged_checks: int
    cross_document_similar: int
    findings: list[str]
