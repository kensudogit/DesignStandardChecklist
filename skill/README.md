# design-standard-checklist-generator

設計標準書からレビュー用チェックリストを作成するためのClaude/AI向けSkillです。

## 主な用途

- 画面設計標準 → 画面設計レビュー表
- 詳細設計標準 → 詳細設計レビュー表
- API設計標準 → API設計レビュー表
- DB設計標準 → DB設計レビュー表
- 複数標準書 → 統合レビュー表

## 特徴

- 規定抽出
- Atomic Check分解
- 重要度判定
- 標準書とチェック項目のトレーサビリティ
- Coverage確認
- 未変換規定の検出
- AI推測と標準由来の分離

## 推奨成果物

1. standard-register.csv
2. extracted-rules.csv
3. design-review-checklist.csv
4. traceability-matrix.csv
5. unconverted-rules.csv
6. coverage-report.md

## 利用例

「この画面設計標準PDFから、実際の設計レビューで利用できるチェックリストを作成してください。
各チェック項目に標準書の章・節・ページ・規定IDを付け、必須・禁止規定のCoverageを100%確認してください。」

## フォルダ名

親フォルダ名と `SKILL.md` の `name` は一致させています。

`design-standard-checklist-generator`
