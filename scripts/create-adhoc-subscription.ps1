<#
  create-adhoc-subscription.ps1
  Creates the standing Graph subscription for Teams ad-hoc call transcripts.
  Reads app creds from ..\.env.local and the cert from the temp dir produced
  by the cert-generation step. Read-only except for the one POST that creates
  the subscription. Prints the subscription id + expiry on success.
#>
$ErrorActionPreference = 'Stop'

function Get-Val([string]$key) {
    $envFile = Join-Path $PSScriptRoot '..\.env.local'
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if ($line) { return ($line -replace "^\s*$key\s*=\s*", '').Trim().Trim('"').Trim("'") }
    return $null
}

$tenantId = Get-Val 'AZURE_TENANT_ID'
$clientId = Get-Val 'AZURE_GRAPH_CLIENT_ID'
$secret   = Get-Val 'AZURE_GRAPH_CLIENT_SECRET'

$certDir = Join-Path $env:TEMP 'oracle-teams-cert'
$certB64 = (Get-Content (Join-Path $certDir 'cert.b64.txt') -Raw).Trim()
$clientState = (Get-Content (Join-Path $certDir 'clientState.txt') -Raw).Trim()
$certId = (Get-Content (Join-Path $certDir 'certId.txt') -Raw).Trim()

$notifyUrl = 'https://oracle.designflow.app/api/teams/notifications'

# App-only token
$tok = Invoke-RestMethod -Method Post `
    -Uri ("https://login.microsoftonline.com/{0}/oauth2/v2.0/token" -f $tenantId) `
    -ContentType 'application/x-www-form-urlencoded' `
    -Body @{ client_id=$clientId; client_secret=$secret; scope='https://graph.microsoft.com/.default'; grant_type='client_credentials' }
$H = @{ Authorization = "Bearer $($tok.access_token)"; 'content-type' = 'application/json' }

$expiry = (Get-Date).ToUniversalTime().AddMinutes(55).ToString("yyyy-MM-ddTHH:mm:ss.0000000Z")

$body = @{
    changeType                = 'created'
    resource                  = 'communications/adhocCalls/getAllTranscripts'
    notificationUrl           = $notifyUrl
    lifecycleNotificationUrl  = $notifyUrl
    includeResourceData       = $true
    encryptionCertificate     = $certB64
    encryptionCertificateId   = $certId
    clientState               = $clientState
    expirationDateTime        = $expiry
} | ConvertTo-Json -Depth 5

function Try-Create([string]$base) {
    Write-Host ("--- POST {0}/subscriptions ---" -f $base) -ForegroundColor Cyan
    try {
        $r = Invoke-RestMethod -Method Post -Headers $H -Uri "$base/subscriptions" -Body $body
        Write-Host "SUCCESS - subscription created." -ForegroundColor Green
        "  id          = $($r.id)"
        "  resource    = $($r.resource)"
        "  expires     = $($r.expirationDateTime)"
        "  notifyUrl   = $($r.notificationUrl)"
        return $true
    } catch {
        $code = $null; try { $code = [int]$_.Exception.Response.StatusCode } catch {}
        Write-Host ("FAILED (HTTP {0})" -f $code) -ForegroundColor Yellow
        try { if ($_.ErrorDetails.Message) { Write-Host ($_.ErrorDetails.Message -replace '\s+',' ') -ForegroundColor DarkYellow } } catch {}
        return $false
    }
}

if (-not (Try-Create 'https://graph.microsoft.com/v1.0')) {
    Write-Host "Retrying on beta endpoint (preview resource may require it)..." -ForegroundColor Cyan
    Try-Create 'https://graph.microsoft.com/beta' | Out-Null
}