from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StandardDocument(Base):
    """STEP 1: 標準書一覧 (standard-register)。"""

    __tablename__ = "standard_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(32), unique=True)  # DOC-001
    document_name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(32))  # taxonomy.DOC_TYPE_PREFIX のキー
    id_prefix: Mapped[str] = mapped_column(String(8))
    version: Mapped[str] = mapped_column(String(64), default="不明")
    established_date: Mapped[str] = mapped_column(String(64), default="不明")
    revised_date: Mapped[str] = mapped_column(String(64), default="不明")
    target_phase: Mapped[str] = mapped_column(String(128), default="不明")
    target_deliverable: Mapped[str] = mapped_column(String(128), default="不明")
    notes: Mapped[str] = mapped_column(Text, default="")

    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    file_format: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")  # uploaded/analyzed/failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    has_page_numbers: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rules: Mapped[list[Rule]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    checks: Mapped[list[ChecklistItem]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Rule(Base):
    """STEP 3-6: 規定抽出一覧 (extracted-rules)。"""

    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("document_pk", "standard_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_pk: Mapped[int] = mapped_column(ForeignKey("standard_documents.id", ondelete="CASCADE"))
    standard_id: Mapped[str] = mapped_column(String(32))  # STD-UI-001
    rule_type: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64))
    original_rule: Mapped[str] = mapped_column(Text)
    normalized_requirement: Mapped[str] = mapped_column(Text)
    chapter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    section: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_path: Mapped[str] = mapped_column(String(512), default="")
    locator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)
    ambiguity: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    explicit_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    matched_markers: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: STEP 13: チェック項目化できなかった理由 (未変換規定一覧の出力元)
    unconverted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[StandardDocument] = relationship(back_populates="rules")
    checks: Mapped[list[ChecklistItem]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class ChecklistItem(Base):
    """STEP 7-12: レビューチェックリスト1行。"""

    __tablename__ = "checklist_items"
    __table_args__ = (UniqueConstraint("document_pk", "check_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_pk: Mapped[int] = mapped_column(ForeignKey("standard_documents.id", ondelete="CASCADE"))
    rule_pk: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"))
    check_id: Mapped[str] = mapped_column(String(32))  # CHK-UI-001
    no: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(64))
    sub_category: Mapped[str] = mapped_column(String(128), default="")
    check_point: Mapped[str] = mapped_column(Text)
    requirement: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    severity_reason: Mapped[str] = mapped_column(String(255), default="")
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: STEP 11: 統合された完全重複 / 類似候補
    merged_check_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    similar_check_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: 複数標準を根拠とする場合の追加出典 (STEP 11)
    extra_standard_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    # レビュー実施時に人が埋める列
    result: Mapped[str] = mapped_column(String(16), default="Pending")  # OK/NG/N/A/Pending
    evidence: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(128), default="")
    review_date: Mapped[str] = mapped_column(String(32), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    document: Mapped[StandardDocument] = relationship(back_populates="checks")
    rule: Mapped[Rule] = relationship(back_populates="checks")


class AnalysisRun(Base):
    """STEP 13: Coverage レポートのスナップショット。"""

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_pk: Mapped[int] = mapped_column(ForeignKey("standard_documents.id", ondelete="CASCADE"))
    total_rules: Mapped[int] = mapped_column(Integer, default=0)
    target_rules: Mapped[int] = mapped_column(Integer, default=0)
    converted_rules: Mapped[int] = mapped_column(Integer, default=0)
    unconverted_rules: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    mandatory_total: Mapped[int] = mapped_column(Integer, default=0)
    mandatory_converted: Mapped[int] = mapped_column(Integer, default=0)
    prohibited_total: Mapped[int] = mapped_column(Integer, default=0)
    prohibited_converted: Mapped[int] = mapped_column(Integer, default=0)
    ambiguous_rules: Mapped[int] = mapped_column(Integer, default=0)
    missing_source_rules: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_candidates: Mapped[int] = mapped_column(Integer, default=0)
    check_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Recommendation(Base):
    """AI推奨事項 (必須原則 8)。

    標準書由来のチェック項目とは別テーブルに保持する。こうしておけば、
    チェックリスト・トレーサビリティ・Coverage のどの問い合わせにも構造的に混入しない。
    出典は持たない (標準書に無い以上、章・節・ページは存在しない)。
    """

    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("document_pk", "recommendation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_pk: Mapped[int] = mapped_column(ForeignKey("standard_documents.id", ondelete="CASCADE"))
    recommendation_id: Mapped[str] = mapped_column(String(32))  # REC-UI-001
    no: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(64))
    sub_category: Mapped[str] = mapped_column(String(128), default="")
    check_point: Mapped[str] = mapped_column(Text)
    requirement: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    #: なぜ追加を提案するのか (標準書に無いことの説明)
    rationale: Mapped[str] = mapped_column(Text, default="")
    #: catalog (観点カタログ由来) / claude (Claude API 生成)
    generator: Mapped[str] = mapped_column(String(16), default="catalog")
    generator_detail: Mapped[str] = mapped_column(String(128), default="")
    #: 採否。標準由来ではないため、採用するかは人が決める。
    adoption: Mapped[str] = mapped_column(String(16), default="Proposed")  # Proposed/Adopted/Rejected
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ReviewSet(Base):
    """統合レビュー表 (複数標準書の横断チェックリスト)。"""

    __tablename__ = "review_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    consolidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    members: Mapped[list[ReviewSetDocument]] = relationship(
        back_populates="review_set", cascade="all, delete-orphan", order_by="ReviewSetDocument.position"
    )
    checks: Mapped[list[ConsolidatedCheck]] = relationship(
        back_populates="review_set", cascade="all, delete-orphan"
    )


class ReviewSetDocument(Base):
    """統合レビュー表に含める標準書。"""

    __tablename__ = "review_set_documents"
    __table_args__ = (UniqueConstraint("review_set_pk", "document_pk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_set_pk: Mapped[int] = mapped_column(ForeignKey("review_sets.id", ondelete="CASCADE"))
    document_pk: Mapped[int] = mapped_column(ForeignKey("standard_documents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    review_set: Mapped[ReviewSet] = relationship(back_populates="members")
    document: Mapped[StandardDocument] = relationship()


class ConsolidatedCheck(Base):
    """統合チェックリストの1行。

    レビュー結果は保持しない。記入は代表チェック項目と統合されたチェック項目
    (= 同一内容の別標準書の項目) へ書き戻すため、真実の所在はひとつに保たれる。
    """

    __tablename__ = "consolidated_checks"
    __table_args__ = (UniqueConstraint("review_set_pk", "no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_set_pk: Mapped[int] = mapped_column(ForeignKey("review_sets.id", ondelete="CASCADE"))
    no: Mapped[int] = mapped_column(Integer)
    #: 代表となる各文書側チェック項目
    primary_item_pk: Mapped[int] = mapped_column(
        ForeignKey("checklist_items.id", ondelete="CASCADE")
    )
    #: 同一内容として統合された他文書のチェック項目 (代表を含まない)
    merged_item_pks: Mapped[list[int]] = mapped_column(JSON, default=list)
    #: 類似だが統合はしていない Check ID (人が判断する)
    similar_check_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(16))

    review_set: Mapped[ReviewSet] = relationship(back_populates="checks")
    primary_item: Mapped[ChecklistItem] = relationship()


class User(Base):
    """レビュー担当者。auth_enabled のときだけ使う。

    誰が判定したのかを Reviewer 欄と結び付けるため、共有トークンではなく
    個人アカウントにしている。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
