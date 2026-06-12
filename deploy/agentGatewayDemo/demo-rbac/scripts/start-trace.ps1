# AgentGateway debug trace (RBAC forensics)
. "$PSScriptRoot\_common.ps1"

$ErrorActionPreference = "Stop"

Write-Host "Streaming debug trace (filter: get_employee)..." -ForegroundColor Cyan
Write-Host "DeployRoot: $Script:DeployRoot"
Write-Host "Trigger attack in Inspector or run run-demo.ps1 in another window" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Look for JSON: type=authorizationResult, result=deny" -ForegroundColor Yellow
Write-Host ""

curl.exe -N "http://127.0.0.1:15000/debug/trace?expression=mcp.tool.name+%3D%3D+%22get_employee%22"
