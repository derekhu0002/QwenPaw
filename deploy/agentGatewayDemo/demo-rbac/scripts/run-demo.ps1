# RBAC automated demo clients
. "$PSScriptRoot\_common.ps1"

$ErrorActionPreference = "Stop"
Set-DeployLocation

$guestClient = Join-DemoPath "clients\demo_guest.py"
$employeeClient = Join-DemoPath "clients\demo_employee.py"
$managerClient = Join-DemoPath "clients\demo_manager.py"

Write-Host "=== RBAC Automated Demo (3 tiers) ===" -ForegroundColor Green
Write-Host "DeployRoot: $Script:DeployRoot"
Write-Host ""

Write-Host "--- 1/3 guest (no token) ---" -ForegroundColor Cyan
python $guestClient
$guestCode = $LASTEXITCODE

Write-Host ""
Write-Host "--- 2/3 employeeQwenpaw (forum author) ---" -ForegroundColor Cyan
python $employeeClient
$code = $LASTEXITCODE

Write-Host ""
Write-Host "--- 3/3 managerQwenpaw (admin) ---" -ForegroundColor Cyan
python $managerClient

Write-Host ""
if ($guestCode -eq 0 -and $code -eq 0) {
    Write-Host "Done: 3-tier RBAC verified; employee HR attack blocked" -ForegroundColor Green
} else {
    Write-Host "Failed: run .\demo-rbac\scripts\start-all.ps1 -Restart first" -ForegroundColor Red
}
