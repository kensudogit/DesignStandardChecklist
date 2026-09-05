<#
.SYNOPSIS
  start.ps1 で起動したバックエンドとフロントエンドを停止します。

.DESCRIPTION
  PID のツリーと、待ち受けポートの占有プロセスの両方を止めます。
  npm run dev は起動用のシェルが先に終了して node だけが残ることがあるため、
  ポート側からも確実に止めます。

  このファイルは UTF-8 (BOM 付き) で保存してください。
  Windows PowerShell 5.1 は BOM の無い UTF-8 を CP932 として読むためです。
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot '.running.json'

function Invoke-Taskkill([int]$processId) {
    # taskkill は対象が居ないと stderr に書くため、ここだけ停止扱いにしない
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & taskkill /PID $processId /T /F 2>&1 | Out-Null
    $ErrorActionPreference = $previous
}

function Stop-Target([int]$processId, [int]$port, [string]$label) {
    $stopped = $false

    if ($processId -gt 0 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        Invoke-Taskkill $processId
        $stopped = $true
    }

    # 起動用シェルが先に終了して残った子プロセスを、ポートから特定して止める
    if ($port -gt 0) {
        $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in $owners) {
            Invoke-Taskkill ([int]$owner)
            $stopped = $true
        }
    }

    if ($stopped) {
        Write-Host "$label を停止しました"
    } else {
        Write-Host "$label は既に停止しています" -ForegroundColor DarkGray
    }
}

if (-not (Test-Path $statePath)) {
    Write-Host '起動中のプロセス情報が見つかりません。' -ForegroundColor DarkGray
    Write-Host '既に停止しているか、start.ps1 以外の方法で起動しています。' -ForegroundColor DarkGray
    exit 0
}

$state = Get-Content $statePath -Raw | ConvertFrom-Json
Stop-Target ([int]$state.backend) ([int]$state.backendPort) 'バックエンド'
Stop-Target ([int]$state.frontend) ([int]$state.frontendPort) 'フロントエンド'
Remove-Item $statePath -ErrorAction SilentlyContinue
Write-Host '停止しました。' -ForegroundColor Green
