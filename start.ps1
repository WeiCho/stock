# 一鍵啟動：自動建立環境，並同時啟動 FastAPI 後端與 React 前端。
#
#   .\start.ps1
#
# 首次執行會建立 Python 虛擬環境、安裝後端與前端相依套件（需數分鐘）；
# 之後僅啟動服務。關閉此視窗即可同時停止前後端。
#
# 環境變數：
#   $env:PYTHON = "python3.12"; .\start.ps1   指定 Python 直譯器（預設 python）

chcp 65001 | Out-Null
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

# ── 3) 直接啟動前後端 process（背景，不開新視窗）────────
Write-Host "▶ 啟動後端  → http://localhost:${BACKEND_PORT}"
$env:PYTHONPATH = "server"
$backendProc = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "server.main:app",
                  "--host", "0.0.0.0", "--port", $BACKEND_PORT,
                  "--timeout-graceful-shutdown", "3" `
    -WorkingDirectory $ScriptDir `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 2

Write-Host "▶ 啟動前端  → http://localhost:5173"
$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory (Join-Path $ScriptDir "web") `
    -PassThru -NoNewWindow

Write-Host "（首次查詢個股會下載 10 年歷史，需稍候）"
Write-Host ""

# 稍候後自動開啟瀏覽器
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host "▶ 服務已啟動。關閉此視窗即可同時停止前後端。"
Write-Host ""

# ── 4) 等待，關閉視窗或 Ctrl+C 時 kill 前後端 ────────
try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Write-Host ""
    Write-Host "▶ 正在停止服務…"
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc -and -not $frontendProc.HasExited) {
        # kill npm 及其子 process（node/vite）
        $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $frontendProc.Id }
        foreach ($c in $children) { Stop-Process -Id $c.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "▶ 已停止。"
}