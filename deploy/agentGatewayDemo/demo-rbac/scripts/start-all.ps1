# Start all RBAC demo services in background (no popup windows).
# Run from DeployRoot:  .\demo-rbac\scripts\start-all.ps1
# Stop services:        .\demo-rbac\scripts\stop-all.ps1

param(
    [switch]$Restart
)

. "$PSScriptRoot\_common.ps1"

$ErrorActionPreference = "Stop"
Set-DeployLocation
Install-DemoPythonDeps
$AgwExe = Assert-AgentGateway

if (Test-DemoServicesRunning) {
    if ($Restart) {
        Write-Host "Restarting demo services..." -ForegroundColor Yellow
        Stop-DemoServices | Out-Null
        Start-Sleep -Seconds 1
    } else {
        Write-Host "Demo services already running in background." -ForegroundColor Yellow
        Write-Host "  Stop:    .\demo-rbac\scripts\stop-all.ps1" -ForegroundColor DarkGray
        Write-Host "  Restart: .\demo-rbac\scripts\start-all.ps1 -Restart" -ForegroundColor DarkGray
        exit 0
    }
}

$hrServer = Join-DemoPath "mcp-hr\server.py"
$forumServer = Join-DemoPath "mcp-forum\server.py"
$agwConfig = Join-DemoPath "config\agentgateway-rbac.yaml"
$gatewayLog = Join-DemoPath "logs\gateway-access.log"
$hrLog = Join-DemoPath "logs\mcp-hr.log"
$forumLog = Join-DemoPath "logs\mcp-forum.log"

Write-Host ""
Write-Host "=== RBAC Demo - Starting services (background) ===" -ForegroundColor Green
Write-Host "DeployRoot: $Script:DeployRoot"
Write-Host ""

$processes = @()

$processes += Start-DemoBackgroundProcess `
    -Name "mcp-hr" `
    -FilePath "python" `
    -ArgumentList @($hrServer) `
    -WorkingDirectory $Script:DeployRoot `
    -LogFile $hrLog
Start-Sleep -Seconds 1

$processes += Start-DemoBackgroundProcess `
    -Name "mcp-forum" `
    -FilePath "python" `
    -ArgumentList @($forumServer) `
    -WorkingDirectory $Script:DeployRoot `
    -LogFile $forumLog
Start-Sleep -Seconds 1

$processes += Start-DemoBackgroundProcess `
    -Name "agentgateway" `
    -FilePath $AgwExe `
    -ArgumentList @("-f", $agwConfig) `
    -WorkingDirectory $Script:DeployRoot `
    -LogFile $gatewayLog
Start-Sleep -Seconds 2

Save-DemoServicesState -Processes $processes -DeployRoot $Script:DeployRoot

Write-Host "Started 3 background services:" -ForegroundColor Green
foreach ($p in $processes) {
    Write-Host "  $($p.name)  PID $($p.pid)  log: $($p.logFile)" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "Stop all (MCP + Gateway + Inspectors):  .\demo-rbac\scripts\stop-all.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Dual Inspector: .\demo-rbac\scripts\open-dual-inspector.ps1"
Write-Host "  2. Helper page:     open .\demo-rbac\inspector-helper.html"
Write-Host "  3. Auto demo:       .\demo-rbac\scripts\run-demo.ps1"
Write-Host "  4. Debug trace:     .\demo-rbac\scripts\start-trace.ps1"
Write-Host "  5. Auth deny audit: .\demo-rbac\scripts\audit-auth-deny.ps1 -RunAttack"
Write-Host "  6. Auth deny viewer: .\demo-rbac\scripts\show-auth-deny.ps1"
Write-Host "  7. Admin Console:   http://localhost:15000/ui"
