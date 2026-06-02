param(
    [string]$VenvPath = ".venv",
    [int]$PreferredPort = 8088,
    [switch]$ForceNpmCi,
    [switch]$SkipBrowser,
    [switch]$Reinitialize,
    [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host "[qwenpaw-dev] $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    throw $Message
}

function Test-CommandAvailable {
    param([string]$Command)
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Resolve-PythonCommand {
    $candidates = @(
        @("py", "-3.12"),
        @("py", "-3.11"),
        @("py", "-3.10"),
        @("py", "-3.13"),
        @("python")
    )

    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        if (-not (Test-CommandAvailable $command)) {
            continue
        }

        try {
            if ($candidate.Length -gt 1) {
                & $command $candidate[1..($candidate.Length - 1)] --version *> $null
            } else {
                & $command --version *> $null
            }
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    Fail "Python 3.10-3.13 is required. Install Python first, then re-run this script."
}

function Get-VenvPythonPath {
    param([string]$Path)
    return Join-Path $Path "Scripts\python.exe"
}

function Get-VenvQwenPawPath {
    param([string]$Path)
    return Join-Path $Path "Scripts\qwenpaw.exe"
}

function Ensure-Venv {
    param([string]$Path)

    $venvPython = Get-VenvPythonPath -Path $Path
    if (Test-Path $venvPython) {
        Write-Step "Using existing virtual environment at $Path"
        return
    }

    $pythonCommand = Resolve-PythonCommand
    Write-Step "Creating virtual environment at $Path"
    if ($pythonCommand.Length -gt 1) {
        & $pythonCommand[0] $pythonCommand[1..($pythonCommand.Length - 1)] -m venv $Path
    } else {
        & $pythonCommand[0] -m venv $Path
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fail "Failed to create virtual environment at $Path"
    }
}

function Ensure-PythonDependencies {
    param([string]$Path)

    $venvPython = Get-VenvPythonPath -Path $Path
    Write-Step "Upgrading pip tooling"
    & $venvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to upgrade pip tooling"
    }

    Write-Step "Installing editable development dependencies"
    & $venvPython -m pip install -e ".[dev,full]"
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to install Python dependencies"
    }

    if (-not (Test-Path (Get-VenvQwenPawPath -Path $Path))) {
        Fail "qwenpaw.exe was not created in the virtual environment"
    }
}

function Ensure-NodeDependencies {
    if (-not (Test-CommandAvailable "npm")) {
        Fail "Node.js with npm is required to build the console frontend. Install Node.js first, then re-run this script."
    }

    Push-Location (Join-Path $RepoRoot "console")
    try {
        if ($ForceNpmCi -or -not (Test-Path "node_modules")) {
            Write-Step "Installing console dependencies with npm ci"
            npm ci
            if ($LASTEXITCODE -ne 0) {
                Fail "npm ci failed in console/"
            }
        } else {
            Write-Step "Using existing console/node_modules"
        }

        Write-Step "Building console frontend"
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Fail "npm run build failed in console/"
        }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path (Join-Path $RepoRoot "console\dist\index.html"))) {
        Fail "console/dist/index.html was not produced by the frontend build"
    }
}

function Ensure-Initialized {
    param([string]$Path)

    $qwenpawExe = Get-VenvQwenPawPath -Path $Path
    $configPath = Join-Path $HOME ".qwenpaw\config.json"
    if ((Test-Path $configPath) -and -not $Reinitialize) {
        Write-Step "Using existing QwenPaw config at $configPath"
        return
    }

    Write-Step "Initializing QwenPaw defaults"
    & $qwenpawExe init --defaults --accept-security
    if ($LASTEXITCODE -ne 0) {
        Fail "qwenpaw init failed"
    }
}

function Test-PortAvailable {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Resolve-AppPort {
    param([int]$Port)

    if (Test-PortAvailable -Port $Port) {
        return $Port
    }

    foreach ($candidate in 18088..18110) {
        if (Test-PortAvailable -Port $candidate) {
            Write-Step "Preferred port $Port is busy, falling back to $candidate"
            return $candidate
        }
    }

    Fail "No available port found for QwenPaw"
}

function Start-BrowserProbe {
    param([string]$Url)

    if ($SkipBrowser) {
        return $null
    }

    return Start-Job -ScriptBlock {
        param([string]$TargetUrl)

        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            try {
                $response = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 3
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                    Start-Process $TargetUrl | Out-Null
                    return
                }
            } catch {
            }
            Start-Sleep -Seconds 2
        }
    } -ArgumentList $Url
}

function Stop-BrowserProbe {
    param($Job)

    if ($null -eq $Job) {
        return
    }

    try {
        Stop-Job -Job $Job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $Job -Force -ErrorAction SilentlyContinue | Out-Null
    } catch {
    }
}

if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    Fail "Run this script from the checked-out QwenPaw repository."
}

Ensure-Venv -Path $VenvPath
Ensure-PythonDependencies -Path $VenvPath
Ensure-NodeDependencies
Ensure-Initialized -Path $VenvPath

$port = Resolve-AppPort -Port $PreferredPort
$url = "http://127.0.0.1:$port/"

Write-Step "QwenPaw will be available at $url"

if ($InstallOnly) {
    Write-Step "InstallOnly specified; skipping app startup"
    exit 0
}

$browserJob = Start-BrowserProbe -Url $url
$qwenpawExe = Get-VenvQwenPawPath -Path $VenvPath

try {
    Write-Step "Starting QwenPaw app"
    & $qwenpawExe app --port $port
    exit $LASTEXITCODE
} finally {
    Stop-BrowserProbe -Job $browserJob
}