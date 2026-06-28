# Starts the frontend dev server on :5173 (proxies /api -> backend :8000)
Set-Location "$PSScriptRoot/frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
