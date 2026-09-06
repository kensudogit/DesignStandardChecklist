from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: レビュー結果。未レビューは Pending で、CSV 出力時もこの表記のまま出す。
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
    """標準書1件の応答 (STEP 1: 標準書一覧)。

    規定数・チェック数・Coverage はモデルに無く、api/documents.py で数えて詰める。
    版数や制定日は読み取れなかった場合、空ではなく「不明」が入る。
    """
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
    """抽出した規定1件の応答 (STEP 3-6: 規定抽出一覧)。

    original_rule は標準書の原文そのまま、normalized_requirement はそれを
    要求事項の形に整えたもの。チェック項目の文言は必ずこのどちらかに由来する。
    """
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
    """レビューチェックリストの1行 (STEP 7-12)。

    1件の規定が複数のチェック項目へ分解されるため、standard_id は複数行で
    重複しうる。一意なのは check_id の方。
    """
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
    """レビュー結果の更新。未指定の項目は変更しない。

    画面が1欄ずつ保存してくるので、None を「変更なし」として扱う必要がある。
    """
    result: ResultValue | None = None
    evidence: str | None = None
    reviewer: str | None = None
    review_date: str | None = None
    comment: str | None = None


class CoverageByType(BaseModel):
    """規定種別ごとの変換率。"""
    rule_type: str
    total: int
    converted: int
    unconverted: int
    coverage: float


class CoverageOut(BaseModel):
    """Coverage レポート (STEP 13)。

    必須規定と禁止規定は、取りこぼすとレビューが成立しないため、
    全体の率とは別に集計する。
    """
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
    """レビューの進捗集計。by_severity は未判定も含めた重要度別の件数。"""
    total: int
    ok: int
    ng: int
    na: int
    pending: int
    by_severity: dict[str, int]


class TraceabilityRow(BaseModel):
    """トレーサビリティマトリクスの1行 (STEP 12)。"""
    check_id: str
    standard_id: str
    source_document: str
    chapter: str | None
    section: str | None
    page: str
    trace_status: str
    notes: str


class UnconvertedRow(BaseModel):
    """未変換規定一覧の1行 (STEP 13)。

    ここが空でないことは異常ではない。曖昧な規定は意図的に変換しない。
    """
    standard_id: str
    original_rule: str
    reason_not_converted: str
    required_action: str
    owner: str = ""
    status: str = "Open"


class DocumentTypeOption(BaseModel):
    """文書種別の選択肢。prefix は採番される ID の接頭辞。"""
    value: str
    label: str
    prefix: str


class MetaOut(BaseModel):
    """画面の選択肢をサーバ側の定義に合わせるためのマスタ。"""
    document_types: list[DocumentTypeOption]
    rule_types: list[str]
    severities: list[str]
    result_values: list[str]
    categories: list[str]
    supported_extensions: list[str]


# --- AI推奨事項 (必須原則 8: 標準由来と分離) ---------------------------------

AdoptionValue = Literal["Proposed", "Adopted", "Rejected"]


class RecommendationOut(BaseModel):
    """AI推奨事項1件。

    標準書に規定が無い観点の提案であり、出典 (章・節・ページ) を持たない。
    ChecklistItemOut とは別リソースとして扱う。
    """
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
    """AI推奨事項の生成要求。replace=True なら既存を総入れ替えする。"""
    generator: Literal["catalog", "claude"] = "catalog"
    #: 既存の提案を置き換えるか
    replace: bool = True


class RecommendationUpdate(BaseModel):
    """採否とコメントの更新。推奨内容そのものは書き換えない。"""
    adoption: AdoptionValue | None = None
    comment: str | None = None


class RecommendationStatus(BaseModel):
    """生成可否。claude_available が False なら API キーが未設定。"""
    count: int
    generators_available: list[str]
    claude_available: bool
    claude_model: str
    note: str


# --- 統合レビュー表 (複数標準書の横断) ---------------------------------------


class ReviewSetCreate(BaseModel):
    """統合レビュー表の作成要求。document_ids は解析済みの標準書を指す。"""
    name: str = Field(min_length=1, max_length=255)
    document_ids: list[int] = Field(min_length=1)
    notes: str = ""


class ReviewSetUpdate(BaseModel):
    """統合レビュー表の更新。対象標準書を入れ替えると再統合が必要になる。"""
    name: str | None = None
    document_ids: list[int] | None = None
    notes: str | None = None


class ReviewSetMember(BaseModel):
    """統合レビュー表に含まれる標準書1件の要約。"""
    document_id: int
    document_code: str
    document_name: str
    document_type_label: str
    id_prefix: str
    rule_count: int
    check_count: int
    coverage: float | None


class ReviewSetOut(BaseModel):
    """統合レビュー表。

    consolidated_at が None の間は、標準書を登録しただけで統合が未実行の状態。
    """
    id: int
    name: str
    notes: str
    created_at: datetime
    consolidated_at: datetime | None
    documents: list[ReviewSetMember]
    check_count: int
    merged_count: int


class ConsolidatedSource(BaseModel):
    """統合チェック項目の出典1件。1項目が複数の標準書を根拠に持ちうる。"""
    check_id: str
    standard_id: str
    source_document: str
    chapter: str
    section: str
    page: str


class ConsolidatedCheckOut(BaseModel):
    """統合レビュー表の1行。

    ChecklistItemOut と違い、出典が sources の配列になっている。同じ内容の
    規定が複数の標準書にある場合、1行にまとめて出典を並べるため。
    """
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
    """統合レビュー表の Coverage を標準書ごとに分解した1行。"""
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
    """統合レビュー表全体の Coverage。

    total_checks_before_merge と consolidated_checks の差が、重複統合により
    減った項目数にあたる。
    """
    by_document: list[ReviewSetCoverageRow]
    total_target_rules: int
    total_converted_rules: int
    total_coverage: float
    total_checks_before_merge: int
    consolidated_checks: int
    merged_checks: int
    cross_document_similar: int
    findings: list[str]
