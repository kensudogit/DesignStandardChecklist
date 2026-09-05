# 設計標準チェックリスト生成 (Design Standard Checklist Generator)

`design-standard-checklist-generator` Skill を、実際に動作するアプリケーションとして実装したものです。

設計標準書（画面設計標準・詳細設計標準・DB設計標準・API設計標準など）をアップロードすると、
**規定を抽出し、確認可能な質問（Atomic Check）へ変換し、重要度・出典・Coverage を付けた
レビュー用チェックリスト**を生成します。生成後はブラウザ上でレビュー結果（OK / NG / N/A）を
記入し、CSV / Markdown で出力できます。

```
標準書
 → 文書構造解析 → 規定候補抽出 → 規定ID付与 → 要求事項化 → Atomic Check分解
 → チェックID付与 → 重要度付与 → 重複整理 → トレーサビリティ → Coverage確認
 → チェックリスト出力
```

複数の標準書を横断した1枚の統合チェックリストも作れます。また、標準書に規定が無い観点を
「AI推奨事項」として（要求された場合のみ）提案できます。AI推奨事項は標準由来の成果物とは
完全に分離されています。

## 構成

| レイヤ | 技術 | 場所 |
|---|---|---|
| バックエンド | Python 3.12 / FastAPI / SQLAlchemy / SQLite | [`backend/`](backend) |
| フロントエンド | Next.js (App Router) / React / TypeScript | [`frontend/`](frontend) |
| 元Skill | SKILL.md・テンプレート・変換ルール | [`skill/`](skill) |
| サンプル標準書 | 12の文書種別を一通り揃えた標準書サンプル（Markdown / Word / Excel） | [`samples/`](samples) |
| 変換精度の評価 | 正解データ (gold) と評価スクリプト | [`backend/eval/`](backend/eval) |

抽出エンジンは **既定で決定的（ルールベース）** です。LLM に依存しないため、同じ標準書からは
常に同じチェックリストが生成され、すべてのチェック項目が標準書の原文に紐づきます。

Claude API は2か所で**任意に**使えます。どちらも既定は無効で、APIキーが無くても全機能が動きます。

| 用途 | 既定 | 出力への影響 |
|---|---|---|
| AI推奨事項の生成 | 無効 | 専用の成果物。チェックリストには混ざりません |
| 並列表現の分解補助（STEP 7） | 無効 | Claude が答えるのは「原文のどこで切るか」だけ。文言は原文の語のみ |

後者は「桁数および範囲の入力チェック」のように、日本語の係り受けを読まないと切れない並列に
限って使います。返ってきた区切りが原文と1文字でも合わなければ捨ててルールベースの結果を使うため、
標準書に無い語がチェック項目に入る経路はありません（必須原則 1/3）。

## 起動方法

**Docker は不要です。** Python と Node.js があれば動きます。
データベースは SQLite を自動生成するため、事前準備はありません。

### 必要なもの

| | バージョン | 確認 | 入っていない場合 |
|---|---|---|---|
| Python | 3.12 以上 | `python --version` | [python.org](https://www.python.org/downloads/) / `winget install --id Python.Python.3.12 -e` |
| Node.js | 20 以上 | `node --version` | [nodejs.org](https://nodejs.org/) / `winget install --id OpenJS.NodeJS.LTS -e` |

### いちばん簡単な方法

Windows（PowerShell）:

```powershell
.\start.ps1
```

macOS / Linux:

```bash
./start.sh
```

初回は仮想環境の作成と依存関係のインストールを自動で行うため数分かかります。
2回目以降は数秒で起動します。起動後、ブラウザが自動で開きます。

- アプリ: http://localhost:3000
- API ドキュメント: http://localhost:8000/docs

**ポートが使用中の場合は空きポートを自動で探します**（例: 3000 が塞がっていれば 3001）。
実際に使われるポートは起動時のメッセージに表示されます。

停止するには、起動したウィンドウで `Ctrl+C` を押すか:

```powershell
.\stop.ps1
```

ログは `logs/` に出力されます。起動に失敗したときはここを確認してください。

> **Windows で「このシステムではスクリプトの実行が無効になっている」と出る場合**
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\start.ps1
> ```
>
> または一度だけ `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` を実行してください。

### 手動で起動する

スクリプトを使わない場合は、ターミナルを2つ開いてください。

ターミナル1（バックエンド）:

```bash
cd backend && python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
```

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

ターミナル2（フロントエンド）:

```bash
cd frontend && npm install
```

```bash
cd frontend && npm run dev
```

macOS / Linux では `.venv/Scripts/python.exe` を `.venv/bin/python` に読み替えてください。
バックエンドのポートを変える場合は `frontend/.env.local` の `NEXT_PUBLIC_API_BASE` も合わせて変更します。

### 使い方を確認する

画面右上の **「利用手順」** を押すと、登録から成果物出力までの詳細な手順、統合レビュー表・
AI推奨事項の使い方、この生成器が守っている原則、よくある困りごとをモーダルで確認できます。

### 試す

`samples/` に、文書種別を一通り揃えた標準書サンプルがあります。どれをアップロードしても
必須規定・禁止規定の Coverage は 100% になります。

| サンプル | 種別 | 形式 | 規定 | チェック項目 |
|---|---|---|---|---|
| `画面設計標準.md` | 画面 | Markdown | 32 | 42 |
| `詳細設計標準.md` | 詳細設計 | Markdown | 21 | 27 |
| `基本設計標準.md` | 基本設計 | Markdown | 27 | 39 |
| `DB設計標準.md` | DB | Markdown | 19 | 27 |
| `API設計標準.xlsx` | API | Excel（表形式） | 16 | 24 |
| `外部IF設計標準.md` | 外部IF | Markdown | 27 | 41 |
| `帳票設計標準.docx` | 帳票 | Word | 25 | 36 |
| `バッチ設計標準.md` | バッチ | Markdown | 30 | 36 |
| `セキュリティ設計標準.md` | セキュリティ | Markdown | 31 | 31 |
| `コーディング標準.md` | コーディング | Markdown | 27 | 32 |
| `テスト設計標準.md` | テスト | Markdown | 29 | 41 |

`API設計標準.xlsx` は表形式の標準書のサンプルです（実務でよくある
「No / 章 / 節 / 分類 / 規定内容 / 区分 / 重要度 / 備考」の列構成）。`帳票設計標準.docx` は
Word 形式のサンプルで、見出しスタイルから章・節を取ります。

画面設計標準・詳細設計標準・DB設計標準の3本を登録したうえで「統合レビュー表」から横断
チェックリストを作ると、標準書をまたいで完全に重複する3件が統合され、93件になります。

### 任意: 追加機能を使う場合

```bash
cd backend && .venv/Scripts/python.exe -m pip install -r requirements-optional.txt
```

- PostgreSQL を使う（`psycopg`）
- Claude API を使う（`anthropic`）

どちらも使わなければインストール不要です。AI推奨事項の「観点カタログ」方式は
追加インストールなしで動きます。

Claude API を使う場合は `ANTHROPIC_API_KEY` を設定してください。並列表現の分解補助
（STEP 7）を有効にするには、さらに次を設定します。

```
DSC_LLM_SPLIT_ENABLED=true
```

有効にすると、ルールベースが1件にしか分解できなかった規定のうち、並列の接続詞を含むものだけを
Claude に相談します（標準書1本あたり数件）。Claude が答えるのは**原文のどこで切るか**だけで、
チェック項目はこちら側で原文の部分文字列を連結して組み立てます。区切りが原文を覆えていなければ
その提案は捨て、ルールベースの結果を使います。応答は規定文をキーにキャッシュするため、
同じ標準書を再解析してもチェック項目がずれません。

補助で分解されたチェック項目には、その旨が備考に付きます。

### 任意: Docker で起動する

Docker が入っていて、PostgreSQL 込みで動かしたい場合のみ。

```bash
docker compose up --build
```

> **コードを変更したら必ず `--build` を付けてください。**
> フロントエンドは JavaScript をイメージのビルド時に焼き込むため、`--build` なしの
> `docker compose up` では古い画面のまま起動します。画面に変更が反映されないときは、
> まずこれを疑ってください。
>
> ```bash
> docker compose up -d --build
> ```

`.env.example` を `.env` にコピーすると `FRONTEND_PORT` / `BACKEND_PORT` を変更できます
（`BACKEND_PORT` を変えたときは `NEXT_PUBLIC_API_BASE` も合わせて変え、frontend の再ビルドが
必要です。`NEXT_PUBLIC_*` はビルド時にJSへ埋め込まれるためです）。

`use docker --context=desktop-linux buildx` というエラーが出る場合は、
`COMPOSE_BAKE=false` を設定してから実行してください。

## Skill の原則をどう実装しているか

SKILL.md の「必須原則」「禁止事項」は、そのままコードとテストになっています。

| 原則 | 実装 | テスト |
|---|---|---|
| 標準書にない規定を追加しない | 抽出は原文の文字列マッチのみ。`normalize_requirement()` は語尾変換しか行わない | `test_normalize_requirement_does_not_add_vocabulary` |
| 出典を付与する | 章・節・ページを本文の表記からのみ取得し、チェック項目まで引き継ぐ | `test_pdf_sections_and_pages_reach_the_rule` |
| ページ番号を推測しない | PDF は pypdf の実ページ番号のみ。Word/Markdown は `None` → 出力は「不明」 | `test_markdown_has_no_page_numbers` / `test_pdf_blocks_carry_real_page_numbers` |
| 曖昧な規定を断定しない | 「適切な」「必要に応じて」等を検出し「確認要」として注記。命名規則を勝手に作らない | `test_ambiguity_is_flagged_not_invented` |
| 1チェック=1確認事項 | 列挙と並列節を分解 | `test_atomic_split_of_enumeration` |
| 条件付き規定は条件を保持 | 条件句を切り出してチェック文へ再挿入。並列節では条件を無関係な節へ広げない | `test_condition_is_preserved` / `test_parallel_clause_split_keeps_condition_local` |
| 例外規定を欠落させない | 例外句を属性として保持し、独立したチェック項目も生成。文をまたぐ「ただし」も拾う | `test_exception_is_preserved_across_sentences` |
| 必須・禁止・推奨・任意を混同しない | 規範レベルを語尾で判定。任意表現が明示された場合は汎用的な「とする」より優先 | `test_classify_rule_type` / `test_mandatory_and_prohibited_are_not_confused` |
| AI推奨事項を分離 | AI推奨事項は専用テーブル・専用API・専用成果物。チェックリスト／トレーサビリティ／Coverage のどの問い合わせにも構造的に混入しない | `test_recommendations_do_not_leak_into_standard_artifacts` |
| 出典を捏造しない | AI推奨事項のCSVに Standard ID / Chapter / Section / Page 列を持たせない | `test_recommendations_have_no_fabricated_sources` |
| Yes/No/N/A で判定可能な粒度 | すべてのチェック項目を「〜か？」の疑問文に変換 | `test_every_check_point_is_a_question` |
| AI補助でも語を足さない | Claude には原文の部分文字列しか返させず、原文を覆えているか1文字単位で検証。合わなければ捨ててルールベースに戻す | `test_invalid_suggestion_falls_back_to_the_rule_based_result` |

## 機能

### 入力形式

PDF（テキスト埋め込み）・Word (.docx)・Excel (.xlsx)・Markdown・テキスト・CSV。
`.doc` / `.xls` は変換を促すエラーを返します。画像PDFはOCR済みPDFを使うよう案内します。
テキストは UTF-8 / CP932 / EUC-JP を自動判別します。

**表形式（Excel）の標準書**は列の役割を判定します。「規定内容」列だけを規定文として扱い、
「章」「節」「分類」「区分」「重要度」「備考」の各列は標準書自身の記載として取り込みます
（推測ではないため、Coverage や重要度の根拠として使えます）。

- 区分列（必須 / 禁止 / 推奨 / 任意 / 条件付き必須）→ 規範レベル
- 重要度列（重大 / 高 / 中 / 低）→ Severity。キーワード推定より優先されます（STEP 10）
- ただし**本文が明示的な禁止表現なら、区分列が「必須」でも禁止として扱います**（必須原則 7）
- 「規定内容」に相当する列を判定できない表は、従来どおり行を連結して扱います

### 生成される成果物（STEP 14）

画面右上からダウンロードできます（ZIP で一括取得も可能）。CSV は Excel で開けるよう BOM 付き。

**標準書ごと（既定）**

1. `standard-register.csv` — 標準書一覧
2. `extracted-rules.csv` — 規定抽出一覧
3. `design-review-checklist.csv` — レビューチェックリスト
4. `design-review-checklist.md` — 同上（Markdown）
5. `traceability-matrix.csv` — トレーサビリティ表
6. `unconverted-rules.csv` — 未変換規定一覧
7. `coverage-report.md` — Coverage レポート

列構成は `skill/templates/*.csv` と一致しています。

**要求された場合のみ**

8. `ai-recommendations.csv` / `.md` — AI推奨事項（標準書由来ではない）

**統合レビュー表**

9. `consolidated-checklist.csv` / `.md` — 横断チェックリスト
10. `cross-traceability-matrix.csv` — 横断トレーサビリティ表
11. `cross-coverage-report.md` — 標準書別Coverageと重複削減の内訳

### ID体系（STEP 4 / 8）

文書種別ごとにプレフィックスを付けます（画面=UI、DB=DB、API=API、詳細設計=DD…）。

- 規定ID: `STD-UI-001`
- チェックID: `CHK-UI-001`

1つの規定から複数のチェック項目が生成されます（`STD-UI-001` → `CHK-UI-001`〜`CHK-UI-004`）。

### 重要度（STEP 10）

標準書に重要度の明示があればそれを最優先し、無ければ規範レベルと観点キーワードから決めます。
判定根拠は重要度バッジの `title` に表示されます。

- Critical: 法令 / 情報漏洩 / 認証・認可 / データ破壊
- High: 必須規定・禁止規定 / 機能障害 / 不整合 / 例外処理
- Medium: 品質 / 保守性 / 統一性
- Low: 推奨 / 任意

### 重複整理（STEP 11）

完全重複のみ自動統合し、統合元の規定IDを出典として保持します（複数標準を根拠とするケース）。
類似項目は自動削除せず「重複候補」として報告します。同一規定を分解した兄弟チェックは、
定義上別の確認事項なので重複候補に含めません。

### Coverage（STEP 13）

```
Coverage = チェック項目化済み対象規定数 / チェック対象規定総数 × 100
```

必須・禁止・条件付き必須は 100% を目標とし、未達なら Findings に警告が出ます。
未変換規定・曖昧規定・出典欠落・重複候補も併せて表示します。

### 横断チェックリスト（複数標準書）

「統合レビュー表」で複数の標準書を選ぶと、1枚の横断チェックリストを生成します
（SKILL.md 10章の2つ目の実行例）。

- 規定ID・チェックIDは**各標準書のものをそのまま使います**（STD-UI-xxx / STD-DD-xxx）。
  統合表だけの新しいID体系を作ると、文書別チェックリストとの対応が1段増えて追跡しにくくなるためです。
- 標準書をまたいで**完全に重複する**チェック項目のみ統合し、複数の標準書を出典として保持します。
- 類似項目は自動統合せず「類似候補」として報告します。
- 重要度は統合した項目のうち**最も重いもの**を採ります（軽い方に引きずられないため）。
- Coverage は**標準書ごとに**算出します。
- 統合表で記入した結果は、統合元となったすべてのチェック項目へ書き戻します。
  同じ内容のチェックが標準書ごとに違う判定になるのを防ぐためです。

成果物: `consolidated-checklist.csv` / `.md`、`cross-traceability-matrix.csv`、
`cross-coverage-report.md`。

### AI推奨事項（要求された場合のみ）

標準書に**規定が無い**観点を提案する機能です。SKILL.md の成果物一覧でも
「要求された場合のみ」とされているため、生成するまで1件も存在せず、既定の成果物は
標準書由来のみで構成されます。

生成方式は2つあります。

| 方式 | 必要なもの | 特徴 |
|---|---|---|
| `catalog`（観点カタログ） | なし | SKILL.md 5章・6章の重点観点と標準書を突き合わせ、触れられていない観点だけを提案。決定的 |
| `claude`（Claude API） | `ANTHROPIC_API_KEY` | 抽出済みの規定一覧を Claude（`claude-opus-5`）に渡し、不足観点を提案させる |

必須原則 8「標準由来と明確に分離する」は、運用ではなく**構造**で担保しています。

- AI推奨事項は専用テーブル（`recommendations`）にしか入らない
- チェックリスト・トレーサビリティ・Coverage のどの問い合わせにも現れない
- 成果物も別ファイル（`ai-recommendations.csv` / `.md`）。ZIP には生成済みの場合だけ同梱される
- CSVに **Standard ID / Chapter / Section / Page 列を持たせない**。標準書に無い提案に出典を書けば、
  それは出典の捏造（禁止事項）になるため
- 各項目に採否（Proposed / Adopted / Rejected）を記録できる

Claude API を使う場合:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```

キーが未設定でも `catalog` 方式は動作します（UIでは Claude の選択肢が無効化されます）。

### レビュー記入

チェックリスト画面で結果（OK / NG / N/A / Pending）・Evidence・Reviewer・Review Date・
コメントを直接編集でき、変更は即座に保存されます。
**再解析しても記入済みの内容は Check ID を手がかりに引き継がれます。**

### 認証（既定は無効）

単独利用ではログイン不要のまま使えます。複数人でレビュー記入する場合は有効にしてください。

```bash
DSC_AUTH_ENABLED=true
DSC_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

- 有効にすると、`/api/health` を除く全APIがログイン必須になります
- 最初のアクセス時に画面から管理者アカウントを作成します（環境変数で初期管理者を指定することも可能）
- パスワードは `hashlib.scrypt`、セッションは HMAC-SHA256 署名トークン。追加の依存はありません
- **判定を記録すると Reviewer 欄がログイン利用者で自動補完されます**（明示入力があればそちらを尊重）
- 利用者の追加は管理者のみ

### データベース

既定は SQLite（`backend/storage/dsc.db` に自動生成されます。準備不要）。
複数人で同時に記入する場合は PostgreSQL を指定してください。
SQLite は書き込みが直列化されるため、同時記入では待ちや失敗が起きやすくなります。

```bash
DSC_DATABASE_URL=postgresql+psycopg://user:password@host:5432/dsc
```

`psycopg` が必要なので `requirements-optional.txt` をインストールしてください。
`docker compose` を使う場合は PostgreSQL が既定で構成されます。

## テスト

```bash
cd backend && .venv/Scripts/python.exe -m pytest -q
```

223件。抽出エンジンの単体テスト（`test_extraction.py`）、各入力形式のパーサ
（`test_parsers.py`）、表形式の標準書と規範表現の語彙（`test_table_standards.py`）、
アップロード〜出力までの結合テスト（`test_api.py`）、横断チェックリスト
（`test_review_sets.py`）、AI推奨事項の分離（`test_recommendations.py`）、
認証（`test_auth.py`）、全サンプル標準書の通し変換（`test_samples.py`）、
AI補助が原文に無い語を混ぜないこと（`test_llm_split.py`）、
変換精度の回帰検知（`test_eval_baseline.py`）を含みます。

### 変換精度の測定

上記のテストは「動くこと」を確認しますが、生成されたチェックリストの**中身が正しいか**は
別問題です。抽出ロジックを触ると、テスト件数は変わらないままチェックリストだけが静かに
悪化することがあります。そのために正解データ（gold）との突き合わせを用意しています。

```bash
cd backend && .venv/Scripts/python.exe -m eval.runner --details
```

標準書5本分の正解データ（規定 115件・確認事項 160件）に対して、規定抽出・Atomic分解・
規範レベル・分類・条件保持・例外保持を測ります。現在のスコアは次のとおりです。

| 指標 | スコア |
|---|---|
| 規定抽出 F1 | 100.0%（取りこぼし 0 / 誤抽出 0） |
| 確認事項 F1 | 98.7%（適合率 100.0% / 再現率 97.5%） |
| 規範レベル正解率 | 100.0% |
| 分類正解率 | 99.1% |
| 条件の保持 | 16/16 |
| 例外の保持 | 4/4 |

正解データの作り方と、残っている変換の課題は
[`backend/eval/README.md`](backend/eval/README.md) を参照してください。

`--check-baseline` で `eval/baseline.json` より悪化していれば exit 1 になり、同じ判定を
`tests/test_eval_baseline.py` が CI で行います。精度を上げたときは `--update-baseline` で
baseline を更新してコミットに含めてください。

push / PR ごとに GitHub Actions で backend のテストと frontend の typecheck・build が走ります
（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）。

```bash
cd frontend && npm run typecheck
```

## API

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/health` | 死活監視（認証が有効でも認証不要） |
| GET | `/api/auth/status` | 認証の有効/無効、初期セットアップの要否、ログイン中の利用者 |
| POST | `/api/auth/login` | ログイン（セッショントークンを返す） |
| GET / POST | `/api/auth/users` | 利用者の一覧 / 追加（1人目のみ未認証で作成可） |
| GET | `/api/meta` | 文書種別・規範レベル・重要度などの語彙 |
| GET / POST | `/api/documents` | 標準書の一覧 / 登録（登録時に自動解析） |
| GET / PATCH / DELETE | `/api/documents/{id}` | 標準書の参照 / メタ情報更新 / 削除 |
| POST | `/api/documents/{id}/analyze` | 再解析 |
| GET | `/api/documents/{id}/rules` | 規定抽出一覧 |
| GET | `/api/documents/{id}/checklist` | チェックリスト（重要度・分類・結果・全文検索で絞り込み可） |
| PATCH | `/api/documents/{id}/checklist/{itemId}` | レビュー結果の記入 |
| GET | `/api/documents/{id}/coverage` | Coverage |
| GET | `/api/documents/{id}/progress` | レビュー進捗 |
| GET | `/api/documents/{id}/traceability` | トレーサビリティ表 |
| GET | `/api/documents/{id}/unconverted` | 未変換規定一覧 |
| GET | `/api/documents/{id}/export[/{artifact}]` | 成果物のダウンロード（未指定ならZIP一括） |
| GET / POST / DELETE | `/api/documents/{id}/recommendations` | AI推奨事項の参照 / 生成 / 全削除 |
| GET | `/api/documents/{id}/recommendations/status` | 生成方式の利用可否（Claude APIキーの有無） |
| PATCH | `/api/documents/{id}/recommendations/{recId}` | 採否・コメントの記入 |
| GET / POST | `/api/review-sets` | 統合レビュー表の一覧 / 作成 |
| GET / PATCH / DELETE | `/api/review-sets/{id}` | 統合レビュー表の参照 / 更新 / 削除 |
| POST | `/api/review-sets/{id}/consolidate` | 最新の解析結果から再統合 |
| GET | `/api/review-sets/{id}/checklist` | 統合チェックリスト |
| PATCH | `/api/review-sets/{id}/checklist/{rowId}` | レビュー結果の記入（統合元すべてへ書き戻す） |
| GET | `/api/review-sets/{id}/coverage` | 標準書別Coverageと重複削減の内訳 |
| GET | `/api/review-sets/{id}/export[/{artifact}]` | 横断成果物のダウンロード |

## 制限事項

- **形態素解析を使っていません。** 規範表現は `backend/app/core/taxonomy.py` の語彙リストと
  文末パターンで判定します。組織固有の言い回しがある場合は、このファイルに語を足してください。
  分類のロジックはすべてこの1ファイルに集約しています。
- **動詞の活用は限定的です。** 一段動詞（含める・設ける・定める等）とサ変は「〜しているか？」へ
  活用しますが、五段動詞は語によって音便が変わるため活用せず、どの動詞でも成立する
  「〜することとしているか？」の形にしています。読みにくさより誤った活用を避けることを優先しました。
- **画像PDF（スキャンPDF）は解析できません。** OCR済みのPDFを使用してください。
- **Word / Excel / Markdown からはページ番号を取得できません。** 「不明」と表示され、
  推測値は入りません。Excel はシート名と行番号を所在として記録します。
- **横断チェックリストの重複統合は完全一致のみです。** 表現が違う同義の規定は
  「類似候補」として報告するに留め、自動統合はしません（規定を勝手に落とさないため）。
- **AI推奨事項の `claude` 方式には API キーと課金が必要です。** キーが無い場合は
  `catalog` 方式（観点カタログ）を使ってください。生成結果が標準書と重複していないかは
  機械的に除外していますが、提案の妥当性は人が判断してください。
- **認証は最小限です。** パスワードログインとセッショントークンのみで、SSO・パスワードリセット・
  監査ログはありません。インターネットに公開する場合はリバースプロキシ側での保護も併用してください。
