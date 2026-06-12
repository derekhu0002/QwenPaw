# Stop RBAC demo background services (MCP + AgentGateway + Inspectors).
# Run from DeployRoot:  .\demo-rbac\scripts\stop-all.ps1

. "$PSScriptRoot\_common.ps1"

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== RBAC Demo - Stop services ===" -ForegroundColor Cyan
Write-Host "DeployRoot: $Script:DeployRoot"
Write-Host ""

Stop-DemoServices

Write-Host ""
Write-Host "All background services stopped (MCP, Gateway, Inspectors)." -ForegroundColor Green
