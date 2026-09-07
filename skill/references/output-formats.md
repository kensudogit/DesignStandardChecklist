# Output Formats

STEP 14 の成果物。列構成は [`../templates/`](../templates) の CSV と一致させる。

列を並べ替えたり名前を変えたりしない。既にこの表でレビューを回している現場があり、
列がずれると集計マクロや過去の記入結果が使えなくなる。

## 共通ルール

- CSV は **UTF-8 BOM + CRLF**。Excel でそのまま開けるようにするため。
- 出典が取得できなかった箇所は空欄ではなく **`不明`**。空欄だと
  「まだ埋めていない」のか「取得できない」のか区別が付かない（必須原則 9）。
- 備考など、無いことが自然な列は空欄のままにする。すべてを `不明` で埋めない。
- 複数の値を1セルに入れるときは `;` 区切り。

## 1. 標準書一覧

`templates/standard-register-template.csv`

```
Document ID, Document Name, Document Type, Version, Established Date,
Revised Date, Target Phase, Target Deliverable, Notes
```

STEP 1 で識別した内容をそのまま並べる。取れなかった項目は `不明`。

## 2. 規定抽出一覧

`templates/extracted-rules-template.csv`

```
Standard ID, Rule Type, Category, Original Rule, Normalized Requirement,
Source Document, Chapter, Section, Page, Condition, Exception, Ambiguity, Notes
```

チェックリストの手前にある中間成果物。**`Original Rule` には原文をそのまま入れる。**
ここが原文でなくなると、チェック項目の語が標準書に由来することを誰も確認できなくなる。

`Original Rule` と `Normalized Requirement` を並べて出すのは、変換が妥当かを
ここで確認できるようにするため。語が増えていればこの2列を見比べた時点で分かる。

`Category` は `分類/見出しの末尾`（例: `UI/項目定義`）。見出しが無い場合は分類のみ。
チェックリスト側は `Category` と `Sub Category` に分かれるが、この中間成果物では
1列に収めている。

## 3. レビューチェックリスト

`templates/checklist-template.csv` / `templates/checklist-template.md`

```
No, Check ID, Category, Sub Category, Check Point, Severity, Requirement,
Standard ID, Source Document, Chapter, Section, Page, Condition, Exception,
Result, Evidence, Reviewer, Review Date, Comment
```

- `Result` の初期値は `Pending`。取りうる値は `OK` / `NG` / `N/A` / `Pending`。
- `Evidence` / `Reviewer` / `Review Date` / `Comment` は空欄で出す（レビュアーの記入欄）。
- 重複統合された項目の `Standard ID` は統合元も含めて `;` 区切りで並べる。
- Markdown 版はセル内の `|` を `\|` にエスケープする。

`Requirement`（要求事項）と `Check Point`（質問文）を両方持たせているのは、
質問文だけでは「何が満たされていれば OK か」が読み取りにくい場面があるため。

## 4. トレーサビリティ表

`templates/traceability-matrix-template.csv`

```
Check ID, Standard ID, Source Document, Chapter, Section, Page, Trace Status, Notes
```

`Trace Status`:

| 値 | 条件 |
|---|---|
| `Traced` | 章・節・ページ・所在のいずれかが取れている |
| `Source Unknown` | いずれも取れていない |

`Notes` に入れるもの（該当するものを ` / ` で連結）:

- `複数標準由来: STD-DD-004;STD-DB-011`
- `重複統合元: CHK-DD-007`
- `類似候補: CHK-UI-012 (0.91)`
- `出典を特定できないため推測せず不明とした`

ページ番号を推測して埋めない。`Source Unknown` が並ぶこと自体が
「この文書形式ではページが取れない」という報告になる。

## 5. 未変換規定一覧

`templates/unconverted-rules-template.csv`

```
Standard ID, Original Rule, Reason Not Converted, Required Action, Owner, Status
```

`Required Action` の既定:

| 未変換の理由 | Required Action |
|---|---|
| 曖昧表現を含む | 標準書の判定基準を確認し、チェック項目化の可否を判断する |
| それ以外 | 規定文を分割・具体化したうえで再解析する |

`Status` の初期値は `Open`。

この一覧は Coverage が 100% でないときの内訳になる。件数が合わないと
Coverage レポートが信用されないので、必ず対応させる。

## 6. Coverage レポート

`templates/coverage-report-template.md`

```markdown
# Coverage Report

## Summary
- Total target rules:
- Converted rules:
- Unconverted rules:
- Mandatory rules:
- Mandatory converted:
- Prohibited rules:
- Prohibited converted:

## Coverage Formula
Coverage = Converted target rules / Total target rules * 100

## Mandatory Coverage
Target: 100%

## Prohibited Coverage
Target: 100%

## Findings
- Unconverted:
- Ambiguous:
- Missing source references:
- Duplicate candidates:
```

規範レベル別の内訳（total / converted / unconverted / coverage）も併せて出す。

`Findings` には次を書く。**指摘が1件も無いときも1行残す。**
空欄のレポートは「まだ実行していない」ように見える。

```
必須・禁止規定のCoverageは100%です。未変換・曖昧・出典欠落もありません。
```

ページ番号を持たない文書形式（Markdown / Text）の場合は、末尾に注記を足す。

```markdown
## Note
この文書形式ではページ番号を取得できないため、Page 列は「不明」としています。
推測によるページ番号の付与は行いません。
```

## 7. AI推奨事項（要求された場合のみ）

`templates/ai-recommendations-template.csv`

```
Recommendation ID, No, Category, Sub Category, Check Point, Severity,
Requirement, Rationale, Generator, Origin, Adoption, Comment
```

**`Standard ID` / `Chapter` / `Section` / `Page` の列を意図的に持たない。**
持たせると出典があるように見え、標準由来の項目と取り違えられる（必須原則 8）。

- `Origin` は全行に `AI推奨（標準書由来ではない）` を入れる。
  同じフォルダに置かれても取り違えられないようにするため。
- `Generator` は生成方法（観点カタログとの突き合わせか、モデルによる提案か）。
- `Adoption` は採否の記入欄。初期値は空欄。

提案するのは**標準書に規定が無い観点だけ**。標準書に書いてあることを言い換えて
出しても、標準由来の項目と重複するだけで価値が無い。
観点の下敷きは SKILL.md 5章・6章。

件数は 20 件程度を上限にする。多すぎると標準由来の項目が埋もれる。

## 8. 統合レビュー表（複数標準書の横断）

`templates/consolidated-checklist-template.csv`

```
No, Check ID, Category, Sub Category, Check Point, Severity, Requirement,
Standard IDs, Source Documents, Chapters, Sections, Pages,
Condition, Exception, Merged Check IDs, Result, Evidence, Reviewer, Review Date, Comment
```

- `Check ID` は**各文書のものを維持する**。統合表だけの新しいID体系を作らない。
- `Standard IDs` / `Source Documents` / `Chapters` / `Sections` / `Pages` は
  出典ごとの値を `;` 区切りで並べる。1つに丸めない。
- `Source Documents` は重複を除いて並べる（同じ文書から複数の規定が来ることがある）。
- `Severity` は統合した項目の中で**最も重いもの**。

対応するトレーサビリティ表 `templates/cross-traceability-template.csv`:

```
Check ID, Standard ID, Source Document, Chapter, Section, Page, Consolidated No, Role
```

統合チェック1行につき、出典となった標準書ごとに1行を出す。
どの標準書のどの規定から来たかを全て並べるため、**行数はチェック件数より多くなる**。
`Role` は代表（`Primary`）か統合元（`Merged`）かを示す。
