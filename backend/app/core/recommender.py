"""STEP 14-7: AI推奨事項の生成（要求された場合のみ）。

必須原則 8「AI推奨事項を追加する場合は、標準由来と明確に分離する」を守るため、
ここで作るものは Recommendation テーブルにしか入らない。チェックリスト・
トレーサビリティ・Coverage には一切混ざらない。

2つの生成方式がある。
- catalog: 観点カタログと標準書の突き合わせ。APIキー不要で決定的。
- claude:  Claude API に標準書の規定一覧を渡し、不足観点を提案させる。

いずれも「標準書に規定が無い観点」だけを提案する。標準書に書いてあることを
言い換えて出すのは、標準由来の項目と重複するだけで価値が無い。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.core import taxonomy as tx
from app.core.viewpoints import Viewpoint, viewpoints_for

logger = logging.getLogger(__name__)

#: 提案数の上限。多すぎると標準由来の項目が埋もれる。
MAX_RECOMMENDATIONS = 20

CLAUDE_MODEL = "claude-opus-5"


class RecommendationError(RuntimeError):
    pass


@dataclass
class Recommendation:
    category: str
    sub_category: str
    check_point: str
    requirement: str
    severity: str
    rationale: str
    generator: str
    generator_detail: str = ""


def _covered(viewpoint: Viewpoint, haystack: str) -> bool:
    return any(keyword in haystack for keyword in viewpoint.keywords)


def catalog_recommendations(
    document_type: str,
    rule_texts: list[str],
    check_points: list[str],
) -> list[Recommendation]:
    """観点カタログのうち、標準書が触れていないものを提案する。"""
    haystack = " ".join(rule_texts) + " " + " ".join(check_points)
    label = tx.DOC_TYPE_LABEL.get(document_type, document_type)

    out: list[Recommendation] = []
    for viewpoint in viewpoints_for(document_type):
        if _covered(viewpoint, haystack):
            continue
        out.append(
            Recommendation(
                category=viewpoint.category,
                sub_category=viewpoint.sub_category,
                check_point=viewpoint.check_point,
                requirement=viewpoint.check_point.rstrip("？?").replace("定義されているか", "定義されている"),
                severity=viewpoint.severity,
                rationale=(
                    f"{label}に「{viewpoint.sub_category}」に関する規定が見当たらないため、"
                    "レビュー観点としての追加を提案します（標準書由来ではありません）。"
                ),
                generator="catalog",
                generator_detail="観点カタログ (SKILL.md 5章・6章)",
            )
        )
    return out[:MAX_RECOMMENDATIONS]


# --- Claude API を使う生成 ---------------------------------------------------


SYSTEM_PROMPT = """あなたは日本の業務システム開発における設計レビューの専門家です。

与えられた設計標準書の規定一覧を読み、**その標準書には規定が無いが、設計レビューでは
確認すべき観点**を提案してください。

厳守事項:
1. 標準書に既に規定がある内容は提案しない。言い換えただけの重複は無価値です。
2. 標準書に書いていない規定を「標準書の規定である」と書かない。提案はあくまで提案です。
3. チェック項目は Yes / No / N/A で判定できる疑問文にし、末尾を「〜か？」とする。
4. 1つのチェック項目には1つの確認事項だけを入れる。
5. 章・節・ページなどの出典は書かない。標準書に無い以上、出典は存在しません。
6. 提案は最大10件。数より、抜けると手戻りが大きい観点を優先する。"""

USER_TEMPLATE = """# 対象標準書

- 文書名: {document_name}
- 文書種別: {document_type_label}

# この標準書から抽出済みの規定（{rule_count}件）

{rules}

# 依頼

上記の規定に含まれていない、この種別の設計レビューで確認すべき観点を提案してください。
severity は Critical / High / Medium / Low のいずれか、category は次から選んでください。

{categories}"""


def _build_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "sub_category": {"type": "string"},
                        "check_point": {"type": "string"},
                        "requirement": {"type": "string"},
                        "severity": {"type": "string", "enum": list(tx.SEVERITIES)},
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "category",
                        "sub_category",
                        "check_point",
                        "requirement",
                        "severity",
                        "rationale",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["recommendations"],
        "additionalProperties": False,
    }


def claude_available() -> bool:
    """Claude API を呼べる状態か。SDK未導入・資格情報なしのどちらでも False。"""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def claude_recommendations(
    *,
    document_name: str,
    document_type: str,
    rule_texts: list[str],
) -> list[Recommendation]:
    """Claude に不足観点を提案させる。資格情報が無い場合は RecommendationError。"""
    try:
        import anthropic
    except ImportError as exc:
        raise RecommendationError(
            "Claude API を使うには anthropic SDK が必要です。"
            "backend で pip install -r requirements-optional.txt を実行するか、"
            "追加インストール不要の「観点カタログ」方式（generator=catalog）を使用してください。"
        ) from exc

    if not claude_available():
        raise RecommendationError(
            "ANTHROPIC_API_KEY が設定されていません。"
            "環境変数を設定するか、APIキー不要の「観点カタログ」方式"
            "（generator=catalog）を使用してください。"
        )

    categories = "、".join([c for c, _ in tx.CATEGORY_KEYWORDS])
    prompt = USER_TEMPLATE.format(
        document_name=document_name,
        document_type_label=tx.DOC_TYPE_LABEL.get(document_type, document_type),
        rule_count=len(rule_texts),
        rules="\n".join(f"- {text}" for text in rule_texts),
        categories=categories,
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _build_schema()}},
        )
    except anthropic.AuthenticationError as exc:
        raise RecommendationError("ANTHROPIC_API_KEY が無効です。") from exc
    except anthropic.RateLimitError as exc:
        raise RecommendationError(
            "Claude API がレート制限中です。しばらく待って再実行してください。"
        ) from exc
    except anthropic.APIStatusError as exc:
        raise RecommendationError(f"Claude API がエラーを返しました ({exc.status_code})。") from exc
    except anthropic.APIConnectionError as exc:
        raise RecommendationError("Claude API へ接続できませんでした。") from exc

    if response.stop_reason == "refusal":
        raise RecommendationError("Claude が応答を拒否しました。入力内容を確認してください。")

    payload = _parse_payload(response)
    return _to_recommendations(payload, rule_texts)


def _parse_payload(response: object) -> dict:
    import json

    text = "".join(
        block.text  # type: ignore[attr-defined]
        for block in response.content  # type: ignore[attr-defined]
        if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise RecommendationError("Claude から空の応答が返りました。")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RecommendationError("Claude の応答をJSONとして解釈できませんでした。") from exc


def _to_recommendations(payload: dict, rule_texts: list[str]) -> list[Recommendation]:
    haystack = " ".join(rule_texts)
    out: list[Recommendation] = []
    for raw in payload.get("recommendations", [])[:MAX_RECOMMENDATIONS]:
        check_point = str(raw.get("check_point", "")).strip()
        if not check_point:
            continue
        if not check_point.endswith(("か？", "か?")):
            check_point = check_point.rstrip("。？?") + "か？"
        severity = str(raw.get("severity", "Medium"))
        if severity not in tx.SEVERITIES:
            severity = "Medium"
        # 標準書に既にある内容の言い換えは落とす
        core = check_point.rstrip("か？?")
        if len(core) >= 8 and core in haystack:
            continue
        out.append(
            Recommendation(
                category=str(raw.get("category", tx.DEFAULT_CATEGORY)),
                sub_category=str(raw.get("sub_category", "")),
                check_point=check_point,
                requirement=str(raw.get("requirement", "")).strip() or core,
                severity=severity,
                rationale=str(raw.get("rationale", "")).strip()
                or "標準書に規定が無い観点として提案されました（標準書由来ではありません）。",
                generator="claude",
                generator_detail=f"Claude API ({CLAUDE_MODEL})",
            )
        )
    return out


def generate(
    *,
    generator: str,
    document_name: str,
    document_type: str,
    rule_texts: list[str],
    check_points: list[str],
) -> list[Recommendation]:
    if generator == "claude":
        return claude_recommendations(
            document_name=document_name,
            document_type=document_type,
            rule_texts=rule_texts,
        )
    if generator == "catalog":
        return catalog_recommendations(document_type, rule_texts, check_points)
    raise RecommendationError(f"未知の生成方式です: {generator}")
