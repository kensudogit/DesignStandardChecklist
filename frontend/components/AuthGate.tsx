"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, ApiError, auth } from "@/lib/api";
import type { AuthStatus, AuthUser } from "@/lib/types";

interface AuthContextValue {
  enabled: boolean;
  user: AuthUser | null;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  enabled: false,
  user: null,
  logout: () => undefined,
});

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * 認証が有効なときだけログイン画面を挟む。
 * 無効なとき（既定）は何も表示せず、そのまま子要素を描画する。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.authStatus());
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "認証状態を取得できません");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const logout = useCallback(() => {
    auth.clear();
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="alert alert-error" style={{ marginTop: 20 }}>
        {error}
      </div>
    );
  }

  if (status === null) {
    return <p className="muted">読み込み中…</p>;
  }

  if (!status.auth_enabled) {
    return (
      <AuthContext.Provider value={{ enabled: false, user: null, logout }}>
        {children}
      </AuthContext.Provider>
    );
  }

  if (status.user === null) {
    return <LoginScreen needsBootstrap={status.needs_bootstrap} onDone={load} />;
  }

  return (
    <AuthContext.Provider value={{ enabled: true, user: status.user, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

function LoginScreen({
  needsBootstrap,
  onDone,
}: {
  needsBootstrap: boolean;
  onDone: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (needsBootstrap) {
        await api.createUser({
          username: username.trim(),
          password,
          display_name: displayName.trim() || username.trim(),
        });
      }
      const result = await api.login(username.trim(), password);
      auth.set(result.token);
      setPassword("");
      onDone();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "ログインに失敗しました");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ maxWidth: 460, margin: "40px auto" }}>
      <h2>{needsBootstrap ? "初期管理者の作成" : "ログイン"}</h2>
      <p className="hint">
        {needsBootstrap
          ? "利用者がまだ登録されていません。最初の管理者アカウントを作成してください。"
          : "レビュー結果の記入者を記録するため、ログインが必要です。"}
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <form onSubmit={submit}>
        <div style={{ marginBottom: 12 }}>
          <label htmlFor="username">ユーザー名</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>

        {needsBootstrap && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="display-name">表示名（Reviewer欄に記録されます）</label>
            <input
              id="display-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="未入力ならユーザー名を使用"
            />
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <label htmlFor="password">パスワード</label>
          <input
            id="password"
            type="password"
            autoComplete={needsBootstrap ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={needsBootstrap ? 8 : undefined}
          />
          {needsBootstrap && (
            <p className="small muted" style={{ margin: "4px 0 0" }}>
              8文字以上。
            </p>
          )}
        </div>

        <button className="primary" type="submit" disabled={busy}>
          {busy ? "処理中…" : needsBootstrap ? "作成してログイン" : "ログイン"}
        </button>
      </form>
    </section>
  );
}

/** ヘッダーに出すログイン状態。認証が無効なら何も出さない。 */
export function AuthBadge() {
  const { enabled, user, logout } = useAuth();
  if (!enabled || user === null) return null;
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className="small muted">
        {user.display_name}
        {user.is_admin && <span className="origin-tag">管理者</span>}
      </span>
      <button onClick={logout}>ログアウト</button>
    </span>
  );
}
