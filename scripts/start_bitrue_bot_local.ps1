param(
    [string]$ConfigPath = "config/bitrue_bot.local.json",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000
)

$env:BITRUE_BOT_CONFIG = $ConfigPath

if (-not $env:BITRUE_WEBHOOK_SECRET) {
    Write-Error "BITRUE_WEBHOOK_SECRET is not set. Set it in your shell before starting the bot."
    exit 1
}

Write-Host "Starting Bitrue bot in local-only mode on $Host`:$Port using $ConfigPath"
uvicorn bitrue_bot.main:app --host $Host --port $Port

