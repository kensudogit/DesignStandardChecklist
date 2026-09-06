/**
 * 全ページ共通のレイアウト。ヘッダとナビゲーションを置く。
 *
 * 本文を `AuthGate` で包んでいるため、認証が有効なときは未ログイン状態で
 * 各ページの中身が描画されることはない。認証が無効なら素通しになる。
 */

import type { Metadata } from "next";
import Link from "next/link";

import { AuthBadge, AuthGate } from "@/components/AuthGate";
import { GuideButton } from "@/components/GuideModal";
import "./globals.css";

/** ブラウザのタブと検索結果に出る情報。 */
export const metadata: Metadata = {
  title: "設計標準チェックリスト生成",
  description:
    "設計標準書を解析し、規定抽出・Atomic Check分解・重要度付与・トレーサビリティ・Coverage確認を経てレビュー用チェックリストを生成します。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body>
        <header className="app-header">
          <div className="row">
            <div>
              <h1>設計標準チェックリスト生成</h1>
              <p>
                標準書 → 規定抽出 → Atomic Check分解 → 重要度付与 → トレーサビリティ →
                Coverage確認 → チェックリスト出力
              </p>
            </div>
            <span className="spacer" />
            <nav className="row" style={{ gap: 6 }}>
              <Link className="nav-link" href="/">
                標準書
              </Link>
              <Link className="nav-link" href="/review-sets">
                統合レビュー表
              </Link>
              <GuideButton />
              <AuthBadge />
            </nav>
          </div>
        </header>
        <main className="container">
          <AuthGate>{children}</AuthGate>
        </main>
      </body>
    </html>
  );
}
