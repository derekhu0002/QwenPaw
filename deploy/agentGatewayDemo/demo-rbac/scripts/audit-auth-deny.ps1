# Run employee attack (optional) then extract auth-deny evidence from Gateway log + debug trace.
#
# Usage:
#   .\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack
#   .\demo-rbac\scripts\audit-auth-deny.ps1              # log only (after manual attack)
#   .\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack -IncludeTrace

param(
    [switch]$RunAttack,
    [switch]$IncludeTrace,
    [int]$TailLines = 800,
    [int]$TraceSeconds = 18
)

. "$PSScriptRoot\_common.ps1"

$ErrorActionPreference = "Stop"
Set-DeployLocation

$LogFile = Join-DemoPath "logs\gateway-access.log"
$TraceFile = Join-DemoPath "logs\trace-capture.tmp"
$EmployeeClient = Join-DemoPath "clients\demo_employee.py"

$RequiredTerms = @("get_employee", "employeeQwenpaw")
$DenyHints = @(
    "deny", "authorizationResult", "authorization", "mcpAuthorization",
    "Unknown tool", "reject", "403", "401", "400", "error", "fail", "invalid"
)

function Test-AttackLine {
    param([string]$Line)
    foreach ($term in $RequiredTerms) {
        if ($Line -notlike "*$term*") {
            return $false
        }
    }
    return $true
}

function Get-DenyHints {
    param([string]$Line)
    $found = @()
    foreach ($hint in $DenyHints) {
        if ($Line -like "*$hint*") {
            $found += $hint
        }
    }
    return $found
}

function Start-TraceCapture {
    param([int]$Seconds)
    $logDir = Split-Path $TraceFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    if (Test-Path $TraceFile) {
        Remove-Item $TraceFile -Force
    }
    $expr = 'jwt.sub == "employeeQwenpaw"'
    $url = "http://127.0.0.1:15000/debug/trace?expression=" + [uri]::EscapeDataString($expr)
    Write-Host "Starting debug trace capture (${Seconds}s, filter: employeeQwenpaw)..." -ForegroundColor DarkGray
    $proc = Start-Process -FilePath "curl.exe" -PassThru -NoNewWindow -Wait:$false `
        -ArgumentList @("-N", "-s", "--max-time", "$Seconds", $url) `
        -RedirectStandardOutput $TraceFile `
        -RedirectStandardError "NUL"
    return $proc
}

function Expand-TraceBody {
    param([string]$JsonLine)
    if ($JsonLine -notmatch '"type"\s*:\s*"bodySnapshot"') { return $null }
    if ($JsonLine -match '"body"\s*:\s*"([^"]+)"') {
        try {
            $bytes = [Convert]::FromBase64String($Matches[1])
            return [Text.Encoding]::UTF8.GetString($bytes)
        } catch {
            return $null
        }
    }
    return $null
}

function Test-TraceAttackEvent {
    param([string]$JsonLine)
    $body = Expand-TraceBody $JsonLine
    $haystack = if ($body) { "$JsonLine`n$body" } else { $JsonLine }
    if ($haystack -notlike "*employeeQwenpaw*") { return $false }
    if ($haystack -like "*get_employee*") { return $true }
    if ($haystack -like "*hr_get_employee*") { return $true }
    if ($haystack -like "*Unknown tool*") { return $true }
    if ($JsonLine -like '*"type":"authorizationResult"*' -and $JsonLine -like '*Deny*') { return $true }
    if ($JsonLine -like '*"result":"deny"*') { return $true }
    return $false
}

function Show-TraceCapture {
    param([System.Diagnostics.Process]$Proc)
    if ($null -ne $Proc -and -not $Proc.HasExited) {
        $Proc | Wait-Process -Timeout 20 -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path $TraceFile)) {
        Write-Host "WARN: no trace capture file (is AgentGateway admin :15000 up?)" -ForegroundColor Yellow
        return 0
    }
    $raw = Get-Content -Path $TraceFile -ErrorAction SilentlyContinue
    if (-not $raw) {
        Write-Host "WARN: trace capture empty." -ForegroundColor Yellow
        return 0
    }

    $events = @()
    foreach ($line in $raw) {
        if ($line -notmatch "^data:\s*(.+)$") { continue }
        $json = $Matches[1].Trim()
        if ($json -eq "") { continue }
        $events += $json
    }

    $relevant = @($events | Where-Object { Test-TraceAttackEvent $_ })

    Write-Host ""
    Write-Host "--- Debug trace (employeeQwenpaw / get_employee / deny) ---" -ForegroundColor Cyan
    if ($relevant.Count -eq 0) {
        Write-Host "No trace events matched get_employee attack or deny hints." -ForegroundColor Yellow
        return 0
    }

    $n = 0
    foreach ($ev in $relevant) {
        $n++
        $hints = Get-DenyHints $ev
        $body = Expand-TraceBody $ev
        if ($body) {
            $hints += @(Get-DenyHints $body)
            $hints = @($hints | Select-Object -Unique)
        }
        if ($hints.Count -gt 0) {
            Write-Host "[$n] [TRACE DENY: $($hints -join ', ')]" -ForegroundColor Red
        } elseif ($ev -like "*employeeQwenpaw*") {
            Write-Host "[$n] [TRACE subject]" -ForegroundColor Yellow
        } else {
            Write-Host "[$n] [TRACE event]" -ForegroundColor DarkGray
        }
        Write-Host $ev
        if ($body -and ($body -like "*get_employee*" -or $body -like "*Unknown tool*")) {
            Write-Host "  decoded body:" -ForegroundColor DarkGray
            Write-Host "  $body" -ForegroundColor DarkGray
        }
        Write-Host ""
    }
    return $relevant.Count
}

Write-Host ""
Write-Host "=== RBAC audit: employeeQwenpaw vs get_employee ===" -ForegroundColor Green
Write-Host "DeployRoot: $Script:DeployRoot"
Write-Host ""

$traceProc = $null
if ($RunAttack -or $IncludeTrace) {
    $traceProc = Start-TraceCapture -Seconds $TraceSeconds
    Start-Sleep -Seconds 1
}

if ($RunAttack) {
    Write-Host "Running attack client (demo_employee.py)..." -ForegroundColor Cyan
    python $EmployeeClient
    $attackCode = $LASTEXITCODE
    Write-Host ""
    if ($attackCode -eq 0) {
        Write-Host "[OK] Attack blocked by gateway (client exit 0)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Client exit code $attackCode (check services)" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 1
}

& "$PSScriptRoot\show-auth-deny.ps1" -TailLines $TailLines
$logExit = $LASTEXITCODE

$traceHits = 0
if ($RunAttack -or $IncludeTrace) {
    $traceHits = Show-TraceCapture -Proc $traceProc
}

Write-Host ""
Write-Host "Done. Access log: $LogFile" -ForegroundColor DarkGray
Write-Host "Live trace stream: .\demo-rbac\scripts\start-trace.ps1" -ForegroundColor DarkGray

if ($logExit -ne 0 -and $traceHits -eq 0 -and -not $RunAttack) {
    exit $logExit
}
exit 0
