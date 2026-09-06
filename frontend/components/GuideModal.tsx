"use client";

/**
 * 「利用手順」モーダル。ヘッダーのボタンから開く。
 *
 * 手順の文章はこのファイル内の定数として持つ。別ファイルや API に置くほどの
 * 量ではなく、画面の変更と説明の変更を同じ差分で追えるようにするため。
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 利用手順1ステップ分。`note` は補足で、無ければ出さない。 */
interface Step {
  no: string;
  title: string;
  body: string;
  note?: string;
}

/**
 * 基本的な使い方。登録から成果物出力までを一周する順に並べている。
 *
 * 本文は表示専用の定数。仕様を変えたらここも直す必要があるので、
 * 挙動を書き換えたときは対応するステップの記述を確認すること。
 */
const BASIC_STEPS: Step[] = [
  {
    no: "01",
    title: "標準書を登録する",
    body: "トップ画面のフォームで標準書ファイルを選び、文書種別を選択して「登録して解析する」を押します。PDF・Word（.docx）・Excel（.xlsx）・Markdown・テキスト・CSV に対応しています。版数や制定日は任意で、未入力なら「不明」として記録されます。アップロード後、規定の抽出から Coverage の算出までを自動で実行します。",
    note: "表形式（Excel）の標準書は「規定内容」列を自動判定し、章・節・分類・区分・重要度・備考の各列を標準書の記載として取り込みます。行を丸ごと連結することはありません。",
  },
  {
    no: "02",
    title: "チェックリストを確認する",
    body: "解析が終わると詳細画面が開きます。「レビューチェックリスト」が主画面で、重要度・分類・結果で絞り込み、チェック項目・規定原文・各種IDを対象に全文検索できます。重要度は Critical / High / Medium / Low の順に並びます。",
    note: "各行の「標準書の原文」を開くと、そのチェックの根拠になった規定の文をそのまま読めます。重要度バッジにマウスを乗せると判定根拠が表示されます。",
  },
  {
    no: "03",
    title: "レビュー結果を記入する",
    body: "結果（OK / NG / N/A / Pending）、Evidence、Reviewer、Review Date、コメントを直接編集できます。結果はその場で、テキスト欄はフォーカスを外した時点で保存されます。NG の行は背景色が変わるため、残課題を見つけやすくなっています。",
    note: "認証を有効にしている場合、結果を記録すると Reviewer 欄にログイン中の利用者が自動で入ります。手入力した値は上書きしません（代理入力のため）。",
  },
  {
    no: "04",
    title: "根拠をたどる",
    body: "「トレーサビリティ」タブで、Check ID → Standard ID → 出典（文書名・章・節・ページ）の対応を確認できます。「規定抽出一覧」タブでは、抽出した規定そのものと、そこから生成されたチェックIDを一覧できます。",
    note: "ページ番号は PDF からしか取得できません。Word・Excel・Markdown では「不明」と表示します。推測したページ番号を入れることはありません。",
  },
  {
    no: "05",
    title: "Coverage を確認する",
    body: "「Coverage」タブで、チェック項目化できた規定の割合を確認します。必須規定・禁止規定は 100% が目標で、未達なら Findings に警告が出ます。曖昧な表現を含む規定、出典を特定できない規定、重複候補の件数もここに出ます。",
    note: "チェック項目にできなかった規定は「未変換規定」タブに理由と必要な対応が並びます。Coverage が 100% でない場合はここを確認してください。",
  },
  {
    no: "06",
    title: "成果物を出力する",
    body: "詳細画面の上部から、チェックリスト（CSV / Markdown）、規定抽出一覧、トレーサビリティ表、未変換規定一覧、Coverage レポート、標準書一覧をダウンロードできます。「成果物一式 (ZIP)」で一括取得も可能です。",
    note: "CSV は Excel でそのまま開けるよう UTF-8 BOM 付きで出力します。列構成は skill/templates のテンプレートと一致しています。",
  },
];

/** 一周したあとに使う機能。統合レビュー表・AI推奨事項・再解析。 */
const ADVANCED_STEPS: Step[] = [
  {
    no: "07",
    title: "複数の標準書を横断する",
    body: "ヘッダーの「統合レビュー表」から、複数の標準書を選んで1枚の横断チェックリストを作れます。規定ID・チェックIDは各標準書のものをそのまま使うため、文書別のチェックリストとの対応を追えます。",
    note: "標準書をまたいで完全に一致するチェック項目だけを統合し、複数の標準書を出典として保持します。表現が違う類似項目は自動統合せず「類似候補」として報告します。統合表で記入した結果は、統合元すべてのチェック項目へ書き戻されます。",
  },
  {
    no: "08",
    title: "AI推奨事項を生成する",
    body: "「AI推奨事項」タブで、標準書に規定が無い観点を提案できます。生成方式は2つあり、観点カタログ方式は追加インストールもAPIキーも不要です。Claude API 方式は ANTHROPIC_API_KEY を設定した場合のみ選べます。",
    note: "AI推奨事項は標準書由来ではありません。チェックリスト・トレーサビリティ・Coverage には一切含まれず、出典（章・節・ページ）も持ちません。成果物も別ファイルで、採否を Proposed / Adopted / Rejected で記録できます。",
  },
  {
    no: "09",
    title: "標準書を更新したら再解析する",
    body: "標準書が改訂されたら、同じ標準書を登録し直すか「再解析」を押します。規定IDとチェックIDは振り直されますが、記入済みの結果・Evidence・Reviewer・コメントは Check ID を手がかりに引き継がれます。",
    note: "統合レビュー表を作っている場合は、各標準書を再解析したあとに「再統合」を押して最新の解析結果から作り直してください。",
  },
];

/** つまずきやすい点。原因と対処を対にして並べる。 */
const TIPS: { title: string; body: string }[] = [
  {
    title: "ポートが使用中で起動できない",
    body: "start.ps1 / start.sh は使用中のポートを検出して空きポートを自動で探します。実際に使われたポートは起動時のメッセージに表示されます。",
  },
  {
    title: "PDF から規定が取れない",
    body: "画像として取り込まれたスキャンPDFは解析できません。OCR 済みの、文字を選択できるPDFを使用してください。",
  },
  {
    title: "組織固有の言い回しが拾われない",
    body: "規範表現の語彙は backend/app/core/taxonomy.py の1ファイルに集約しています。「〜を厳守する」のような独自表現は、ここに追加すれば抽出されるようになります。",
  },
  {
    title: "複数人で同時に記入したい",
    body: "認証を有効にし、データベースを PostgreSQL に切り替えてください。SQLite は書き込みが直列化されるため、同時記入では待ちや失敗が起きやすくなります。",
  },
];

/** 冒頭に出す構成技術。中身の説明ではなく、全体像を掴ませるための飾り。 */
const TAGS = [
  "Next.js 16",
  "React 19",
  "TypeScript",
  "FastAPI",
  "SQLAlchemy",
  "SQLite / PostgreSQL",
  "Docker",
  "GitHub Actions",
  "Claude API",
];

/**
 * 利用手順のモーダル。
 *
 * 閉じる手段は3つ用意している (×ボタン / 背景クリック / Escape キー)。
 * 内容が長いため、閉じ方が分からず行き詰まるのを避けるため。
 */
export function GuideModal({ onClose }: { onClose: () => void }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [atBottom, setAtBottom] = useState(false);

  // 末尾まで読んだかどうか。24px の余裕を持たせているのは、
    // 端数や慣性スクロールでぴったり一致しないことがあるため
  const handleScroll = useCallback(() => {
    const element = bodyRef.current;
    if (!element) return;
    setAtBottom(element.scrollTop + element.clientHeight >= element.scrollHeight - 24);
  }, []);

  useEffect(() => {
    // 開いた直後のキーボード操作がモーダル内から始まるようにする
    closeRef.current?.focus();
    // 背景のスクロールを止める。元の値を控えておき、閉じるときに戻す
        // (決め打ちで "" に戻すと、他が設定していた値を壊す)
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  // 背景クリックで閉じる。パネル側で伝播を止めているので中身の操作では閉じない
  return (
    <div className="guide-overlay" onClick={onClose} role="presentation">
      <div
        className="guide-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        /* パネル内のクリックが背景まで届くと、操作するたびに閉じてしまう */
        onClick={(event) => event.stopPropagation()}
      >
        <header className="guide-header">
          <span className="guide-bar" aria-hidden="true" />
          <span className="guide-menu" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <div className="guide-heading">
            <h2 id="guide-title">利用手順</h2>
            <p className="guide-eyebrow">DESIGN STANDARD GUIDE</p>
          </div>
          <span className="guide-spacer" />
          {/* 末尾まで読んだら消す。読み終えた後も出続けると急かして見える */}
          {!atBottom && <span className="guide-scroll-hint">スクロールして確認</span>}
          <button
            ref={closeRef}
            type="button"
            className="guide-close"
            onClick={onClose}
            aria-label="閉じる"
          >
            ×
          </button>
        </header>

        <div className="guide-body" ref={bodyRef} onScroll={handleScroll}>
          <section className="guide-card guide-card-hero">
            <p className="guide-card-eyebrow">画面設計 / 詳細設計 / DB / API 設計標準</p>
            <h3>設計標準チェックリスト生成</h3>
            <p className="guide-card-text">
              設計標準書を読み込み、規定を抽出して「確認可能な質問」に変換し、重要度・出典・
              Coverage を付けたレビュー用チェックリストを生成します。ブラウザ上でレビュー結果を
              記入し、CSV / Markdown で出力できます。
            </p>
            <div className="guide-tags">
              {TAGS.map((tag) => (
                <span key={tag} className="guide-tag">
                  {tag}
                </span>
              ))}
            </div>
          </section>

          <section className="guide-card guide-card-arch">
            <div className="guide-badge-row">
              <span className="guide-badge">ARCHITECTURE</span>
              <h3>Next.js UI + FastAPI 抽出エンジン</h3>
            </div>
            <p className="guide-card-text">
              Next.js から FastAPI を呼び出し、解析結果を SQLite（既定）または PostgreSQL に
              保存します。抽出エンジンは決定的なルールベースで、同じ標準書からは常に同じ
              チェックリストが生成されます。
            </p>
            <ul className="guide-list">
              <li>Next.js — 標準書一覧・チェックリスト記入・統合レビュー表・成果物出力</li>
              <li>FastAPI — 文書構造解析・規定抽出・Atomic Check 分解・重要度付与・Coverage</li>
              <li>SQLite / PostgreSQL — 標準書・規定・チェック項目・レビュー結果</li>
              <li>Claude API — AI推奨事項の生成のみ（任意。標準由来の成果物とは完全に分離）</li>
              <li>GitHub Actions — テスト・型チェック・ビルド・スクリプト構文検査</li>
            </ul>
          </section>

          <p className="guide-section-label">BASIC WORKFLOW</p>
          {BASIC_STEPS.map((step) => (
            <StepCard key={step.no} step={step} />
          ))}

          <p className="guide-section-label">ADVANCED</p>
          {ADVANCED_STEPS.map((step) => (
            <StepCard key={step.no} step={step} />
          ))}

          <p className="guide-section-label">PRINCIPLES</p>
          <section className="guide-card guide-card-arch">
            <div className="guide-badge-row">
              <span className="guide-badge">RULES</span>
              <h3>この生成器が守っていること</h3>
            </div>
            <ul className="guide-list">
              <li>標準書に書かれていない規定を、標準書由来として追加しない</li>
              <li>章・節・ページを推測しない。取得できなければ「不明」と表示する</li>
              <li>条件付き規定の条件と、例外規定を落とさない</li>
              <li>必須・禁止・推奨・任意を混同しない</li>
              <li>1つのチェック項目には1つの確認事項だけを入れる</li>
              <li>すべてのチェック項目を Yes / No / N/A で判定できる疑問文にする</li>
              <li>AI推奨事項は標準由来と構造的に分離する</li>
            </ul>
          </section>

          <p className="guide-section-label">TIPS</p>
          <section className="guide-card">
            <dl className="guide-faq">
              {TIPS.map((tip) => (
                <div key={tip.title}>
                  <dt>{tip.title}</dt>
                  <dd>{tip.body}</dd>
                </div>
              ))}
            </dl>
          </section>

          <p className="guide-footnote">
            サンプルの標準書は <code>samples/</code> フォルダにあります。まずはこれを登録して
            動きを確認してください。
          </p>
        </div>
      </div>
    </div>
  );
}

/** ステップ1件の見た目。番号は装飾なので読み上げ対象から外す。 */
function StepCard({ step }: { step: Step }) {
  return (
    <section className="guide-step">
      <span className="guide-step-no" aria-hidden="true">
        {step.no}
      </span>
      <div className="guide-step-main">
        <h3>{step.title}</h3>
        <p>{step.body}</p>
        {step.note && <p className="guide-note">{step.note}</p>}
      </div>
    </section>
  );
}

/** ヘッダーに置く「利用手順」ボタン。押すとモーダルを開く。 */
export function GuideButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="guide-trigger" onClick={() => setOpen(true)}>
        利用手順
      </button>
      {open && <GuideModal onClose={() => setOpen(false)} />}
    </>
  );
}
