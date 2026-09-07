# design-standard-checklist-generator

設計標準書からレビュー用チェックリストを作成する Skill。

標準書の規定を「Yes / No / N/A で答えられる質問」へ変換し、重要度・出典・Coverage を
付けた成果物を出す。要約ではなく、**レビューの場でそのまま使える表**を作ることが目的。

## 主な用途

- 画面設計標準 → 画面設計レビュー表
- 詳細設計標準 → 詳細設計レビュー表
- API設計標準 → API設計レビュー表
- DB設計標準 → DB設計レビュー表
- 複数標準書 → 統合レビュー表

## 構成

| | 内容 |
|---|---|
| [`SKILL.md`](SKILL.md) | 必須原則、STEP 1-14 の処理手順、出力ルール |
| [`references/classification.md`](references/classification.md) | 規範レベル・品質観点・重要度の語彙表と判定順序 |
| [`references/conversion-rules.md`](references/conversion-rules.md) | 要求事項化と Atomic Check 分解の具体例、分解してはいけない形 |
| [`references/table-standards.md`](references/table-standards.md) | 表形式の標準書の読み方 |
| [`references/output-formats.md`](references/output-formats.md) | 成果物の列定義 |
| [`templates/`](templates) | CSV / Markdown のテンプレート |
| [`examples/`](examples) | 入力の標準書と、そこから生成した成果物 |

## この Skill が守っていること

- **標準書に無い語をチェック項目に入れない。** 変換は語尾の付け替えだけで行う。
  読みやすさより出典の追跡可能性を優先する。
- **条件と例外を落とさない。** 条件を消すと当てはまらない設計まで NG になる。
- **必須・禁止・推奨・任意を混同しない。** 判定順序を決めてあり、
  禁止表現は表の区分列より優先する。
- **推測で埋めない。** ページ番号・章節が取れなければ「不明」と書く。
- **AI推奨事項を標準由来と分離する。** 別ファイルにし、出典列を持たせない。
- **変換できなかった規定を隠さない。** 未変換規定一覧と Coverage レポートに出す。

## 成果物

1. `standard-register.csv` — 標準書一覧
2. `extracted-rules.csv` — 規定抽出一覧
3. `design-review-checklist.csv` / `.md` — レビューチェックリスト
4. `traceability-matrix.csv` — トレーサビリティ表
5. `unconverted-rules.csv` — 未変換規定一覧
6. `coverage-report.md` — Coverage レポート
7. `ai-recommendations.csv` — AI推奨事項（要求された場合のみ）

複数標準書を横断する場合は `consolidated-checklist.csv` と
`cross-traceability.csv` を追加する。

## 利用例

> この画面設計標準PDFから、実際の設計レビューで利用できるチェックリストを作成してください。
> 各チェック項目に標準書の章・節・ページ・規定IDを付け、必須・禁止規定のCoverageを
> 100%確認してください。

> 画面設計標準と詳細設計標準を横断してレビュー表を作ってください。
> 同じ内容の項目は1行にまとめ、どの標準書のどの規定から来たかを全部残してください。

## 実装との関係

このリポジトリの `backend/app/core/` は、この Skill の手順をそのまま実装したもの。
コード側のコメントは `SKILL.md STEP 7`、`必須原則 5/6`、`conversion-rules.md 3` の形で
この Skill を参照している。**手順の番号を変えると、コードのコメントが指す先が壊れる。**

`examples/` の CSV はその実装で生成しているので、Skill の記述と実装の出力が
一致していることを実際に確認できる。

## フォルダ名

親フォルダ名と `SKILL.md` の `name` は一致させている。

`design-standard-checklist-generator`
