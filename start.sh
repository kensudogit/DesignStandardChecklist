#!/usr/bin/env bash
# Docker を使わずにバックエンドとフロントエンドを起動します（macOS / Linux 用）。
#
#   必要なもの: Python 3.12 以上 / Node.js 20 以上
#   データベースは SQLite を自動生成するため、準備は不要です。
#
#   使い方:  ./start.sh            既定のポート (backend 8000 / frontend 3000)
#            BACKEND_PORT=8100 FRONTEND_PORT=3100 ./start.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend="$root/backend"
frontend="$root/frontend"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
note() { printf '    \033[90m%s\033[0m\n' "$1"; }
fail() { printf '\033[31mエラー: %s\033[0m\n' "$1" >&2; exit 1; }

# --- 前提の確認 ---
python_bin=""
for candidate in python3.13 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      python_bin="$candidate"
      break
    fi
  fi
done
[ -n "$python_bin" ] || fail "Python 3.12 以上が見つかりません。https://www.python.org/downloads/ から入れてください。"
note "Python: $($python_bin --version)"

command -v node >/dev/null 2>&1 || fail "Node.js が見つかりません。https://nodejs.org/ から LTS を入れてください。"
note "Node.js: $(node --version)"

# --- セットアップ ---
venv_python="$backend/.venv/bin/python"
if [ ! -x "$venv_python" ]; then
  step "Python の仮想環境を作成しています（初回のみ）"
  "$python_bin" -m venv "$backend/.venv"
fi

marker="$backend/.venv/.installed"
if [ ! -f "$marker" ] || [ "$backend/requirements.txt" -nt "$marker" ]; then
  step "バックエンドの依存関係をインストールしています"
  "$venv_python" -m pip install --upgrade pip --quiet
  "$venv_python" -m pip install -r "$backend/requirements.txt" --quiet
  touch "$marker"
fi

if [ ! -d "$frontend/node_modules" ]; then
  step "フロントエンドの依存関係をインストールしています（初回のみ・数分かかります）"
  (cd "$frontend" && npm install --no-audit --no-fund)
fi

# --- ポートの決定 ---
port_free() { ! (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1); }
find_port() {
  local preferred=$1 label=$2 candidate
  for candidate in $(seq "$preferred" $((preferred + 40))); do
    if port_free "$candidate"; then
      [ "$candidate" -ne "$preferred" ] && note "$label: ポート $preferred は使用中のため $candidate を使います"
      echo "$candidate"
      return 0
    fi
  done
  fail "$label: $preferred 以降に空きポートが見つかりません"
}

backend_port=$(find_port "${BACKEND_PORT:-8000}" "バックエンド")
frontend_port=$(find_port "${FRONTEND_PORT:-3000}" "フロントエンド")
api_base="http://localhost:$backend_port"

# --- 起動 ---
step "バックエンドを起動しています"
(cd "$backend" && "$venv_python" -m uvicorn app.main:app --host 127.0.0.1 --port "$backend_port") &
backend_pid=$!

step "フロントエンドを起動しています"
# NEXT_PUBLIC_* はコンパイル時に埋め込まれるため、起動前に渡す
(cd "$frontend" && NEXT_PUBLIC_API_BASE="$api_base" PORT="$frontend_port" npm run dev) &
frontend_pid=$!

cleanup() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
  printf '\033[90m停止しました。\033[0m\n'
}
trap cleanup EXIT INT TERM

step "起動を待っています"
for _ in $(seq 1 40); do
  sleep 0.5
  if curl -fsS "$api_base/api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
done
[ "${ready:-0}" = "1" ] || fail "バックエンドが応答しません。上のログを確認してください。"

printf '\n\033[32m  起動しました\033[0m\n\n'
printf '    アプリ           http://localhost:%s\n' "$frontend_port"
printf '    API ドキュメント %s/docs\n\n' "$api_base"
note "サンプル標準書は samples フォルダにあります"
note "停止するには Ctrl+C を押してください"
printf '\n'

wait
