# Parse AgentGateway access log lines and build auth-deny report objects (ASCII-safe).

function Parse-AccessLogLine {
    param([string]$Line)

    $result = [ordered]@{
        raw       = $Line
        timestamp = $null
        level     = $null
        scope     = $null
        fields    = @{}
    }

    $rest = $Line
    if ($Line -match '^(\S+)\s+(\S+)\s+(\S+)\s+(.*)$') {
        $result.timestamp = $Matches[1]
        $result.level = $Matches[2]
        $result.scope = $Matches[3]
        $rest = $Matches[4]
    }

    $quotedPattern = '(?<key>[\w.\-]+)="(?<val>[^"]*)"'
    foreach ($match in [regex]::Matches($rest, $quotedPattern)) {
        $result.fields[$match.Groups['key'].Value] = $match.Groups['val'].Value
    }

    $stripped = [regex]::Replace($rest, '[\w.\-]+="[^"]*"', ' ')
    $plainPattern = '(?<key>[\w.\-]+)=(?<val>\S+)'
    foreach ($match in [regex]::Matches($stripped, $plainPattern)) {
        $key = $match.Groups['key'].Value
        if (-not $result.fields.ContainsKey($key)) {
            $result.fields[$key] = $match.Groups['val'].Value
        }
    }

    return $result
}

function Build-AuthDenyEntry {
    param(
        [string]$Line,
        [string[]]$DenyHints
    )

    $parsed = Parse-AccessLogLine $Line
    $f = $parsed.fields

    $subject = $f['jwt.sub']
    $internalTool = $f['gen_ai.tool.name']
    if (-not $internalTool) { $internalTool = $f['audit_mcp_tool'] }

    $clientTool = $internalTool
    $target = $f['mcp.target']
    if ($target -and $internalTool) {
        $clientTool = "${target}_${internalTool}"
    }
    if ($f['error'] -match 'Unknown tool:\s*(\S+)') {
        $clientTool = $Matches[1]
    }

    $status = $f['http.status']
    $isDeny = ($DenyHints.Count -gt 0) -or ($status -in @('400', '401', '403'))

    $role = 'unknown'
    if ($subject -eq 'employeeQwenpaw') { $role = 'employee' }
    elseif ($subject -eq 'managerQwenpaw') { $role = 'manager' }

    $highlightKeys = @(
        'jwt.sub', 'gen_ai.tool.name', 'audit_mcp_tool', 'http.status',
        'error', 'reason', 'mcp.method.name', 'mcp.target', 'mcp.resource.type'
    )

    $fieldRows = @()
    foreach ($key in ($f.Keys | Sort-Object)) {
        $fieldRows += [ordered]@{
            key       = $key
            value     = $f[$key]
            highlight = ($highlightKeys -contains $key)
        }
    }

    return [ordered]@{
        index     = 0
        verdict   = if ($isDeny) { 'deny' } else { 'audit' }
        denyHints = @($DenyHints)
        summary   = [ordered]@{
            subject      = $subject
            role         = $role
            actionTool   = $clientTool
            internalTool = $internalTool
            mcpTarget    = $target
            httpStatus   = $status
            error        = $f['error']
            reason       = $f['reason']
            timestamp    = $parsed.timestamp
            mcpMethod    = $f['mcp.method.name']
        }
        parsed    = @{
            timestamp = $parsed.timestamp
            level     = $parsed.level
            scope     = $parsed.scope
            fields    = $f
        }
        fieldRows = $fieldRows
        raw       = $Line
    }
}

function Write-AuthDenyReport {
    param(
        [array]$Entries,
        [string]$LogFile,
        [string]$OutputHtml
    )

    $report = [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString('o')
        logFile     = $LogFile
        filter      = 'get_employee + employeeQwenpaw'
        count       = $Entries.Count
        entries     = $Entries
    }

    $json = $report | ConvertTo-Json -Depth 8 -Compress
    $templatePath = Join-DemoPath 'auth-deny-viewer.template.html'
    if (-not (Test-Path $templatePath)) {
        throw "Template not found: $templatePath"
    }

    $html = Get-Content -Path $templatePath -Raw -Encoding UTF8
    $html = $html.Replace('__REPORT_JSON__', $json)

    $outDir = Split-Path $OutputHtml -Parent
    if ($outDir -and -not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    }

    [System.IO.File]::WriteAllText($OutputHtml, $html, [System.Text.UTF8Encoding]::new($false))
    return $OutputHtml
}
