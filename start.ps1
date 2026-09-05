<#
.SYNOPSIS
  Docker を使わずにバックエンドとフロントエンドを起動します。

.DESCRIPTION
  初回は Python の仮想環境と npm パッケージを自動で用意します。
  2回目以降は起動だけなので数秒で立ち上がります。

  必要なもの: Python 3.12 以上 / Node.js 20 以上
  データベースは SQLite (backend/storage/dsc.db) を自動生成するため、準備は不要です。

  このファイルは UTF-8 (BOM 付き) で保存してください。
  Windows PowerShell 5.1 は BOM の無い UTF-8 を CP932 として読むため、
  日本語を含むスクリプトが構文エラーになります。

.PARAMETER BackendPort
  バックエンドのポート。既定 8000。使用中なら空きポートを自動で探します。

.PARAMETER FrontendPort
  フロントエンドのポート。既定 3000。使用中なら空きポートを自動で探します。

.PARAMETER SkipInstall
  依存関係のインストールを省略して起動だけ行います。

.EXAMPLE
  .\start.ps1

.EXAMPLE
  .\start.ps1 -FrontendPort 3400
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Write-Note($message) { Write-Host "    $message" -ForegroundColor DarkGray }
function Fail($message) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }

function Invoke-Taskkill([int]$processId) {
    # taskkill は対象が居ないと stderr に書くため、ここだけ停止扱いにしない
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & taskkill /PID $processId /T /F 2>&1 | Out-Null
    $ErrorActionPreference = $previous
}

function Stop-Everything([int]$backendPid, [int]$frontendPid, [int]$backendPort, [int]$frontendPort) {
    foreach ($processId in @($backendPid, $frontendPid)) {
        if ($processId -gt 0) { Invoke-Taskkill $processId }
    }
    # 起動用シェルが先に終了して残った子プロセスも、ポートから特定して止める
    foreach ($port in @($backendPort, $frontendPort)) {
        if ($port -le 0) { continue }
        $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in $owners) { Invoke-Taskkill ([int]$owner) }
    }
}

function Test-PortFree([int]$port) {
    return -not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Find-FreePort([int]$preferred, [string]$label) {
    if (Test-PortFree $preferred) { return $preferred }
    for ($candidate = $preferred + 1; $candidate -le $preferred + 40; $candidate++) {
        if (Test-PortFree $candidate) {
            Write-Note "$label : ポート $preferred は使用中のため $candidate を使います"
            return $candidate
        }
    }
    Fail "$label : $preferred 以降に空きポートが見つかりません"
}

# --- 前提の確認 --------------------------------------------------------------

Write-Step '前提を確認しています'

$pythonExe = $null
$pythonArgs = @()
$candidates = @(
    @{ Exe = 'py'; Args = @('-3.12') },
    @{ Exe = 'py'; Args = @('-3') },
    @{ Exe = 'python3'; Args = @() },
    @{ Exe = 'python'; Args = @() }
)
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $version = (& $candidate.Exe @($candidate.Args) --version 2>&1 | Out-String).Trim()
    } catch {
        continue
    }
    if ($version -match 'Python (\d+)\.(\d+)') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 12)) {
            $pythonExe = $candidate.Exe
            $pythonArgs = $candidate.Args
            Write-Note "Python: $version"
            break
        }
    }
}
if (-not $pythonExe) {
    Write-Host 'ERROR: Python 3.12 以上が見つかりません。' -ForegroundColor Red
    Write-Host '  次のいずれかで導入してください:' -ForegroundColor Red
    Write-Host '    winget install --id Python.Python.3.12 -e' -ForegroundColor Red
    Write-Host '    https://www.python.org/downloads/' -ForegroundColor Red
    Write-Host '  導入後、PowerShell を開き直してから再実行してください。' -ForegroundColor Red
    exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: Node.js が見つかりません。' -ForegroundColor Red
    Write-Host '  次のいずれかで導入してください:' -ForegroundColor Red
    Write-Host '    winget install --id OpenJS.NodeJS.LTS -e' -ForegroundColor Red
    Write-Host '    https://nodejs.org/' -ForegroundColor Red
    Write-Host '  導入後、PowerShell を開き直してから再実行してください。' -ForegroundColor Red
    exit 1
}
Write-Note "Node.js: $(node --version)"

# --- セットアップ ------------------------------------------------------------

$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

if (-not $SkipInstall) {
    if (-not (Test-Path $venvPython)) {
        Write-Step 'Python の仮想環境を作成しています (初回のみ)'
        & $pythonExe @($pythonArgs) -m venv (Join-Path $backend '.venv')
        if ($LASTEXITCODE -ne 0) { Fail '仮想環境の作成に失敗しました' }
    }

    # requirements.txt が前回のインストールより新しいときだけ入れ直す
    $marker = Join-Path $backend '.venv\.installed'
    $requirements = Join-Path $backend 'requirements.txt'
    $needsInstall = -not (Test-Path $marker)
    if (-not $needsInstall) {
        $needsInstall = (Get-Item $requirements).LastWriteTimeUtc -gt (Get-Item $marker).LastWriteTimeUtc
    }
    if ($needsInstall) {
        Write-Step 'バックエンドの依存関係をインストールしています (初回は数分かかります)'
        & $venvPython -m pip install --upgrade pip --quiet
        & $venvPython -m pip install -r $requirements --quiet
        if ($LASTEXITCODE -ne 0) { Fail 'バックエンドの依存関係のインストールに失敗しました' }
        New-Item -ItemType File -Path $marker -Force | Out-Null
    }

    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Step 'フロントエンドの依存関係をインストールしています (初回のみ・数分かかります)'
        Push-Location $frontend
        try {
            & npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { Fail 'npm install に失敗しました' }
        } finally {
            Pop-Location
        }
    }
}

if (-not (Test-Path $venvPython)) { Fail "仮想環境が見つかりません: $venvPython" }

# --- ポートの決定 ------------------------------------------------------------

$BackendPort = Find-FreePort $BackendPort 'バックエンド'
$FrontendPort = Find-FreePort $FrontendPort 'フロントエンド'
$apiBase = "http://localhost:$BackendPort"

# --- 起動 --------------------------------------------------------------------

$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null

function Show-Log([string]$label, [string]$path) {
    if (-not (Test-Path $path)) { return }
    $lines = Get-Content $path -Tail 25 -ErrorAction SilentlyContinue
    if (-not $lines) { return }
    Write-Host ""
    Write-Host "--- $label ---" -ForegroundColor Yellow
    $lines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
}

Write-Step 'バックエンドを起動しています'
$backendProcess = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath $venvPython `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
    -WorkingDirectory $backend `
    -RedirectStandardOutput (Join-Path $logs 'backend.log') `
    -RedirectStandardError (Join-Path $logs 'backend.err')

Write-Step 'フロントエンドを起動しています'
# NEXT_PUBLIC_* はコンパイル時に埋め込まれるため、起動前に環境変数で渡す
$env:NEXT_PUBLIC_API_BASE = $apiBase
$env:PORT = "$FrontendPort"
$frontendProcess = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath 'cmd.exe' `
    -ArgumentList @('/c', 'npm', 'run', 'dev') `
    -WorkingDirectory $frontend `
    -RedirectStandardOutput (Join-Path $logs 'frontend.log') `
    -RedirectStandardError (Join-Path $logs 'frontend.err')

Write-Step '起動を待っています (初回は依存の読み込みに時間がかかります)'
# localhost は ::1 に解決されることがあるので、127.0.0.1 を明示して確認する
$healthUrl = "http://127.0.0.1:$BackendPort/api/health"
$ready = $false
for ($attempt = 1; $attempt -le 180; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($backendProcess.HasExited) {
        Show-Log 'backend.err' (Join-Path $logs 'backend.err')
        Fail "バックエンドが終了しました (exit $($backendProcess.ExitCode))"
    }
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        # まだ起動中
    }
}
if (-not $ready) {
    Show-Log 'backend.err' (Join-Path $logs 'backend.err')
    Show-Log 'backend.log' (Join-Path $logs 'backend.log')
    Stop-Everything $backendProcess.Id $frontendProcess.Id $BackendPort $FrontendPort
    Fail "バックエンドが応答しません (90秒待機)。上のログを確認してください。"
}

# フロントエンドが待ち受け始めるまで待つ (ブラウザを早く開きすぎないように)
for ($attempt = 1; $attempt -le 120; $attempt++) {
    if (-not (Test-PortFree $FrontendPort)) { break }
    if ($frontendProcess.HasExited) {
        Show-Log 'frontend.err' (Join-Path $logs 'frontend.err')
        Fail "フロントエンドが終了しました (exit $($frontendProcess.ExitCode))"
    }
    Start-Sleep -Milliseconds 500
}

# プロセスIDを控えておき、stop.ps1 から止められるようにする
$state = @{
    backend      = $backendProcess.Id
    frontend     = $frontendProcess.Id
    backendPort  = $BackendPort
    frontendPort = $FrontendPort
}
$state | ConvertTo-Json | Set-Content -Path (Join-Path $root '.running.json') -Encoding UTF8

Write-Host ''
Write-Host '  起動しました' -ForegroundColor Green
Write-Host ''
Write-Host "    アプリ           http://localhost:$FrontendPort"
Write-Host "    API ドキュメント $apiBase/docs"
Write-Host ''
Write-Note 'サンプル標準書は samples フォルダにあります'
Write-Note 'ログは logs フォルダに出力されます'
Write-Note '停止するには、このウィンドウで Ctrl+C を押すか .\stop.ps1 を実行してください'
Write-Host ''

try {
    Start-Process "http://localhost:$FrontendPort" | Out-Null
} catch {
    Write-Note 'ブラウザを自動で開けませんでした。上のURLを開いてください。'
}

try {
    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-Everything $backendProcess.Id $frontendProcess.Id $BackendPort $FrontendPort
    Remove-Item (Join-Path $root '.running.json') -ErrorAction SilentlyContinue
    Write-Host '停止しました。' -ForegroundColor DarkGray
}
