"""変換精度の測定。

gold (eval/gold/) と実装の出力を突き合わせて、STEP 3-7 の精度を数値で出す。
測るのは実装そのもの: パーサ → assign_structure → extract_rules → checks_for_rule と、
本番の analyze_document と同じ関数を同じ順で呼ぶ (DB への書き込みだけ行わない)。

使い方:
    python -m eval.runner                    # 全 gold を評価してレポート表示
    python -m eval.runner --gold 画面設計標準  # 対象を絞る
    python -m eval.runner --details          # 取りこぼし / 誤抽出を1件ずつ表示
    python -m eval.runner --json out.json    # 機械可読な結果を書き出す
    python -m eval.runner --check-baseline   # baseline.json から悪化していたら exit 1
    python -m eval.runner --update-baseline  # 現在値を baseline.json に記録
    python -m eval.runner --llm-candidates   # AI補助に回る規定文を一覧表示 (API不要)
    python -m eval.runner --llm              # AI補助を有効にして測る (APIキーが必要)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import llm_split  # noqa: E402
from app.core.atomizer import AtomicCheck, base_sentence  # noqa: E402
from app.core.extractor import ExtractedRule, extract_rules  # noqa: E402
from app.core.parsers import parse_document  # noqa: E402
from app.core.pipeline import checks_for_rule  # noqa: E402
from app.core.structure import assign_structure  # noqa: E402
from eval.gold import (  # noqa: E402
    GoldCheck,
    GoldRule,
    GoldSet,
    load_gold_sets,
    normalize,
    validate,
)

GOLD_DIR = EVAL_DIR / "gold"
BASELINE_PATH = EVAL_DIR / "baseline.json"
#: --llm で使うキャッシュ。本番 (backend/storage/) とは分けて、評価結果を汚さない。
CACHE_PATH = EVAL_DIR / "llm-split-cache.json"

#: baseline 比較で「悪化」とみなす下げ幅。表記ゆれ程度の揺れで CI を落とさないための余白。
REGRESSION_TOLERANCE = 0.005


@dataclass
class Produced:
    """実装が出した規定1件と、そこから作られた確認事項。"""

    rule: ExtractedRule
    checks: list[AtomicCheck]
    unconverted_reason: str | None


@dataclass
class Score:
    """適合率 / 再現率。tp/fp/fn を持つのは、率だけだと母数が見えないため。"""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class Ratio:
    """正解数 / 母数。母数 0 のときは 1.0 (評価対象なし) とする。"""

    hit: int = 0
    total: int = 0

    @property
    def value(self) -> float:
        return self.hit / self.total if self.total else 1.0

    def add(self, ok: bool) -> None:
        self.total += 1
        self.hit += 1 if ok else 0

    def as_dict(self) -> dict[str, float | int]:
        return {"hit": self.hit, "total": self.total, "value": round(self.value, 4)}


@dataclass
class Finding:
    """レポートに出す個別の不一致。ここが改善作業の入口になる。"""

    kind: str
    detail: str
    expected: str = ""
    actual: str = ""


@dataclass
class DocumentResult:
    name: str
    document: str
    rule: Score = field(default_factory=Score)
    check: Score = field(default_factory=Score)
    rule_type: Ratio = field(default_factory=Ratio)
    category: Ratio = field(default_factory=Ratio)
    condition: Ratio = field(default_factory=Ratio)
    exception: Ratio = field(default_factory=Ratio)
    ambiguity: Ratio = field(default_factory=Ratio)
    convertible: Ratio = field(default_factory=Ratio)
    findings: list[Finding] = field(default_factory=list)
    gold_problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "document": self.document,
            "rule": self.rule.as_dict(),
            "check": self.check.as_dict(),
            "rule_type_accuracy": self.rule_type.as_dict(),
            "category_accuracy": self.category.as_dict(),
            "condition_recall": self.condition.as_dict(),
            "exception_recall": self.exception.as_dict(),
            "ambiguity_accuracy": self.ambiguity.as_dict(),
            "convertible_accuracy": self.convertible.as_dict(),
            "findings": [
                {"kind": f.kind, "detail": f.detail, "expected": f.expected, "actual": f.actual}
                for f in self.findings
            ],
        }


def run_pipeline(document: Path, assist: llm_split.SplitAssist | None = None) -> list[Produced]:
    """analyze_document と同じ手順を DB 無しで実行する。"""
    parsed = parse_document(document.name, document.read_bytes())
    located = assign_structure(parsed.blocks)
    out: list[Produced] = []
    for item in extract_rules(located):
        checks, reason = checks_for_rule(item, assist=assist)
        out.append(Produced(rule=item, checks=checks, unconverted_reason=reason))
    return out


def _haystack(check: AtomicCheck) -> str:
    """gold の Must Include を探す対象。

    確認事項の文言に加えて条件・例外も見る。実装が条件を check_point 側に
    埋め込むか別フィールドに置くかは実装都合なので、どちらでも拾えるようにする。
    """
    parts = [check.check_point, check.condition or "", check.exception or ""]
    return normalize(" ".join(p for p in parts if p))


def _match_checks(
    gold_checks: list[GoldCheck], produced: list[AtomicCheck]
) -> tuple[dict[str, int], list[int]]:
    """gold の確認事項に、実装の出力を1対1で割り当てる。

    候補が複数あるときは最も短いものを採る。余計な語が少ないほど、その gold が
    意図した確認事項そのものである可能性が高いため。決定的に動く。
    """
    hays = [_haystack(c) for c in produced]
    assigned: dict[str, int] = {}
    used: set[int] = set()
    for gold_check in gold_checks:
        candidates = [i for i, hay in enumerate(hays) if i not in used and gold_check.matches(hay)]
        if not candidates:
            continue
        best = min(candidates, key=lambda i: (len(hays[i]), i))
        assigned[gold_check.key] = best
        used.add(best)
    unmatched = [i for i in range(len(produced)) if i not in used]
    return assigned, unmatched


def evaluate(gold: GoldSet, assist: llm_split.SplitAssist | None = None) -> DocumentResult:
    result = DocumentResult(
        name=gold.name, document=str(gold.document.relative_to(REPO_ROOT)).replace("\\", "/")
    )
    result.gold_problems = validate(gold)

    produced = run_pipeline(gold.document, assist=assist)
    by_text: dict[str, Produced] = {}
    for item in produced:
        by_text.setdefault(normalize(item.rule.original_rule), item)

    matched: list[tuple[GoldRule, Produced]] = []
    for gold_rule in gold.rules:
        found = by_text.get(gold_rule.normalized)
        if found is None:
            result.rule.fn += 1
            result.findings.append(
                Finding(kind="規定の取りこぼし", detail=gold_rule.key, expected=gold_rule.original_rule)
            )
            continue
        result.rule.tp += 1
        matched.append((gold_rule, found))

    gold_texts = {r.normalized for r in gold.rules}
    for item in produced:
        if normalize(item.rule.original_rule) not in gold_texts:
            result.rule.fp += 1
            result.findings.append(
                Finding(
                    kind="規定の誤抽出",
                    detail=f"{item.rule.rule_type}/{item.rule.category}",
                    actual=item.rule.original_rule,
                )
            )

    for gold_rule, item in matched:
        _score_attributes(result, gold_rule, item)
        _score_checks(result, gold, gold_rule, item)

    # gold が知らない規定から出た確認事項も過剰出力なので数える
    for item in produced:
        if normalize(item.rule.original_rule) not in gold_texts:
            result.check.fp += len(item.checks)
    return result


def _score_attributes(result: DocumentResult, gold_rule: GoldRule, item: Produced) -> None:
    rule = item.rule

    ok = rule.rule_type in gold_rule.rule_types
    result.rule_type.add(ok)
    if not ok:
        result.findings.append(
            Finding(
                kind="規範レベルの誤り",
                detail=gold_rule.key,
                expected=" | ".join(gold_rule.rule_types),
                actual=rule.rule_type,
            )
        )

    if gold_rule.categories:
        ok = rule.category in gold_rule.categories
        result.category.add(ok)
        if not ok:
            result.findings.append(
                Finding(
                    kind="分類の誤り",
                    detail=gold_rule.key,
                    expected=" | ".join(gold_rule.categories),
                    actual=rule.category,
                )
            )

    for label, expected, actual, ratio in (
        ("条件", gold_rule.condition, rule.condition, result.condition),
        ("例外", gold_rule.exception, rule.exception, result.exception),
    ):
        if expected:
            ok = bool(actual) and normalize(expected) in normalize(actual)
            ratio.add(ok)
            if not ok:
                result.findings.append(
                    Finding(
                        kind=f"{label}の欠落",
                        detail=gold_rule.key,
                        expected=expected,
                        actual=actual or "(なし)",
                    )
                )
        elif actual:
            ratio.add(False)
            result.findings.append(
                Finding(
                    kind=f"{label}の過検出", detail=gold_rule.key, expected="(なし)", actual=actual
                )
            )

    ok = bool(rule.ambiguity) == gold_rule.ambiguity
    result.ambiguity.add(ok)
    if not ok:
        result.findings.append(
            Finding(
                kind="曖昧表現の判定誤り",
                detail=gold_rule.key,
                expected="曖昧" if gold_rule.ambiguity else "曖昧でない",
                actual=rule.ambiguity or "(検出なし)",
            )
        )

    ok = (item.unconverted_reason is None) == gold_rule.convertible
    result.convertible.add(ok)
    if not ok:
        result.findings.append(
            Finding(
                kind="変換可否の誤り",
                detail=gold_rule.key,
                expected="変換できる" if gold_rule.convertible else "未変換が正しい",
                actual=item.unconverted_reason or "変換した",
            )
        )


def _score_checks(
    result: DocumentResult, gold: GoldSet, gold_rule: GoldRule, item: Produced
) -> None:
    gold_checks = gold.checks_of(gold_rule.key)
    assigned, unmatched = _match_checks(gold_checks, item.checks)

    for gold_check in gold_checks:
        if gold_check.key in assigned:
            result.check.tp += 1
        else:
            result.check.fn += 1
            result.findings.append(
                Finding(
                    kind="確認事項の取りこぼし",
                    detail=f"{gold_check.key} (要語: {' + '.join(gold_check.must_include)})",
                    expected=gold_check.expected,
                    actual=" / ".join(c.check_point for c in item.checks) or "(なし)",
                )
            )

    for index in unmatched:
        result.check.fp += 1
        result.findings.append(
            Finding(
                kind="確認事項の過剰出力",
                detail=gold_rule.key,
                actual=item.checks[index].check_point,
            )
        )


@dataclass
class Report:
    documents: list[DocumentResult]

    @property
    def total(self) -> DocumentResult:
        agg = DocumentResult(name="合計", document="")
        for doc in self.documents:
            for attr in ("rule", "check"):
                src, dst = getattr(doc, attr), getattr(agg, attr)
                dst.tp += src.tp
                dst.fp += src.fp
                dst.fn += src.fn
            for attr in (
                "rule_type",
                "category",
                "condition",
                "exception",
                "ambiguity",
                "convertible",
            ):
                src, dst = getattr(doc, attr), getattr(agg, attr)
                dst.hit += src.hit
                dst.total += src.total
        return agg

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total.as_dict(),
            "documents": [doc.as_dict() for doc in self.documents],
        }

    @property
    def gold_problems(self) -> list[str]:
        return [f"{d.name}: {p}" for d in self.documents for p in d.gold_problems]


#: baseline 比較で見る指標。値が下がったら悪化。
TRACKED = (
    ("rule.f1", "規定抽出 F1"),
    ("check.f1", "確認事項 F1"),
    ("rule_type_accuracy.value", "規範レベル正解率"),
    ("category_accuracy.value", "分類正解率"),
    ("condition_recall.value", "条件の保持率"),
    ("exception_recall.value", "例外の保持率"),
    ("ambiguity_accuracy.value", "曖昧表現の正解率"),
    ("convertible_accuracy.value", "変換可否の正解率"),
)


def _dig(data: dict, dotted: str) -> float:
    node: object = data
    for part in dotted.split("."):
        node = node[part]  # type: ignore[index]
    return float(node)  # type: ignore[arg-type]


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def format_report(report: Report, details: bool) -> str:
    lines: list[str] = []
    header = f"{'対象':<16}{'規定 P/R/F1':<26}{'確認事項 P/R/F1':<26}{'規範':>7}{'分類':>7}"
    lines.append(header)
    lines.append("-" * len(header))
    for doc in [*report.documents, report.total]:
        if doc.name == "合計":
            lines.append("-" * len(header))
        rule = f"{_pct(doc.rule.precision)}/{_pct(doc.rule.recall)}/{_pct(doc.rule.f1)}"
        check = f"{_pct(doc.check.precision)}/{_pct(doc.check.recall)}/{_pct(doc.check.f1)}"
        lines.append(
            f"{doc.name:<16}{rule:<26}{check:<26}"
            f"{_pct(doc.rule_type.value):>7}{_pct(doc.category.value):>7}"
        )

    total = report.total
    lines.append("")
    lines.append(
        f"規定 {total.rule.tp}件一致 / 取りこぼし {total.rule.fn} / 誤抽出 {total.rule.fp}"
        f"    確認事項 {total.check.tp}件一致 / 取りこぼし {total.check.fn} /"
        f" 過剰 {total.check.fp}"
    )
    lines.append(
        f"条件の保持 {total.condition.hit}/{total.condition.total}"
        f"    例外の保持 {total.exception.hit}/{total.exception.total}"
        f"    曖昧表現 {total.ambiguity.hit}/{total.ambiguity.total}"
        f"    変換可否 {total.convertible.hit}/{total.convertible.total}"
    )

    if report.gold_problems:
        lines.append("")
        lines.append("【gold 自体の不備】")
        lines.extend(f"  - {p}" for p in report.gold_problems)

    if details:
        for doc in report.documents:
            if not doc.findings:
                continue
            lines.append("")
            lines.append(f"=== {doc.name} の不一致 {len(doc.findings)}件 ===")
            for finding in doc.findings:
                lines.append(f"  [{finding.kind}] {finding.detail}")
                if finding.expected:
                    lines.append(f"      期待: {finding.expected}")
                if finding.actual:
                    lines.append(f"      実際: {finding.actual}")
    return "\n".join(lines)


def compare_baseline(report: Report, baseline: dict) -> list[str]:
    """baseline から下がった指標を文章で返す。空なら悪化なし。"""
    current = report.as_dict()
    regressions: list[str] = []
    base_docs = {d["name"]: d for d in baseline.get("documents", [])}
    cur_docs = {d["name"]: d for d in current["documents"]}  # type: ignore[union-attr]

    for scope, base, cur in [
        ("合計", baseline.get("total"), current["total"]),
        *[(name, base_docs[name], cur_docs.get(name)) for name in sorted(base_docs)],
    ]:
        if base is None:
            continue
        if cur is None:
            regressions.append(f"{scope}: baseline にあった gold が評価されていない")
            continue
        for path, label in TRACKED:
            try:
                before, after = _dig(base, path), _dig(cur, path)
            except (KeyError, TypeError):
                continue
            if after < before - REGRESSION_TOLERANCE:
                regressions.append(
                    f"{scope} / {label}: {_pct(before).strip()} → {_pct(after).strip()}"
                )
    return regressions


def build_report(
    only: list[str] | None = None, assist: llm_split.SplitAssist | None = None
) -> Report:
    gold_sets = load_gold_sets(GOLD_DIR, REPO_ROOT, only=only)
    return Report(documents=[evaluate(gold, assist=assist) for gold in gold_sets])


def llm_candidates() -> list[tuple[str, str]]:
    """AI補助に回る規定文の一覧 (gold名, 原文)。呼び出し件数の見積りに使う。"""
    out: list[tuple[str, str]] = []
    for gold in load_gold_sets(GOLD_DIR, REPO_ROOT):
        for item in run_pipeline(gold.document):
            if item.unconverted_reason is not None or len(item.checks) != 1:
                continue
            sentence = base_sentence(item.rule)
            if llm_split.is_candidate(sentence):
                out.append((gold.name, sentence))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="設計標準→チェックリスト変換の精度を測る")
    parser.add_argument("--gold", action="append", help="評価する gold 名 (複数指定可)")
    parser.add_argument("--details", action="store_true", help="不一致を1件ずつ表示する")
    parser.add_argument("--json", type=Path, help="結果を JSON で書き出す")
    parser.add_argument("--check-baseline", action="store_true", help="悪化していたら exit 1")
    parser.add_argument("--update-baseline", action="store_true", help="現在値を baseline に記録")
    parser.add_argument(
        "--llm", action="store_true", help="AI補助 (Claude) を有効にして測る。APIキーが必要"
    )
    parser.add_argument(
        "--llm-candidates", action="store_true", help="AI補助に回る規定文を一覧表示する (API不要)"
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if args.llm_candidates:
        candidates = llm_candidates()
        for name, sentence in candidates:
            print(f"{name}: {sentence}")
        print(f"\n計 {len(candidates)}件が AI補助の対象になります。")
        return 0

    assist: llm_split.SplitAssist | None = None
    if args.llm:
        assist = llm_split.build_assist(True, CACHE_PATH)
        if assist is None:
            print(
                "AI補助を使えません。anthropic SDK (pip install -r requirements-optional.txt) と\n"
                "ANTHROPIC_API_KEY を用意してください。"
            )
            return 1

    report = build_report(only=args.gold, assist=assist)
    print(format_report(report, details=args.details))
    if assist is not None:
        print(
            f"\nAI補助: 問い合わせ {assist.stats['asked']}件 /"
            f" キャッシュ {assist.stats['cached']}件 /"
            f" 検証で破棄 {assist.stats['rejected']}件"
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON を書き出しました: {args.json}")

    exit_code = 0
    if report.gold_problems:
        exit_code = 1

    if args.update_baseline:
        if args.gold:
            print("\n--update-baseline は全 gold を対象にしてください (--gold と併用不可)")
            return 1
        BASELINE_PATH.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nbaseline を更新しました: {BASELINE_PATH.name}")
        return exit_code

    if args.check_baseline:
        if not BASELINE_PATH.exists():
            print("\nbaseline.json がありません。--update-baseline で作成してください。")
            return 1
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        regressions = compare_baseline(report, baseline)
        if regressions:
            print("\n【baseline からの悪化】")
            for line in regressions:
                print(f"  - {line}")
            return 1
        print("\nbaseline からの悪化はありません。")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
