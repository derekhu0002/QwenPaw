# Filter AgentGateway access log for employeeQwenpaw + get_employee attack lines.
# Requires start-all.ps1 (tee to demo-rbac/logs/gateway-access.log).
#
# Usage:
#   .\demo-rbac\scripts\show-auth-deny.ps1
#   .\demo-rbac\scripts\show-auth-deny.ps1 -TailLines 1200
#   .\demo-rbac\scripts\show-auth-deny.ps1 -NoBrowser

param(
    [int]$TailLines = 800,
    [switch]$NoBrowser
)

. "$PSScriptRoot\_common.ps1"
. "$PSScriptRoot\_auth-log-parse.ps1"

$ErrorActionPreference = "Stop"

$LogFile = Join-DemoPath "logs\gateway-access.log"
$ReportHtml = Join-DemoPath "logs\auth-deny-report.html"

$RequiredTerms = @("get_employee", "employeeQwenpaw")
$DenyHints = @(
    "deny", "Deny", "DENY",
    "authorization", "Authorization", "mcpAuthorization",
    "Unknown tool", "reject", "Reject", "blocked", "BLOCKED",
    "403", "401", "400",
    "error", "Error", "fail", "Fail", "invalid", "exception",
    "audit_mcp_error"
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

Write-Host ""
Write-Host "=== Gateway access log: auth deny forensics ===" -ForegroundColor Cyan
Write-Host "Log file: $LogFile"
Write-Host "Filter: get_employee + employeeQwenpaw (deny/error hints highlighted)" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $LogFile)) {
    Write-Host "ERROR: log file not found." -ForegroundColor Red
    Write-Host "Restart services with: .\demo-rbac\scripts\start-all.ps1" -ForegroundColor Yellow
    Write-Host "(start-all tees Gateway stdout to logs/gateway-access.log)" -ForegroundColor DarkGray
    exit 2
}

$size = (Get-Item $LogFile).Length
if ($size -eq 0) {
    Write-Host "WARN: log file is empty. Trigger attack first (run-demo.ps1 or audit-auth-deny.ps1 -RunAttack)." -ForegroundColor Yellow
    exit 1
}

$allLines = Get-Content -Path $LogFile -Tail $TailLines -ErrorAction Stop
$matched = @($allLines | Where-Object { Test-AttackLine $_ })

if ($matched.Count -eq 0) {
    Write-Host "No lines matched get_employee + employeeQwenpaw in last $TailLines lines." -ForegroundColor Yellow
    Write-Host "Try: .\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack" -ForegroundColor DarkGray
    Write-Host "Or widen tail: -TailLines 2000" -ForegroundColor DarkGray
    exit 1
}

Write-Host "Matched $($matched.Count) line(s):" -ForegroundColor Green
Write-Host ""

$idx = 0
foreach ($line in $matched) {
    $idx++
    $hints = Get-DenyHints $line
    if ($hints.Count -gt 0) {
        Write-Host "[$idx] [AUTH/DENY: $($hints -join ', ')]" -ForegroundColor Red
    } else {
        Write-Host "[$idx] [request audit]" -ForegroundColor Yellow
    }
    Write-Host $line
    Write-Host ""
}

$withDeny = @($matched | Where-Object { (Get-DenyHints $_).Count -gt 0 })
if ($withDeny.Count -eq 0) {
    Write-Host "Note: access log may not contain literal 'deny'. Check trace section:" -ForegroundColor DarkGray
    Write-Host "  .\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack -IncludeTrace" -ForegroundColor DarkGray
}

$entries = @()
$idx = 0
foreach ($line in $matched) {
    $idx++
    $entry = Build-AuthDenyEntry -Line $line -DenyHints @(Get-DenyHints $line)
    $entry.index = $idx
    $entries += $entry
}

try {
    $reportPath = Write-AuthDenyReport -Entries $entries -LogFile $LogFile -OutputHtml $ReportHtml
    Write-Host "Report: $reportPath" -ForegroundColor Green
    if (-not $NoBrowser) {
        Start-Process $reportPath
        Write-Host "Opened auth deny viewer in browser." -ForegroundColor Green
    }
} catch {
    Write-Host "WARN: failed to generate HTML report: $_" -ForegroundColor Yellow
}

exit 0
