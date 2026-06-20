set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

dev:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/dev/devinit.ps1

stop:
  Write-Host "No tmux session is managed in Windows native mode."

logs:
  if (Test-Path twitter-auto-poster.log) { Get-Content twitter-auto-poster.log -Wait } else { Write-Host "twitter-auto-poster.log not found." }

session-logs:
  if (Test-Path docs/working-memory/session-logs) { Get-ChildItem docs/working-memory/session-logs | Sort-Object LastWriteTime -Descending } else { Write-Host "docs/working-memory/session-logs not found." }
