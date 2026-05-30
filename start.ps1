# 一鍵啟動：自動建立環境，並同時啟動 FastAPI 後端與 React 前端。
#
#   .\start.ps1
#
# 首次執行會建立 Python 虛擬環境、安裝後端與前端相依套件（需數分鐘）；
# 之後僅啟動服務。關閉各視窗即可停止對應服務。
#
# 環境變數：
#   $env:PYTHON = "python3.12"; .\start.ps1   指定 Python 直譯器（預設 python）

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PYTHON = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$BACKEND_PORT = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }

# ── 1) Python 後端環境 ───────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "▶ 建立 Python 虛擬環境並安裝後端相依…"
    & $PYTHON -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
}

# ── 2) 前端相依 ──────────────────────────────────────
if (-not (Test-Path "web\node_modules")) {
    Write-Host "▶ 安裝前端相依（npm install）…"
    Push-Location web
    npm install
    Pop-Location
}

# ── 3) 寫暫存啟動腳本，避開路徑字串逸出問題 ────────────
$backendBat = Join-Path $ScriptDir "_start_backend.cmd"
$frontendBat = Join-Path $ScriptDir "_start_frontend.cmd"

Set-Content -Encoding utf8 -Path $backendBat -Value @"
@echo off
cd /d "$ScriptDir"
set PYTHONPATH=server
".venv\Scripts\python.exe" -m uvicorn server.main:app --host 0.0.0.0 --port $BACKEND_PORT --timeout-graceful-shutdown 3
pause
"@

Set-Content -Encoding utf8 -Path $frontendBat -Value @"
@echo off
cd /d "$ScriptDir\web"
npm run dev
pause
"@

# ── 4) 開兩個 cmd 視窗分別跑前後端 ───────────────────
Write-Host "▶ 後端  → http://localhost:${BACKEND_PORT}"
Write-Host "▶ 前端  → http://localhost:5173"
Write-Host "（首次查詢個股會下載 10 年歷史，需稍候）"
Write-Host ""

Start-Process cmd -ArgumentList "/c", "start", "cmd", "/k", $backendBat
Start-Sleep -Seconds 1
Start-Process cmd -ArgumentList "/c", "start", "cmd", "/k", $frontendBat

# 稍候後自動開啟瀏覽器
Write-Host "▶ 4 秒後自動開啟瀏覽器…"
Start-Sleep -Seconds 4
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "後端與前端已在獨立視窗啟動。"
Write-Host "直接關閉各視窗即可停止對應服務。"
