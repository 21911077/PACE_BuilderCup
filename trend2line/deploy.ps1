param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,

    [string]$Region = "asia-south1",
    [string]$Service = "trend2line",
    [int]$MockLlm = 0,
    [string]$GeminiModel = "",
    [string]$WikiUserAgent = "Trend2Line/0.1"
)

$ErrorActionPreference = "Stop"

Write-Host "==> Checking hackathon compliance (Gemini-only)..." -ForegroundColor Cyan
$matches = Select-String -Path @("requirements*.txt", "app\*.py", "app\stages\*.py", "adk_app\*.py") -Pattern '(^|[^a-z])(anthropic|openai)([^a-z]|$)' -AllMatches -ErrorAction SilentlyContinue | Where-Object { $_.Line -notmatch '^\s*#' }
if ($matches) {
    Write-Error "ERROR: non-Google model SDK referenced in runtime code.`n$($matches | Out-String)"
    exit 1
}
Write-Host "OK: runtime code is Gemini-only." -ForegroundColor Green

$argsList = @(
    "run", "deploy", $Service,
    "--source", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--allow-unauthenticated",
    "--memory", "1Gi",
    "--cpu", "1",
    "--timeout", "300",
    "--max-instances", "3"
)

if ($MockLlm -eq 1) {
    Write-Host "==> Deploying in MOCK mode (No Gemini calls, instant & safe)..." -ForegroundColor Yellow
    $argsList += "--set-env-vars"
    $argsList += "MOCK_LLM=1"
} else {
    if (-not $GeminiModel) {
        Write-Error "Deploy in live mode requires -GeminiModel (e.g. -GeminiModel 'gemini-2.5-flash'). Or specify -MockLlm 1."
        exit 1
    }
    Write-Host "==> Deploying in LIVE mode with model: $GeminiModel..." -ForegroundColor Green
    $argsList += "--set-env-vars"
    $argsList += "MOCK_LLM=0,GEMINI_MODEL=$GeminiModel,WIKI_USER_AGENT=$WikiUserAgent"
    $argsList += "--set-secrets"
    $argsList += "GOOGLE_API_KEY=gemini-api-key:latest"
}

Write-Host "==> Running: gcloud $($argsList -join ' ')" -ForegroundColor Cyan
& gcloud @argsList
