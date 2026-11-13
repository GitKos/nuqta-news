# Переносит автопостинг в GitHub Actions (бесплатно, работает без этого компьютера).
# Перед запуском один раз выполнить:  gh auth login
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host 'Сначала выполните: gh auth login' -ForegroundColor Red; exit 1 }

Copy-Item data\news.db seed\news.db -Force   # история постов, чтобы не было повторов

if (-not (Test-Path .git)) { git init -q -b main }
git add -A
git -c user.name="news-bot" -c user.email="news-bot@users.noreply.github.com" commit -q -m "News autoposter" 2>$null
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { gh repo create nuqta-news --private --source . --remote origin }

$envs = @{}
Get-Content .env | Where-Object { $_ -match '^\s*([A-Z_]+)=(.+)$' } | ForEach-Object { $envs[$Matches[1]] = $Matches[2].Trim() }
gh secret set BOT_TOKEN  --body $envs['BOT_TOKEN']
gh secret set CHANNEL_ID --body $envs['CHANNEL_ID']
gh secret set GEMINI_API_KEY --body $env:GEMINI_API_KEY
gh secret set PIXABAY_KEY    --body $env:PIXABAY_KEY

git push -q -u origin main
# локальный автозапуск выключаем, чтобы посты не дублировались
schtasks /Change /TN UzNewsBot /Disable | Out-Null
gh workflow run news
Write-Host 'Готово. Первый запуск стартовал, статус: gh run list --limit 3' -ForegroundColor Green
