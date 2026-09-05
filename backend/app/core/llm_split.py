"""STEP 7 補助: 並列表現の分解だけを Claude に手伝わせる（要求された場合のみ）。

ルールベースの atomizer が分解を諦めた規定だけが対象。日本語の並列は
「桁数および範囲の入力チェック」のように後続の名詞を共有することがあり、
どこで切ってよいかは表層の文字列だけでは決まらない。そこだけを任せる。

**Claude に新しい文は書かせない。** 原文のどこで切るか / どこが共有されるかだけを
答えさせ、確認事項はこちら側で原文の部分文字列を連結して組み立てる。返ってきた
区切りが原文を過不足なく覆っているかを1文字単位で検証し、合わなければその提案を
捨ててルールベースの結果を使う。標準書に無い語が混ざる経路を残さないため
（必須原則 1「標準書に記載されていない規定を追加しない」/ 3「曖昧な規定を勝手に断定しない」）。

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

from app.core import atomizer
from app.core.extractor import ExtractedRule

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-5"

#: プロンプトを変えたら上げる。キャッシュのキーに含める。
PROMPT_VERSION = "1"

#: チェック項目に付ける来歴。標準由来であることは変わらないが、分解の判断が
#: ルールベースではないことを読み手に分かるようにする。
ASSIST_NOTE = "AI補助: 並列表現の区切りをClaudeが判定（文言は原文の語のみ）"

#: 列挙要素の間に現れてよい語。これ以外が挟まっていたら提案を捨てる。
CONNECTORS = ("および", "及び", "ならびに", "並びに", "、", "，", ",", "・", "／", "/", "と")

#: 分解を検討する対象。ここに当たらない規定は Claude に投げない（費用と待ち時間の節約）。
#: 読点はほとんどの文に現れて足切りにならないので、並列の接続詞だけを見る。
#: 「と」は「として」「ごとに」等の一部でもあるため、atomizer と同じ条件で除外する。
COORDINATOR_RE = re.compile(r"および|及び|ならびに|並びに|(?<![ごこ])と(?![しすいものは同])")

MIN_SENTENCE_LEN = 12
MAX_SENTENCE_LEN = 200
MAX_ITEMS = 8
MAX_ITEM_LEN = 40


@dataclass(frozen=True)
class SplitPlan:
    """原文をどこで切るかだけを表す。すべて原文の部分文字列。"""

    prefix: str
    items: tuple[str, ...]
    suffix: str

    def render(self) -> list[str]:
        return [f"{self.prefix}{item}{self.suffix}" for item in self.items]


def is_candidate(sentence: str) -> bool:
    """Claude に相談する価値がある規定文か。"""
    if not (MIN_SENTENCE_LEN <= len(sentence) <= MAX_SENTENCE_LEN):
        return False
    # 選択 (または) や例示 (等) は分解してはいけないと既に分かっている
    if any(marker in sentence for marker in atomizer.NO_SPLIT_MARKERS):
        return False
    return COORDINATOR_RE.search(sentence) is not None


def validate(sentence: str, plan: SplitPlan) -> bool:
    """提案が原文を過不足なく覆っているか検証する。

    sentence == prefix + item1 + 接続語 + item2 + ... + itemN + suffix
    を1文字単位で確かめる。ここを通ったものは、原文から接続語を取り除いて
    共有部分を複製しただけの文字列であることが保証される。
    """
    if not (2 <= len(plan.items) <= MAX_ITEMS):
        return False
    if any(not item or len(item) > MAX_ITEM_LEN for item in plan.items):
        return False
    if len(set(plan.items)) != len(plan.items):
        return False

    rest = sentence
    if not rest.startswith(plan.prefix):
        return False
    rest = rest[len(plan.prefix) :]

    for index, item in enumerate(plan.items):
        if not rest.startswith(item):
            return False
        rest = rest[len(item) :]
        if index == len(plan.items) - 1:
            break
        for connector in CONNECTORS:
            if rest.startswith(connector):
                rest = rest[len(connector) :]
                break
        else:
            return False

    if rest != plan.suffix:
        return False

    rendered = plan.render()
    return len(set(rendered)) == len(rendered)


SYSTEM_PROMPT = """\
あなたは日本語の設計標準書を、レビュー用チェックリストに変換する作業を補助します。

与えられた規定文1件について、「独立に確認できる複数の要求が1文にまとめられているか」
を判定し、まとめられている場合は**原文のどこで切るか**だけを答えてください。

## 絶対の制約

- 新しい語を書かないでください。prefix / items / suffix はすべて**原文の部分文字列**です。
- 原文は必ず次の形に分解できなければなりません。
  原文 = prefix + items[0] + 接続語 + items[1] + 接続語 + ... + items[N-1] + suffix
  接続語として認められるのは「および」「及び」「ならびに」「並びに」「、」「・」「/」「と」だけです。
- prefix と suffix は空でもかまいません。items は2件以上必要です。
- 迷ったら split を false にしてください。誤って分けるより、分けないほうが害が小さい。

## 分けるべき場合

それぞれが**別々に欠落しうる**要求であるとき。分けた結果が、単独で読んで
「〜されているか？」と判定できる文になること。

## 分けてはいけない場合

- 選択肢の列挙（「AまたはBのいずれかとする」）
- 例示（「A、B等を記載する」）
- 2つで1つの動作になるもの（「AとBを区別する」「AとBを対応付ける」「AとBを統一する」）
- 分けると意味が変わるもの

## 例

原文: 数値項目には桁数および範囲の入力チェックを定義すること
→ split: true, prefix: "数値項目には", items: ["桁数", "範囲"], suffix: "の入力チェックを定義すること"
（「入力チェック」は両方が共有する後続の名詞。prefix と suffix に回す）

原文: 処理の開始と終了をログに出力すること
→ split: true, prefix: "処理の", items: ["開始", "終了"], suffix: "をログに出力すること"

原文: 業務エラーとシステムエラーを区別して設計すること
→ split: false（「区別する」は2つが揃って初めて成立する1つの要求）

原文: 排他制御方式は楽観ロックまたは悲観ロックのいずれかとする
→ split: false（選択肢の列挙）
"""

USER_TEMPLATE = "規定文: {sentence}"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "split": {"type": "boolean", "description": "分けるべきなら true"},
        "prefix": {"type": "string", "description": "全要素が共有する前半。原文の部分文字列"},
        "items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "分けた要素。それぞれ原文の部分文字列",
        },
        "suffix": {"type": "string", "description": "全要素が共有する後半。原文の部分文字列"},
        "reason": {"type": "string", "description": "そう判断した理由を1文で"},
    },
    "required": ["split", "prefix", "items", "suffix", "reason"],
    "additionalProperties": False,
}


def claude_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class SplitCache:
    """規定文 → 提案 のキャッシュ。同じ標準書を再解析しても結果が変わらないようにする。"""

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
                logger.warning("分解キャッシュを読めませんでした: %s", self.path)
                self._data = {}

    @staticmethod
    def key(sentence: str) -> str:
        raw = f"{PROMPT_VERSION}\n{CLAUDE_MODEL}\n{sentence}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, sentence: str) -> dict | None:
        self._load()
        return self._data.get(self.key(sentence))

    def put(self, sentence: str, payload: dict) -> None:
        self._load()
        self._data[self.key(sentence)] = payload
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("分解キャッシュを書けませんでした: %s", self.path)


@dataclass
class SplitAssist:
    """Claude に分解の可否を尋ねる。呼び出し回数はここで数える。"""

    cache: SplitCache
    #: 呼んだ回数 / キャッシュに当たった回数 / 検証で捨てた回数
    stats: dict[str, int] = field(default_factory=lambda: {"asked": 0, "cached": 0, "rejected": 0})

    def plan_for(self, sentence: str) -> SplitPlan | None:
        if not is_candidate(sentence):
            return None

        payload = self.cache.get(sentence)
        if payload is not None:
            self.stats["cached"] += 1
        else:
            payload = self._ask(sentence)
            if payload is None:
                return None
            self.cache.put(sentence, payload)

        if not payload.get("split"):
            return None
        plan = SplitPlan(
            prefix=str(payload.get("prefix", "")),
            items=tuple(str(i) for i in payload.get("items", [])),
            suffix=str(payload.get("suffix", "")),
        )
        if not validate(sentence, plan):
            # 原文と1文字でも合わない提案は使わない
            self.stats["rejected"] += 1
            logger.info("分解の提案を破棄しました (原文と一致しない): %s", sentence)
            return None
        return plan

    def _ask(self, sentence: str) -> dict | None:
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
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
                },
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": USER_TEMPLATE.format(sentence=sentence)}],
            )
        except anthropic.AuthenticationError:
            # 鍵が無効なまま黙ってルールベースに戻ると原因が分からないので、はっきり出す
            logger.error("ANTHROPIC_API_KEY が無効です。分解補助はルールベースに戻します。")
            return None
        except anthropic.RateLimitError:
            logger.warning("Claude API がレート制限中です。この規定はルールベースで分解します。")
            return None
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            # 補助が使えなくてもルールベースの結果で成立するので、ここでは落とさない
            logger.warning("Claude への分解問い合わせに失敗しました: %s", exc)
            return None

        if response.stop_reason == "refusal":
            logger.warning("Claude が分解の判定を拒否しました: %s", sentence)
            return None

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("分解の応答をJSONとして解釈できませんでした: %s", text[:200])
            return None


def build_assist(enabled: bool, cache_path: Path | None) -> SplitAssist | None:
    """設定と資格情報が揃っているときだけ補助を返す。

    APIキーが無い / SDK が入っていない場合は None。呼び出し側はルールベースのまま動く。
    """
    if not enabled:
        return None
    if not claude_available():
        logger.info("ANTHROPIC_API_KEY または anthropic SDK が無いため、分解補助は使いません。")
        return None
    return SplitAssist(cache=SplitCache(cache_path))


def assisted_checks(
    rule: ExtractedRule, assist: SplitAssist, base: str
) -> list[atomizer.AtomicCheck] | None:
    """補助の提案が使えるなら、その区切りで Atomic Check を作り直す。"""
    plan = assist.plan_for(base)
    if plan is None:
        return None
    fragments = [(fragment, rule.condition) for fragment in plan.render()]
    return atomizer.build_checks(rule, fragments, extra_note=ASSIST_NOTE)
