"""STEP 5 補助: 規定か記述例かの判定だけを Claude に手伝わせる（要求された場合のみ）。

ルールベースの抽出が規範表現を見つけられなかった行だけが対象。表形式の標準書は
「要件IDを必ず紐付ける」「正常系と主要異常系を記載」のように体言止め・連用形で
書かれることが多く、「〜すること」のような語尾を持たない。語尾の語彙表を広げて
拾おうとすると、今度は記述例（「受注登録：顧客注文を登録し在庫引当へ連携」）まで
規定として拾ってしまう。この線引きだけを任せる。

**Claude に新しい文は書かせない。** 答えさせるのは次の3つだけで、いずれも
選択か原文の部分文字列であり、生成ではない。

  - その行が規定か、記述例か (boolean)
  - 規定なら規範レベル (RULE_TYPES からの選択)
  - そう判断した根拠となる原文中の語 (原文の部分文字列であることを検証する)

チェック項目の文言は、従来どおりこちら側が原文から組み立てる。根拠の語が原文に
無ければその判定は捨て、ルールベースの結果（＝規定としない）に戻す。標準書に無い
語が混ざる経路を残さないため（必須原則 1「標準書に記載されていない規定を追加しない」）。

同じ規定文には常に同じ答えを返す必要がある。再解析でチェック項目が増減すると
Check ID がずれ、記入済みのレビュー結果が別項目に付いてしまうため、応答は
規定文をキーにキャッシュする。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core import taxonomy as tx

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-5"

#: プロンプトを変えたら上げる。キャッシュのキーに含める。
PROMPT_VERSION = "2"

#: 規定抽出一覧に残す来歴。標準書由来であることは変わらないが、規定と判断したのが
#: ルールベースではないことを読み手に分かるようにする。
ASSIST_MARKER = "AI判定"

#: Claude に選ばせる規範レベル。Reference は「規定ではない」と同義なので入れない。
ALLOWED_RULE_TYPES = ("Mandatory", "Prohibited", "Conditional Mandatory", "Recommended", "Optional")

#: 問い合わせる長さの範囲。短すぎる行は判定材料が無く、長すぎる行は
#: 表のセルではなく本文なのでルールベースで足りる。
MIN_LEN = 5
MAX_LEN = 120

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_rule": {
            "type": "boolean",
            "description": "設計者が守るべき規定なら true。記述例・サンプル値・見出しなら false。",
        },
        "rule_type": {
            "type": "string",
            "enum": list(ALLOWED_RULE_TYPES),
            "description": "規定の場合の規範レベル。規定でない場合も何か1つ選ぶ（無視される）。",
        },
        "evidence": {
            "type": "string",
            "description": (
                "判断の決め手になった語句。原文中の連続した部分文字列で、"
                "決め手として意味を成す最小限の長さにすること。原文に無い語を書かない。"
            ),
        },
    },
    "required": ["is_rule", "rule_type", "evidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたは設計標準書のレビュー支援を行う。

与えられるのは、設計標準書の表から取り出した1行である。この行が
「設計者が守るべき規定」か、「書き方を示す記述例・サンプル値」かを判定する。

規定の例:
  要件IDを必ず紐付ける          -> 規定 (Mandatory)
  正常系と主要異常系を記載        -> 規定 (Mandatory)
  1機能1責務を原則              -> 規定 (Recommended)
  握りつぶさない                -> 規定 (Prohibited)

記述例の例:
  受注登録：顧客注文を登録し在庫引当へ連携  -> 記述例 (特定の機能の説明)
  F-ORD-001 受注登録                    -> 記述例 (サンプルのID)
  ORDER / ORDER_DETAIL                 -> 記述例 (テーブル名の例)
  受付→在庫確認→受注確定                 -> 記述例 (フローの例)

判断の指針:
- 一般の設計に対する指示なら規定。特定の機能・画面・テーブルの具体例なら記述例。
- 体言止めや連用形で終わっていても、指示であれば規定として扱う。
- 迷ったら記述例とする（規定でないものを規定にする方が害が大きい）。

evidence には、判断の決め手になった語句を原文からそのまま抜き出して書く。

- 原文に現れない語を書いてはならない。要約も言い換えもしない。
- 決め手として意味を成す範囲で、できるだけ短く切り出す。行全体を写さない。

  要件IDを必ず紐付ける       -> evidence: 必ず
  正常系と主要異常系を記載     -> evidence: 記載
  1機能1責務を原則           -> evidence: 原則
  握りつぶさない             -> evidence: 握りつぶさない
"""

USER_TEMPLATE = """次の1行を判定してください。

{sentence}"""


#: 分類の選択肢。taxonomy の分類名をそのまま使う。
CATEGORY_NAMES = tuple(name for name, _ in tx.CATEGORY_KEYWORDS)

CATEGORY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": list(CATEGORY_NAMES),
            "description": "最も近い分類。一覧に無い分類は選べない。",
        },
    },
    "required": ["category"],
    "additionalProperties": False,
}

CATEGORY_SYSTEM = """あなたは設計標準書のレビュー支援を行う。

与えられた規定を、次の分類のいずれかに割り当てる。

{names}

判断の指針:
- 標準書自身が書いている分類名 (「観点」「分類」列の値) があれば、それに最も近いものを選ぶ。
- 無ければ規定の内容から判断する。
- どれにも当てはまらないと感じたら「完全性」を選ぶ。
""".format(names=chr(10).join("  - " + n for n in CATEGORY_NAMES))

CATEGORY_TEMPLATE = """規定: {sentence}
標準書が書いている分類: {hint}"""


#: 列の役割の選択肢。table_schema の HEADER_KEYWORDS と同じ語彙。
COLUMN_ROLES = ("rule", "chapter", "section", "category", "rule_type", "severity", "no", "note")

COLUMNS_SCHEMA = {
    "type": "object",
    "properties": {
        "columns": {
            "type": "array",
            "description": "役割が分かった列だけを挙げる。分からない列は挙げない。",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "0 から数えた列番号"},
                    "role": {"type": "string", "enum": list(COLUMN_ROLES)},
                },
                "required": ["index", "role"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["columns"],
    "additionalProperties": False,
}

COLUMNS_SYSTEM = """あなたは設計標準書のレビュー支援を行う。

与えられるのは、設計標準書の表のヘッダ行である。各列がどの役割かを判定する。

役割:
  rule       設計者が守るべき規定の本文が入る列 (「規定内容」「ルール」「確認内容」等)
  chapter    章番号
  section    節番号 / 項番
  category   分類 / 観点
  rule_type  必須・禁止・推奨などの区分
  severity   重要度 / 重大度 / 優先度
  no         連番
  note       備考

判断の指針:
- 役割が分からない列は挙げない。無理に割り当てない。
- rule は必ず1つに絞る。規定の本文が入る列が特定できなければ、columns を空にする。
- 「良い例」「悪い例」「OK例」「NG例」「サンプル」は規定の本文ではない。挙げない。
"""

COLUMNS_TEMPLATE = """次のヘッダ行の各列の役割を判定してください。

{header}"""


def claude_available() -> bool:
    """SDK と資格情報が揃っているか。"""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def is_candidate(sentence: str) -> bool:
    """Claude に投げる価値がある行か（費用と待ち時間の節約）。"""
    return MIN_LEN <= len(sentence) <= MAX_LEN


def _normalize(text: str) -> str:
    """根拠の照合用。空白の違いだけで捨てないようにする。"""
    return re.sub(r"[\s　]+", "", text)


def validate(sentence: str, payload: dict) -> tuple[str, str] | None:
    """応答を検証して (rule_type, evidence) を返す。使えなければ None。

    検証する点は3つ。
      - 規定と判定されていること
      - 規範レベルが選択肢に入っていること (Claude が勝手な値を返していないこと)
      - 根拠が原文の部分文字列であること (原文に無い語を持ち込ませないため)
    """
    if not payload.get("is_rule"):
        return None

    rule_type = payload.get("rule_type")
    if rule_type not in ALLOWED_RULE_TYPES:
        return None

    evidence = str(payload.get("evidence", "")).strip()
    if not evidence or _normalize(evidence) not in _normalize(sentence):
        return None

    return rule_type, evidence


class ClassifyCache:
    """規定文 → 判定 のキャッシュ。同じ標準書を再解析しても結果が変わらないようにする。"""

    def __init__(self, path: Path | None):
        self.path = path
        self._data: dict[str, dict] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.path and self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("判定キャッシュを読めませんでした: %s", self.path)
                self._data = {}

    @staticmethod
    def key(kind: str, sentence: str) -> str:
        """種別を含める。同じ文に別の問い (規定判定 / 分類) を投げるため。"""
        raw = f"{PROMPT_VERSION}\n{CLAUDE_MODEL}\n{kind}\n{sentence}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, kind: str, sentence: str) -> dict | None:
        self._load()
        return self._data.get(self.key(kind, sentence))

    def put(self, kind: str, sentence: str, payload: dict) -> None:
        self._load()
        self._data[self.key(kind, sentence)] = payload
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("判定キャッシュを書けませんでした: %s", self.path)


@dataclass
class ClassifyAssist:
    """Claude に規定かどうかを尋ねる。呼び出し回数はここで数える。"""

    cache: ClassifyCache
    #: 呼んだ回数 / キャッシュに当たった回数 / 検証で捨てた回数 / 規定と判定した回数
    stats: dict[str, int] = field(
        default_factory=lambda: {"asked": 0, "cached": 0, "rejected": 0, "accepted": 0}
    )

    def classify(self, sentence: str) -> tuple[str, str] | None:
        """(rule_type, 根拠) を返す。規定でない / 検証に落ちたときは None。"""
        if not is_candidate(sentence):
            return None

        payload = self.cache.get("rule", sentence)
        if payload is not None:
            self.stats["cached"] += 1
        else:
            payload = self._ask(sentence)
            if payload is None:
                return None
            self.cache.put("rule", sentence, payload)

        result = validate(sentence, payload)
        if result is None:
            # 「規定でない」と判定された場合もここに来る。捨てた数だけ数える
            if payload.get("is_rule"):
                self.stats["rejected"] += 1
                logger.info("規定判定を破棄しました (根拠が原文に無い): %s", sentence)
            return None

        self.stats["accepted"] += 1
        return result

    def categorize(self, sentence: str, hint: str | None) -> str | None:
        """分類を1つ選ばせる。選択肢に無い値が返ったら None。

        ルールベースの語彙一致が何にも当たらなかったときだけ呼ぶ。標準書が分類列を
        持っていれば、その値も判断材料として渡す (標準書自身の分類が最優先という
        方針は変えず、語彙表に無い書き方を橋渡しするだけ)。
        """
        if not is_candidate(sentence):
            return None

        # 規定文と分類列の組で覚える。同じ文でも分類列が違えば別の問い
        key_text = sentence + " <<hint>> " + (hint or "")
        payload = self.cache.get("category", key_text)
        if payload is not None:
            self.stats["cached"] += 1
        else:
            payload = self._ask(
                CATEGORY_TEMPLATE.format(sentence=sentence, hint=hint or "(なし)"),
                system=CATEGORY_SYSTEM,
                schema=CATEGORY_SCHEMA,
            )
            if payload is None:
                return None
            self.cache.put("category", key_text, payload)

        category = payload.get("category")
        if category not in CATEGORY_NAMES:
            self.stats["rejected"] += 1
            logger.info("分類の判定を破棄しました (選択肢に無い): %s", category)
            return None
        self.stats["accepted"] += 1
        return category

    def column_roles(self, header: list[str]) -> dict[int, str] | None:
        """ヘッダ行から 列番号 -> 役割 を得る。使えなければ None。

        語彙一致でヘッダを判定できなかった表だけが対象。「強制度」「レベル区分」の
        ように、語彙表に無い見出しを使う標準書を拾うため。

        検証する点は3つ。
          - 役割が選択肢に入っていること
          - 列番号がヘッダの範囲内であること
          - 規定本文の列 (rule) がちょうど1つあること
            (無ければ表の意味を読み違える。複数なら選べない)
        """
        rendered = " | ".join(f"[{i}] {c}" for i, c in enumerate(header))
        payload = self.cache.get("columns", rendered)
        if payload is not None:
            self.stats["cached"] += 1
        else:
            payload = self._ask(
                COLUMNS_TEMPLATE.format(header=rendered),
                system=COLUMNS_SYSTEM,
                schema=COLUMNS_SCHEMA,
            )
            if payload is None:
                return None
            self.cache.put("columns", rendered, payload)

        roles: dict[int, str] = {}
        for entry in payload.get("columns", []):
            index, role = entry.get("index"), entry.get("role")
            if role not in COLUMN_ROLES or not isinstance(index, int):
                continue
            if not 0 <= index < len(header):
                continue
            roles.setdefault(index, role)

        if list(roles.values()).count("rule") != 1:
            self.stats["rejected"] += 1
            logger.info("列の役割判定を破棄しました (規定本文の列が定まらない): %s", rendered)
            return None

        self.stats["accepted"] += 1
        return roles

    def _ask(self, sentence: str, system: str = "", schema: dict | None = None) -> dict | None:
        """Claude へ1回問い合わせる。system / schema を差し替えて別の問いにも使う。"""
        system = system or SYSTEM_PROMPT
        schema = schema or RESPONSE_SCHEMA
        import anthropic

        self.stats["asked"] += 1
        client = anthropic.Anthropic()
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                # 出力自体は短いが、adaptive thinking の分も max_tokens に含まれるので余裕を取る
                max_tokens=16000,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": schema},
                },
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": USER_TEMPLATE.format(sentence=sentence)}],
            )
        except anthropic.AuthenticationError:
            # 鍵が無効なまま黙ってルールベースに戻ると原因が分からないので、はっきり出す
            logger.error("ANTHROPIC_API_KEY が無効です。規定判定はルールベースに戻します。")
            return None
        except anthropic.RateLimitError:
            logger.warning("Claude API がレート制限中です。この行はルールベースで判定します。")
            return None
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            # 補助が使えなくてもルールベースの結果で成立するので、ここでは落とさない
            logger.warning("Claude への判定問い合わせに失敗しました: %s", exc)
            return None

        if response.stop_reason == "refusal":
            logger.warning("Claude が判定を拒否しました: %s", sentence)
            return None

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("判定の応答をJSONとして解釈できませんでした: %s", text[:200])
            return None


def build_assist(enabled: bool, cache_path: Path | None) -> ClassifyAssist | None:
    """設定と資格情報が揃っているときだけ補助を返す。

    APIキーが無い / SDK が入っていない場合は None。呼び出し側はルールベースのまま動く。
    """
    if not enabled:
        return None
    if not claude_available():
        logger.info("ANTHROPIC_API_KEY または anthropic SDK が無いため、規定判定の補助は使いません。")
        return None
    return ClassifyAssist(cache=ClassifyCache(cache_path))


assert set(ALLOWED_RULE_TYPES) <= set(tx.RULE_TYPES), "規範レベルの語彙が taxonomy とずれている"
