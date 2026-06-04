<#
  diagnose-transcripts.ps1
  Tries several ways of asking Microsoft for Albert's transcripts and reports
  exactly what each returns. Read-only. Reads creds from ..\.env.local
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

$tok = Invoke-RestMethod -Method Post `
    -Uri ("https://login.microsoftonline.com/{0}/oauth2/v2.0/token" -f $tenantId) `
    -ContentType 'application/x-www-form-urlencoded' `
    -Body @{ client_id=$clientId; client_secret=$secret; scope='https://graph.microsoft.com/.default'; grant_type='client_credentials' }
$H = @{ Authorization = "Bearer $($tok.access_token)" }

$u = Invoke-RestMethod -Method Get -Headers $H -Uri 'https://graph.microsoft.com/v1.0/users/Albert@popcre.com'
$uid = $u.id
"Organizer: $($u.displayName)  id=$uid"
""

function Try-Url([string]$label, [string]$url) {
    Write-Host ("=== {0} ===" -f $label) -ForegroundColor Cyan
    Write-Host ("    {0}" -f $url) -ForegroundColor DarkGray
    try {
        $r = Invoke-RestMethod -Method Get -Headers $H -Uri $url
        $items = @($r.value)
        Write-Host ("    HTTP 200  - {0} item(s)" -f $items.Count) -ForegroundColor Green
        foreach ($it in $items) {
            Write-Host ("      - created={0}  meetingId={1}" -f $it.createdDateTime, $it.meetingId)
        }
    } catch {
        $code = $null; try { $code = [int]$_.Exception.Response.StatusCode } catch {}
        Write-Host ("    HTTP {0}" -f $code) -ForegroundColor Yellow
        try { if ($_.ErrorDetails.Message) { Write-Host ("    {0}" -f ($_.ErrorDetails.Message -replace '\s+',' ')) -ForegroundColor DarkYellow } } catch {}
    }
    ""
}

$start = '2026-06-01T00:00:00.0000000Z'
$end   = '2026-06-04T00:00:00.0000000Z'

Try-Url 'v1.0 bare' `
  "https://graph.microsoft.com/v1.0/users/$uid/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='$uid')"

Try-Url 'v1.0 with date window' `
  "https://graph.microsoft.com/v1.0/users/$uid/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='$uid',startDateTime=$start,endDateTime=$end)"

Try-Url 'beta bare' `
  "https://graph.microsoft.com/beta/users/$uid/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='$uid')"

Try-Url 'beta with date window' `
  "https://graph.microsoft.com/beta/users/$uid/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='$uid',startDateTime=$start,endDateTime=$end)"
