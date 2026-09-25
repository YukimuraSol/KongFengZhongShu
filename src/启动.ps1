param()
$ErrorActionPreference = "Stop"
$Root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location -LiteralPath $Root

$deskExe = Join-Path $Root "kongfenzhongshu.exe"

if (-not (Test-Path -LiteralPath $deskExe)) {
    Write-Host "错误: 未找到 kongfenzhongshu.exe" -ForegroundColor Red
    exit 1
}

# 后端由 exe 在同目录检测到 python\python.exe + backend\ 时自动拉起；关闭窗口后自动结束。
Start-Process -FilePath $deskExe -WorkingDirectory $Root -Wait
