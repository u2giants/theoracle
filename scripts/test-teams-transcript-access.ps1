<#
  test-teams-transcript-access.ps1

  PURPOSE
  -------
  A no-dependency probe that answers ONE question:
  "Is this Microsoft tenant set up to let The Oracle read Teams call transcripts?"

  It does NOT change anything. It only reads. Safe to run any number of times.

  WHAT IT CHECKS (in order, stopping at the first failure):
    1. Can we get a Microsoft access token with the app's keys?      (credentials OK?)
    2. Can we read the user directory? (we already have this today)   (basic Graph OK?)
    3. Can we read Teams meeting transcripts?                         (the NEW permission)

  HOW TO RUN
  ----------
  This script needs three values from your Microsoft app registration:
    AZURE_TENANT_ID, AZURE_GRAPH_CLIENT_ID, AZURE_GRAPH_CLIENT_SECRET

  Put them in a file named  .env.local  at the repo root (this file is
  git-ignored, so the secret never gets committed or shared), like:

    AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    AZURE_GRAPH_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    AZURE_GRAPH_CLIENT_SECRET=your-secret-here

  Then run from the repo root:
    pwsh ./scripts/test-teams-transcript-access.ps1

  (You can also set them as environment variables instead of the file.)
#>

$ErrorActionPreference = 'Stop'

function Read-DotEnvValue([string]$key) {
    $fromEnv = [Environment]::GetEnvironmentVariable($key)
    if ($fromEnv) { return $fromEnv }     # env var wins if set
    $envFile = Join-Path $PSScriptRoot '..\.env.local'
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
        if ($line) { return ($line -replace "^\s*$key\s*=\s*", '').Trim().Trim('"').Trim("'") }
    }
    return $null
}

Write-Host ""
Write-Host "=== Teams transcript access probe ===" -ForegroundColor Cyan
Write-Host ""

# --- Gather the three keys --------------------------------------------------
$tenantId = Read-DotEnvValue 'AZURE_TENANT_ID'
$clientId = Read-DotEnvValue 'AZURE_GRAPH_CLIENT_ID'
$secret   = Read-DotEnvValue 'AZURE_GRAPH_CLIENT_SECRET'

$missing = @()
if (-not $tenantId) { $missing += 'AZURE_TENANT_ID' }
if (-not $clientId) { $missing += 'AZURE_GRAPH_CLIENT_ID' }
if (-not $secret)   { $missing += 'AZURE_GRAPH_CLIENT_SECRET' }

if ($missing.Count -gt 0) {
    Write-Host "STOP: missing the following value(s):" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Put them in a .env.local file at the repo root (see the top of this script)," -ForegroundColor Yellow
    Write-Host "then run this again. The secret stays on your machine; it is git-ignored." -ForegroundColor Yellow
    exit 1
}

Write-Host ("Tenant : {0}" -f $tenantId)
Write-Host ("App ID : {0}" -f $clientId)
Write-Host  "Secret : (loaded, not shown)"
Write-Host ""

# --- Step 1: get an app-only token -----------------------------------------
Write-Host "[1/3] Getting a Microsoft access token..." -ForegroundColor Cyan
try {
    $tokenResp = Invoke-RestMethod -Method Post `
        -Uri ("https://login.microsoftonline.com/{0}/oauth2/v2.0/token" -f $tenantId) `
        -ContentType 'application/x-www-form-urlencoded' `
        -Body @{
            client_id     = $clientId
            client_secret = $secret
            scope         = 'https://graph.microsoft.com/.default'
            grant_type    = 'client_credentials'
        }
    $token = $tokenResp.access_token
    Write-Host "      OK - got a token." -ForegroundColor Green
} catch {
    Write-Host "      FAILED to get a token." -ForegroundColor Red
    Write-Host "      => The app keys (tenant/app id/secret) are wrong, expired, or the app does not exist." -ForegroundColor Red
    Write-Host ("      Raw error: {0}" -f $_.Exception.Message)
    exit 1
}
$headers = @{ Authorization = "Bearer $token" }

# --- Step 2: read the user directory (a permission we KNOW we have today) ---
Write-Host "[2/3] Reading the user directory (sanity check)..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Method Get -Headers $headers `
        -Uri 'https://graph.microsoft.com/v1.0/users?$top=1' | Out-Null
    Write-Host "      OK - basic Microsoft Graph access works." -ForegroundColor Green
} catch {
    Write-Host "      FAILED - even basic directory read did not work." -ForegroundColor Red
    Write-Host "      => The app exists but has lost its 'User.Read.All' permission/consent." -ForegroundColor Red
    Write-Host ("      Raw error: {0}" -f $_.Exception.Message)
    exit 1
}

# --- Step 3: the real test - can we read Teams transcripts? -----------------
Write-Host "[3/3] Trying to read Teams call transcripts..." -ForegroundColor Cyan

# Transcripts are read per meeting-organizer. Default to the account owner;
# override by setting an ORACLE_TEST_ORGANIZER environment variable to another email.
$organizerEmail = [Environment]::GetEnvironmentVariable('ORACLE_TEST_ORGANIZER')
if (-not $organizerEmail) { $organizerEmail = 'Albert@popcre.com' }
Write-Host ("      Checking meetings organized by: {0}" -f $organizerEmail)

try {
    $userObj = Invoke-RestMethod -Method Get -Headers $headers `
        -Uri ("https://graph.microsoft.com/v1.0/users/{0}" -f $organizerEmail)
    $organizerId = $userObj.id
} catch {
    Write-Host "      Could not find that person in the directory - check the email address." -ForegroundColor Yellow
    Write-Host ("      Raw error: {0}" -f $_.Exception.Message)
    exit 1
}

$transcriptUri = "https://graph.microsoft.com/v1.0/users/$organizerId/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='$organizerId')"
try {
    $resp = Invoke-RestMethod -Method Get -Headers $headers -Uri $transcriptUri
    $count = @($resp.value).Count
    Write-Host ""
    Write-Host "      SUCCESS - the tenant ALLOWS transcript access." -ForegroundColor Green
    Write-Host ("      (Found {0} transcript record(s) on this first page.)" -f $count) -ForegroundColor Green
    Write-Host ""
    Write-Host "VERDICT: Ready to build the Teams ingestion feature." -ForegroundColor Green
} catch {
    $status = $null
    try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    Write-Host ""
    Write-Host "      Transcript access is NOT available yet." -ForegroundColor Yellow
    if ($status -eq 403) {
        Write-Host "      => 403 Forbidden: the app needs the 'OnlineMeetingTranscript.Read.All'" -ForegroundColor Yellow
        Write-Host "         permission AND a Teams 'application access policy'. This is the" -ForegroundColor Yellow
        Write-Host "         one-time IT-admin setup. Until that is done, this is expected." -ForegroundColor Yellow
    } elseif ($status -eq 401) {
        Write-Host "      => 401 Unauthorized: token rejected for this endpoint - permission not consented." -ForegroundColor Yellow
    } else {
        Write-Host ("      => HTTP {0}. See raw error below." -f $status) -ForegroundColor Yellow
    }
    # Surface Graph's own message - it usually names exactly what is missing.
    try {
        $body = $_.ErrorDetails.Message
        if ($body) { Write-Host ""; Write-Host "      Microsoft's message:" -ForegroundColor DarkYellow; Write-Host "      $body" -ForegroundColor DarkYellow }
    } catch {}
    Write-Host ""
    Write-Host "VERDICT: Not set up yet. Send the IT-admin steps to whoever runs your Microsoft 365." -ForegroundColor Yellow
}
Write-Host ""
