"""評価用の正解データ (gold) の読み込み。

gold は「標準書1本につき CSV 2枚」で持つ。CSV にしているのは、正解を作り・直すのが
レビュー担当者 (Excel を使う人) だからで、プログラムの都合ではない。

- <名前>.rules.csv  … その標準書から抽出されるべき規定の一覧
- <名前>.checks.csv … 各規定から作られるべき確認事項の一覧

どちらの CSV も「網羅」であることが前提。rules.csv に無い規定を実装が抽出したら
誤抽出 (false positive) として数える。したがって「規定ではないので拾ってはいけない文」は
gold に書かない (書かないこと自体が正解の表明になる)。
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

#: 複数の正解を許すセルの区切り (Rule Type / Category)
ALT_SEP = "|"
#: 語の並びを表すセルの区切り (Must Include / Must Not Include)
TERM_SEP = ";"


def normalize(text: str | None) -> str:
    """比較用の正規化。全角英数の揺れと文末の句点だけを吸収する。

    表記そのものを書き換える正規化 (助詞の削除など) はしない。gold と実装の
    どちらかが間違っているのを正規化で隠してしまうため。
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).strip()
    s = " ".join(s.split())
    return s.rstrip("。．.")


def _cell(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _alts(row: dict[str, str], key: str) -> list[str]:
    raw = _cell(row, key)
    return [v.strip() for v in raw.split(ALT_SEP) if v.strip()] if raw else []


def _terms(row: dict[str, str], key: str) -> list[str]:
    raw = _cell(row, key)
    return [normalize(v) for v in raw.split(TERM_SEP) if v.strip()] if raw else []


def _flag(row: dict[str, str], key: str, default: bool) -> bool:
    raw = _cell(row, key).lower()
    if raw in ("yes", "y", "true", "1"):
        return True
    if raw in ("no", "n", "false", "0"):
        return False
    return default


@dataclass
class GoldRule:
    """抽出されるべき規定1件。"""

    key: str
    #: 標準書中の原文。これが実装の original_rule と一致するかで対応付ける。
    original_rule: str
    #: 許容する規範レベル。複数書いた場合はどれでも正解 (判断が割れる規定用)。
    rule_types: list[str] = field(default_factory=list)
    #: 許容する分類。空なら分類は評価しない。
    categories: list[str] = field(default_factory=list)
    #: 条件として保持されるべき語。空なら「条件は無いのが正しい」。
    condition: str = ""
    #: 例外として保持されるべき語。空なら「例外は無いのが正しい」。
    exception: str = ""
    #: 曖昧表現として検出されるべきか。
    ambiguity: bool = False
    #: チェック項目に変換できるべきか。no なら未変換と判定されるのが正解。
    convertible: bool = True
    note: str = ""

    @property
    def normalized(self) -> str:
        return normalize(self.original_rule)


@dataclass
class GoldCheck:
    """作られるべき確認事項1件。

    文言そのものは実装の言い回しに依存するので一致条件にしない。代わりに
    「この語がすべて入っていること」で判定する。言い回しの改善で評価が壊れず、
    かつ主語や条件の欠落は検出できる粒度を狙っている。
    """

    key: str
    rule_key: str
    #: 人が読むための期待文言。判定には使わない。
    expected: str
    #: すべて含まれていなければならない語。
    must_include: list[str] = field(default_factory=list)
    #: 1つでも含まれていたら不一致とする語。
    must_not_include: list[str] = field(default_factory=list)
    note: str = ""

    def matches(self, haystack: str) -> bool:
        if not self.must_include:
            return False
        if any(term in haystack for term in self.must_not_include):
            return False
        return all(term in haystack for term in self.must_include)


@dataclass
class GoldSet:
    name: str
    #: 評価対象の標準書 (リポジトリルートからの相対パス)
    document: Path
    rules: list[GoldRule]
    checks: list[GoldCheck]
    note: str = ""

    def checks_of(self, rule_key: str) -> list[GoldCheck]:
        return [c for c in self.checks if c.rule_key == rule_key]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fp:
        return [row for row in csv.DictReader(fp) if any((v or "").strip() for v in row.values())]


def load_rules(path: Path) -> list[GoldRule]:
    out: list[GoldRule] = []
    for row in _read_csv(path):
        out.append(
            GoldRule(
                key=_cell(row, "Rule Key"),
                original_rule=_cell(row, "Original Rule"),
                rule_types=_alts(row, "Rule Type"),
                categories=_alts(row, "Category"),
                condition=_cell(row, "Condition"),
                exception=_cell(row, "Exception"),
                ambiguity=_flag(row, "Ambiguity", False),
                convertible=_flag(row, "Convertible", True),
                note=_cell(row, "Note"),
            )
        )
    return out


def load_checks(path: Path) -> list[GoldCheck]:
    out: list[GoldCheck] = []
    for row in _read_csv(path):
        out.append(
            GoldCheck(
                key=_cell(row, "Check Key"),
                rule_key=_cell(row, "Rule Key"),
                expected=_cell(row, "Expected"),
                must_include=_terms(row, "Must Include"),
                must_not_include=_terms(row, "Must Not Include"),
                note=_cell(row, "Note"),
            )
        )
    return out


def load_gold_sets(gold_dir: Path, repo_root: Path, only: list[str] | None = None) -> list[GoldSet]:
    """manifest.csv に並んだ gold を読み込む。"""
    manifest = gold_dir / "manifest.csv"
    if not manifest.exists():
        raise FileNotFoundError(f"manifest が見つかりません: {manifest}")

    sets: list[GoldSet] = []
    for row in _read_csv(manifest):
        name = _cell(row, "Gold Name")
        if only and name not in only:
            continue
        document = (repo_root / _cell(row, "Document Path")).resolve()
        rules_csv = gold_dir / f"{name}.rules.csv"
        checks_csv = gold_dir / f"{name}.checks.csv"
        for required in (document, rules_csv, checks_csv):
            if not required.exists():
                raise FileNotFoundError(f"{name}: {required} が見つかりません")
        sets.append(
            GoldSet(
                name=name,
                document=document,
                rules=load_rules(rules_csv),
                checks=load_checks(checks_csv),
                note=_cell(row, "Note"),
            )
        )

    if only:
        missing = sorted(set(only) - {s.name for s in sets})
        if missing:
            raise KeyError(f"manifest に無い gold です: {', '.join(missing)}")
    return sets


def validate(gold: GoldSet) -> list[str]:
    """gold 自体の不備を返す。正解データが壊れたまま測るのを防ぐ。"""
    problems: list[str] = []
    rule_keys = [r.key for r in gold.rules]
    seen: set[str] = set()
    for key in rule_keys:
        if not key:
            problems.append("Rule Key が空の行がある")
        elif key in seen:
            problems.append(f"Rule Key が重複している: {key}")
        seen.add(key)

    normalized: dict[str, str] = {}
    for rule in gold.rules:
        if not rule.original_rule:
            problems.append(f"{rule.key}: Original Rule が空")
        if not rule.rule_types:
            problems.append(f"{rule.key}: Rule Type が空")
        if rule.normalized in normalized:
            problems.append(f"{rule.key}: 原文が {normalized[rule.normalized]} と重複している")
        normalized[rule.normalized] = rule.key

    check_keys: set[str] = set()
    for check in gold.checks:
        if check.key in check_keys:
            problems.append(f"Check Key が重複している: {check.key}")
        check_keys.add(check.key)
        if check.rule_key not in seen:
            problems.append(f"{check.key}: 存在しない Rule Key を参照している ({check.rule_key})")
        if not check.must_include:
            problems.append(f"{check.key}: Must Include が空 (必ず不一致になる)")

    for rule in gold.rules:
        has = bool(gold.checks_of(rule.key))
        if rule.convertible and not has:
            problems.append(f"{rule.key}: 変換されるべきなのに checks.csv に行が無い")
        if not rule.convertible and has:
            problems.append(f"{rule.key}: 未変換が正解なのに checks.csv に行がある")
    return problems
