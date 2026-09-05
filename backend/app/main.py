from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, documents, exports, recommendations, review_sets
from app.config import get_settings
from app.core import taxonomy as tx
from app.core.parsers import SUPPORTED_EXTENSIONS
from app.db import init_db
from app.schemas import DocumentTypeOption, MetaOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Design Standard Checklist Generator",
    description=(
        "設計標準書からレビュー用チェックリストを生成する API。"
        "規定抽出 → Atomic Check 分解 → 重要度付与 → トレーサビリティ → Coverage 検証。"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(documents.router)
app.include_router(analysis.router)
app.include_router(exports.router)
app.include_router(recommendations.router)
app.include_router(review_sets.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta", response_model=MetaOut)
def meta() -> MetaOut:
    """フロントエンドが選択肢を組み立てるための語彙一覧。"""
    return MetaOut(
        document_types=[
            DocumentTypeOption(value=key, label=tx.DOC_TYPE_LABEL[key], prefix=prefix)
            for key, prefix in tx.DOC_TYPE_PREFIX.items()
        ],
        rule_types=list(tx.RULE_TYPES),
        severities=list(tx.SEVERITIES),
        result_values=["OK", "NG", "N/A", "Pending"],
        categories=[c for c, _ in tx.CATEGORY_KEYWORDS] + [tx.DEFAULT_CATEGORY, "例外"],
        supported_extensions=sorted(SUPPORTED_EXTENSIONS),
    )
